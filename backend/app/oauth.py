import secrets
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import User
from .seed import ensure_initialization_membership


def require_oauth_settings():
    settings = get_settings()
    if not settings.oauth_enabled:
        raise HTTPException(503, '企业 OAuth 尚未启用，请联系系统管理员配置 OIDC')
    required = {
        'OAUTH_ISSUER_URL': settings.oauth_issuer_url,
        'OAUTH_CLIENT_ID': settings.oauth_client_id,
        'OAUTH_CLIENT_SECRET': settings.oauth_client_secret,
        'OAUTH_REDIRECT_URI': settings.oauth_redirect_uri,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise HTTPException(503, f'OIDC 配置不完整：{", ".join(missing)}')
    if settings.environment == 'production':
        for name, value in (('OAUTH_REDIRECT_URI', settings.oauth_redirect_uri), ('OAUTH_ISSUER_URL', settings.oauth_issuer_url)):
            if not value.startswith('https://'):
                raise HTTPException(503, f'生产环境 {name} 必须使用 HTTPS')
    allowed_algorithms = {'RS256', 'RS384', 'RS512', 'PS256', 'PS384', 'PS512', 'ES256', 'ES384', 'ES512', 'EdDSA'}
    if settings.oauth_id_token_algorithm not in allowed_algorithms:
        raise HTTPException(503, 'OAUTH_ID_TOKEN_ALGORITHM 必须配置为非对称签名算法')
    return settings


@lru_cache(maxsize=8)
def oidc_discovery(issuer_url: str) -> dict:
    url = f'{issuer_url.rstrip("/")}/.well-known/openid-configuration'
    try:
        response = httpx.get(url, timeout=15)
        response.raise_for_status()
        metadata = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, '无法读取企业 OIDC 发现配置') from None
    if metadata.get('issuer', '').rstrip('/') != issuer_url.rstrip('/'):
        raise HTTPException(502, '企业 OIDC Issuer 与发现配置不一致')
    for key in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
        if not metadata.get(key):
            raise HTTPException(502, f'企业 OIDC 发现配置缺少 {key}')
    return metadata


def begin_oauth_login() -> tuple[str, str, str]:
    settings = require_oauth_settings()
    metadata = oidc_discovery(settings.oauth_issuer_url)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    query = urlencode({
        'response_type': 'code',
        'client_id': settings.oauth_client_id,
        'redirect_uri': settings.oauth_redirect_uri,
        'scope': settings.oauth_scopes,
        'state': state,
        'nonce': nonce,
    })
    separator = '&' if '?' in metadata['authorization_endpoint'] else '?'
    return f'{metadata["authorization_endpoint"]}{separator}{query}', state, nonce


def _token_request(settings, metadata: dict, code: str) -> dict:
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': settings.oauth_redirect_uri,
        'client_id': settings.oauth_client_id,
    }
    auth = None
    if settings.oauth_token_auth_method == 'client_secret_basic':
        auth = (settings.oauth_client_id, settings.oauth_client_secret)
    elif settings.oauth_token_auth_method == 'client_secret_post':
        data['client_secret'] = settings.oauth_client_secret
    else:
        raise HTTPException(503, 'OAUTH_TOKEN_AUTH_METHOD 仅支持 client_secret_basic 或 client_secret_post')
    try:
        response = httpx.post(metadata['token_endpoint'], data=data, auth=auth, timeout=20)
        response.raise_for_status()
        tokens = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(401, '企业 OAuth 授权码交换失败，请重新登录') from None
    if not tokens.get('id_token'):
        raise HTTPException(502, '企业 OIDC 令牌响应缺少 id_token')
    return tokens


def _oidc_claims(settings, metadata: dict, tokens: dict, expected_nonce: str) -> dict:
    try:
        key = jwt.PyJWKClient(metadata['jwks_uri']).get_signing_key_from_jwt(tokens['id_token']).key
        claims = jwt.decode(
            tokens['id_token'], key, algorithms=[settings.oauth_id_token_algorithm],
            audience=settings.oauth_client_id, issuer=metadata['issuer'],
            options={'require': ['exp', 'iat', 'sub', 'iss', 'aud']},
        )
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, '企业 OIDC 身份令牌校验失败') from None
    if not expected_nonce or claims.get('nonce') != expected_nonce:
        raise HTTPException(401, '企业 OIDC Nonce 校验失败')
    access_token = tokens.get('access_token')
    if metadata.get('userinfo_endpoint') and access_token:
        try:
            response = httpx.get(metadata['userinfo_endpoint'], headers={'Authorization': f'Bearer {access_token}'}, timeout=15)
            response.raise_for_status()
            userinfo = response.json()
        except (httpx.HTTPError, ValueError):
            raise HTTPException(502, '无法读取企业 OIDC 用户信息') from None
        if userinfo.get('sub') != claims.get('sub'):
            raise HTTPException(401, '企业 OIDC UserInfo 主体不一致')
        claims = {**claims, **userinfo}
    return claims


def complete_oauth_login(code: str, expected_nonce: str) -> dict:
    settings = require_oauth_settings()
    metadata = oidc_discovery(settings.oauth_issuer_url)
    tokens = _token_request(settings, metadata, code)
    return _oidc_claims(settings, metadata, tokens, expected_nonce)


def _claim(claims: dict, configured_name: str, fallbacks: tuple[str, ...] = ()) -> str:
    for name in (configured_name, *fallbacks):
        value = claims.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ''


def bind_oauth_user(db: Session, claims: dict) -> User:
    settings = get_settings()
    subject = _claim(claims, 'sub')
    if not subject:
        raise HTTPException(401, '企业 OIDC 用户信息缺少 sub')
    username = _claim(claims, settings.oauth_username_claim, ('preferred_username', 'upn', 'email'))
    employee_id = _claim(claims, settings.oauth_employee_id_claim, ('employee_id', 'employee_number'))
    department = _claim(claims, settings.oauth_department_claim, ('department', 'dept'))
    email = _claim(claims, settings.oauth_email_claim, ('email',))
    if not username or not employee_id:
        raise HTTPException(422, '企业 OIDC 必须返回用户名和工号，请检查 Claim 配置；不能仅按用户名绑定用户')
    for label, value, limit in [('sub', subject, 255), ('用户名', username, 80), ('工号', employee_id, 40),
                                ('所属部门', department, 120), ('邮箱', email, 160)]:
        if len(value) > limit:
            raise HTTPException(422, f'企业 OIDC 返回的{label}超过 {limit} 个字符')
    user = db.scalar(select(User).where(User.oauth_subject == subject))
    if not user:
        user = db.scalar(select(User).where(User.employee_id == employee_id))
        if user and user.oauth_subject and user.oauth_subject != subject:
            raise HTTPException(409, '本地账号已绑定其他企业身份')
        if user:
            user.oauth_subject = subject
        else:
            user = User(username=username, employee_id=employee_id, department=department or None,
                        email=email or None, oauth_subject=subject, is_active=True, is_superuser=False)
            db.add(user)
            db.flush()
            ensure_initialization_membership(db, user)
    if user.is_superuser:
        raise HTTPException(403, '系统管理员请使用本地管理员账号登录')
    if not user.is_active:
        raise HTTPException(403, '用户已停用，请联系系统管理员')
    user.username = username
    if department:
        user.department = department
    if email:
        user.email = email
    db.flush()
    return user

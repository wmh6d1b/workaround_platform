import hmac

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..deps import current_user, user_permissions
from ..models import User
from ..oauth import begin_oauth_login, bind_oauth_user, complete_oauth_login
from ..schemas import LoginInput, OAuthCallbackInput, TokenOut, UserOut
from ..security import create_token, verify_password
from ..services import audit

router = APIRouter(prefix='/auth', tags=['认证与用户'])
OAUTH_COOKIE_PATH = '/api/v1/auth/oauth'


def token_result(db: Session, user: User) -> TokenOut:
    return TokenOut(access_token=create_token(user.id), user=UserOut.model_validate(user), permissions=sorted(user_permissions(db, user)))


@router.post('/login', response_model=TokenOut, summary='本地账号登录（开发调试或生产系统管理员）')
def login(payload: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash) or not user.is_active:
        raise HTTPException(401, '账号或密码错误')
    if get_settings().environment == 'production' and not user.is_superuser:
        raise HTTPException(403, '生产环境仅系统管理员可使用本地账号登录')
    audit(db, user, 'LOGIN', 'auth', user.id)
    db.commit()
    return token_result(db, user)


@router.post('/oauth/login', summary='创建企业 OIDC 授权地址并写入防 CSRF 状态 Cookie')
def oauth_login(response: Response):
    authorization_url, state, nonce = begin_oauth_login()
    secure = get_settings().environment == 'production'
    for name, value in (('wmp_oauth_state', state), ('wmp_oauth_nonce', nonce)):
        response.set_cookie(name, value, max_age=600, httponly=True, secure=secure, samesite='lax', path=OAUTH_COOKIE_PATH)
    return {'authorization_url': authorization_url, 'expires_in': 600}


@router.post('/oauth/callback', response_model=TokenOut, summary='校验 OIDC 回调并绑定已导入的 WMP 用户')
def oauth_callback(payload: OAuthCallbackInput, request: Request, response: Response, db: Session = Depends(get_db)):
    expected_state = request.cookies.get('wmp_oauth_state', '')
    expected_nonce = request.cookies.get('wmp_oauth_nonce', '')
    if not expected_state or not hmac.compare_digest(payload.state, expected_state):
        raise HTTPException(401, 'OAuth State 校验失败，请重新登录')
    claims = complete_oauth_login(payload.code, expected_nonce)
    user = bind_oauth_user(db, claims)
    audit(db, user, 'LOGIN_OAUTH', 'auth', user.id, {'issuer': get_settings().oauth_issuer_url})
    db.commit()
    secure = get_settings().environment == 'production'
    for name in ('wmp_oauth_state', 'wmp_oauth_nonce'):
        response.delete_cookie(name, path=OAUTH_COOKIE_PATH, secure=secure, samesite='lax')
    return token_result(db, user)


@router.get('/me', response_model=UserOut, summary='获取当前用户')
def me(user: User = Depends(current_user)):
    return user


@router.get('/permissions', summary='获取当前用户按钮权限点；传项目 ID 时按项目角色计算')
def permissions(project_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {'permissions': sorted(user_permissions(db, user, project_id))}


@router.post('/logout', summary='退出登录并记录审计')
def logout(user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit(db, user, 'LOGOUT', 'auth', user.id)
    db.commit()
    return {'message': '已退出登录，客户端应清除访问令牌'}


@router.post('/password/forgot', summary='忘记密码入口')
def forgot_password():
    return {'message': '本地管理员密码请联系系统管理员重置；其他用户请使用企业 OAuth 登录'}

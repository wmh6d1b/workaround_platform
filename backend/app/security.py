import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from .config import get_settings

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180_000).hex()
    return f'{salt}${digest}'

def verify_password(password: str, stored: str | None) -> bool:
    if not stored or '$' not in stored:
        return False
    salt, digest = stored.split('$', 1)
    candidate = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 180_000).hex()
    return hmac.compare_digest(candidate, digest)

def create_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': user_id, 'iat': now, 'exp': now + timedelta(minutes=settings.jwt_expire_minutes)}, settings.jwt_secret, algorithm='HS256')

def decode_token(token: str) -> str:
    payload = jwt.decode(token, get_settings().jwt_secret, algorithms=['HS256'])
    return str(payload['sub'])

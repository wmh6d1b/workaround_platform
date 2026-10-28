from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import Project, ProjectMember, User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)

def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '未登录或登录已过期', {'WWW-Authenticate': 'Bearer'})
    try:
        user_id = decode_token(credentials.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '登录凭证无效或已过期') from None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, '用户不存在或已停用')
    return user

def require_superuser(user: User) -> None:
    """Guard platform-wide operations; project roles must never grant them."""
    if not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, '仅系统管理员可执行全局管理操作')


def ensure_operational_project(db: Session, project_id: str) -> None:
    """The OAuth landing project must never carry real business data, including for superusers."""
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status.HTTP_404_NOT_FOUND, '项目不存在')
    if project.code == 'WMP-USER-INIT':
        raise HTTPException(status.HTTP_409_CONFLICT, '用户初始化项目仅用于账号落地，请切换到真实项目后再执行此操作')
    if project.status == 'DISABLED':
        raise HTTPException(status.HTTP_409_CONFLICT, '停用项目不能开展新的规避措施业务')


def user_permissions(db: Session, user: User, project_id: str | None = None) -> set[str]:
    """Project membership takes precedence; global role is the no-membership fallback."""
    if user.is_superuser:
        return {'*'}
    query = select(ProjectMember).where(ProjectMember.user_id == user.id)
    if project_id:
        query = query.where(ProjectMember.project_id == project_id)
    memberships = db.scalars(query).unique().all()
    if project_id and not memberships:
        return {p.code for p in user.global_role.permissions} if user.global_role else set()
    permissions = {p.code for member in memberships for p in member.role.permissions}
    if not project_id and user.global_role:
        permissions.update(p.code for p in user.global_role.permissions)
    return permissions


def authorize(db: Session, user: User, permission: str, project_id: str | None = None) -> None:
    if permission not in user_permissions(db, user, project_id) and not user.is_superuser:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f'缺少操作权限：{permission}')


def accessible_project_ids(db: Session, user: User) -> set[str] | None:
    """Return accessible project IDs; None means unrestricted."""
    if user.is_superuser or user.global_role_id:
        return None
    return set(db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)).all())

from datetime import date, datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, noload

from ..db import get_db
from ..deps import accessible_project_ids, authorize, current_user, require_superuser
from ..models import AuditLog, BuildArtifact, User, Wkd, WkdStatus
from ..services import wkd_list_out

router = APIRouter(tags=['首页与通知'])


@router.get('/dashboard/summary', summary='首页指标、最近更新与待办数据')
def summary(project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'home.view', project_id)
    base = select(Wkd).options(noload(Wkd.operations))
    artifacts_query = select(BuildArtifact)
    if project_id:
        base = base.where(Wkd.project_id == project_id)
        artifacts_query = artifacts_query.where(BuildArtifact.project_id == project_id)
    else:
        allowed_projects = accessible_project_ids(db, user)
        if allowed_projects is not None:
            base = base.where(Wkd.project_id.in_(allowed_projects))
            artifacts_query = artifacts_query.where(BuildArtifact.project_id.in_(allowed_projects))

    def count(query) -> int:
        return db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0

    month_start = datetime.combine(date.today().replace(day=1), time.min)
    recent = db.scalars(base.order_by(Wkd.updated_at.desc()).limit(5)).unique().all()
    todos_query = base.where(Wkd.current_handler_id == user.id)
    todos = db.scalars(todos_query.order_by(Wkd.updated_at.desc()).limit(5)).unique().all()
    return {'total': count(base), 'approved': count(base.where(Wkd.status == WkdStatus.APPROVED)),
            'pending': count(todos_query), 'monthly_new': count(base.where(Wkd.created_at >= month_start)),
            'monthly_builds': count(artifacts_query.where(BuildArtifact.created_at >= month_start)),
            'recent': [wkd_list_out(x) for x in recent], 'todos': [wkd_list_out(x) for x in todos]}


@router.get('/notifications', summary='查询当前用户通知')
def notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'home.view')
    return {'items': [], 'unread': 0}


@router.post('/notifications/read', summary='将全部通知标记为已读')
def read_notifications(db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'home.view')
    return {'message': '全部通知已读'}


@router.get('/audit-logs', summary='查询全局重要操作审计日志（仅系统管理员）')
def audit_logs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    require_superuser(user)
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)).all()
    return [{'id': x.id, 'user_id': x.user_id, 'action': x.action, 'resource_type': x.resource_type,
             'resource_id': x.resource_id, 'detail': x.detail, 'created_at': x.created_at} for x in rows]

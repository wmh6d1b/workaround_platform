from datetime import date, datetime, time

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_project_ids, authorize, current_user, require_superuser
from ..models import AuditLog, BuildArtifact, User, Wkd, WkdStatus
from ..services import wkd_out

router = APIRouter(tags=['首页与通知'])


@router.get('/dashboard/summary', summary='首页指标、最近更新与待办数据')
def summary(project_id: str | None = None, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'home.view', project_id)
    base = select(Wkd)
    artifacts_query = select(BuildArtifact)
    if project_id:
        base = base.where(Wkd.project_id == project_id)
        artifacts_query = artifacts_query.where(BuildArtifact.project_id == project_id)
    else:
        allowed_projects = accessible_project_ids(db, user)
        if allowed_projects is not None:
            base = base.where(Wkd.project_id.in_(allowed_projects))
            artifacts_query = artifacts_query.where(BuildArtifact.project_id.in_(allowed_projects))
    rows = db.scalars(base).unique().all()
    month_start = datetime.combine(date.today().replace(day=1), time.min)
    monthly_builds = db.scalars(artifacts_query.where(BuildArtifact.created_at >= month_start)).all()
    return {'total': len(rows), 'approved': sum(x.status == WkdStatus.APPROVED for x in rows),
            'pending': sum(x.current_handler_id == user.id for x in rows),
            'monthly_new': sum(x.created_at >= month_start for x in rows), 'monthly_builds': len(monthly_builds),
            'recent': [wkd_out(x) for x in sorted(rows, key=lambda x: x.updated_at, reverse=True)[:5]],
            'todos': [wkd_out(x) for x in rows if x.current_handler_id == user.id][:5]}


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

import csv
import io
from datetime import date, datetime, time, timedelta
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import accessible_project_ids, authorize, current_user
from ..models import AuditLog, BuildArtifact, User, Wkd, WkdHistory, WkdStatus
from ..services import wkd_out

router = APIRouter(tags=['首页、通知与数据统计'])


def scoped_wkds(db: Session, user: User, permission: str, project_id: str | None = None,
                version_id: str | None = None, machine_id: str | None = None,
                subsystem_id: str | None = None, start_date: str | None = None, end_date: str | None = None):
    authorize(db, user, permission, project_id)
    query = select(Wkd)
    if project_id:
        query = query.where(Wkd.project_id == project_id)
    else:
        allowed_projects = accessible_project_ids(db, user)
        if allowed_projects is not None: query = query.where(Wkd.project_id.in_(allowed_projects))
    if version_id: query = query.where(Wkd.version_id == version_id)
    if machine_id: query = query.where(Wkd.machines.any(id=machine_id))
    if subsystem_id: query = query.where(Wkd.subsystem_id == subsystem_id)
    if start_date: query = query.where(Wkd.created_at >= start_date)
    if end_date: query = query.where(Wkd.created_at <= f'{end_date} 23:59:59')
    return db.scalars(query).unique().all()


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

@router.get('/statistics', summary='按项目、版本、机台、子系统和日期查询统计数据及流转趋势')
def statistics(project_id: str | None = None, version_id: str | None = None, machine_id: str | None = None,
               subsystem_id: str | None = None, start_date: str | None = None, end_date: str | None = None,
               db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = scoped_wkds(db, user, 'stats.view', project_id, version_id, machine_id, subsystem_id, start_date, end_date)
    status_counts = {status.value: sum(x.status == status for x in rows) for status in WkdStatus}
    try:
        trend_end = date.fromisoformat(end_date) if end_date else date.today()
        trend_start = date.fromisoformat(start_date) if start_date else trend_end - timedelta(days=13)
    except ValueError:
        raise HTTPException(422, '统计日期格式应为 YYYY-MM-DD') from None
    if trend_start > trend_end or (trend_end - trend_start).days > 62:
        raise HTTPException(422, '开始日期不能晚于结束日期，且趋势周期不能超过 63 天')
    days = [trend_start + timedelta(days=i) for i in range((trend_end - trend_start).days + 1)]
    wkd_ids = [x.id for x in rows]
    approvals = []
    if wkd_ids:
        approvals = db.scalars(select(WkdHistory).where(WkdHistory.wkd_id.in_(wkd_ids), WkdHistory.action == 'APPROVE',
            WkdHistory.created_at >= datetime.combine(trend_start, time.min), WkdHistory.created_at <= datetime.combine(trend_end, time.max))).all()
    durations = [(next((h.created_at for h in approvals if h.wkd_id == x.id), x.updated_at) - x.created_at).total_seconds() / 86400
                 for x in rows if x.status == WkdStatus.APPROVED]
    trend = [{'date': day.isoformat(), 'created': sum(x.created_at.date() == day for x in rows),
              'approved': sum(x.created_at.date() == day for x in approvals)} for day in days]
    return {'total': len(rows), 'approved': status_counts['APPROVED'],
            'approval_rate': round(status_counts['APPROVED'] / len(rows) * 100, 1) if rows else 0,
            'average_processing_days': round(sum(durations) / len(durations), 1) if durations else 0,
            'covered_subsystems': len({x.subsystem_id for x in rows}), 'status_counts': status_counts,
            'trend': trend, 'items': [wkd_out(x) for x in rows]}

@router.get('/statistics/export', summary='鉴权并导出统计明细 CSV')
def export_statistics(project_id: str | None = None, version_id: str | None = None, machine_id: str | None = None,
                      subsystem_id: str | None = None, start_date: str | None = None, end_date: str | None = None,
                      db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = scoped_wkds(db, user, 'stats.export', project_id, version_id, machine_id, subsystem_id, start_date, end_date)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['WKD编号', '标题', '项目', '版本', '机台', '子系统', '责任人', '状态', '创建时间'])
    for x in rows: writer.writerow([x.number, x.title, x.project.name, x.version.number, ','.join(m.name for m in x.machines), x.subsystem.name, x.owner.name, x.status.value, x.created_at])
    content = '\ufeff' + output.getvalue()
    return StreamingResponse(iter([content.encode('utf-8')]), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=wmp-statistics.csv'})

@router.get('/audit-logs', summary='查询重要操作审计日志')
def audit_logs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not user.is_superuser: authorize(db, user, 'system.role.view')
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)).all()
    return [{'id': x.id, 'user_id': x.user_id, 'action': x.action, 'resource_type': x.resource_type,
             'resource_id': x.resource_id, 'detail': x.detail, 'created_at': x.created_at} for x in rows]

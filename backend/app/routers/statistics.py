import csv
import io
from collections import Counter
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import current_user
from ..models import ExecutionType, Machine, Project, Stage, Subsystem, User, Version, Wkd, WkdHistory, WkdStatus
from ..services import wkd_out

router = APIRouter(tags=['数据统计'])


def parse_period(start_date: str | None, end_date: str | None) -> tuple[date, date]:
    try:
        end = date.fromisoformat(end_date) if end_date else date.today()
        start = date.fromisoformat(start_date) if start_date else end - timedelta(days=13)
    except ValueError:
        raise HTTPException(422, '统计日期格式应为 YYYY-MM-DD') from None
    if start > end or (end - start).days > 365:
        raise HTTPException(422, '开始日期不能晚于结束日期，且统计周期不能超过 366 天')
    return start, end


def scoped_wkds(db: Session, scope: str, project_ids: list[str] | None,
                version_ids: list[str] | None, machine_ids: list[str] | None, subsystem_ids: list[str] | None,
                found_version_ids: list[str] | None, planned_version_ids: list[str] | None,
                statuses: list[WkdStatus] | None, execution_types: list[ExecutionType] | None,
                activity_scenes: list[str] | None, measure_types: list[str] | None,
                owner_ids: list[str] | None, handler_ids: list[str] | None, stages: list[Stage] | None,
                keyword: str | None, date_field: str, start_date: str | None, end_date: str | None):
    if scope not in {'project', 'global'}:
        raise HTTPException(422, '统计作用域仅支持 project 或 global')
    if scope == 'project' and (not project_ids or len(project_ids) != 1):
        raise HTTPException(422, '项目统计必须且只能指定一个项目')
    query = select(Wkd)
    if project_ids:
        query = query.where(Wkd.project_id.in_(project_ids))
    if version_ids:
        query = query.where(Wkd.version_id.in_(version_ids))
    if machine_ids:
        query = query.where(Wkd.machines.any(Machine.id.in_(machine_ids)))
    if subsystem_ids:
        query = query.where(Wkd.subsystem_id.in_(subsystem_ids))
    if found_version_ids:
        query = query.where(Wkd.found_version_id.in_(found_version_ids))
    if planned_version_ids:
        query = query.where(Wkd.planned_version_id.in_(planned_version_ids))
    if statuses:
        query = query.where(Wkd.status.in_(statuses))
    if execution_types:
        query = query.where(Wkd.execution_type.in_(execution_types))
    if activity_scenes:
        query = query.where(Wkd.activity_scene.in_(activity_scenes))
    if measure_types:
        query = query.where(Wkd.measure_type.in_(measure_types))
    if owner_ids:
        query = query.where(Wkd.owner_id.in_(owner_ids))
    if handler_ids:
        query = query.where(Wkd.current_handler_id.in_(handler_ids))
    if stages:
        query = query.where(Wkd.stage.in_(stages))
    if keyword and keyword.strip():
        value = f'%{keyword.strip()}%'
        query = query.where((Wkd.number.ilike(value)) | (Wkd.title.ilike(value)) |
                            (Wkd.issue_no.ilike(value)) | (Wkd.requirement_no.ilike(value)))
    if date_field not in {'created', 'updated'}:
        raise HTTPException(422, '日期字段仅支持 created 或 updated')
    start, end = parse_period(start_date, end_date)
    if start_date:
        query = query.where((Wkd.created_at if date_field == 'created' else Wkd.updated_at) >= datetime.combine(start, time.min))
    if end_date:
        query = query.where((Wkd.created_at if date_field == 'created' else Wkd.updated_at) <= datetime.combine(end, time.max))
    return db.scalars(query).unique().all(), start, end


def bucket(day: date, granularity: str) -> date:
    if granularity == 'week':
        return day - timedelta(days=day.weekday())
    if granularity == 'month':
        return day.replace(day=1)
    return day


def trend_data(rows: list[Wkd], approvals: list[WkdHistory], start: date, end: date):
    days = (end - start).days + 1
    granularity = 'day' if days <= 31 else 'week' if days <= 93 else 'month'
    created = Counter(bucket(x.created_at.date(), granularity) for x in rows if start <= x.created_at.date() <= end)
    approved = Counter(bucket(x.created_at.date(), granularity) for x in approvals if start <= x.created_at.date() <= end)
    keys = sorted(set(created) | set(approved))
    if not keys:
        keys = [bucket(start, granularity)]
    return granularity, [{'date': key.isoformat(), 'created': created[key], 'approved': approved[key]} for key in keys]


def query_arguments(scope: str = 'project', project_ids: list[str] | None = Query(None),
                    version_ids: list[str] | None = Query(None), machine_ids: list[str] | None = Query(None),
                    subsystem_ids: list[str] | None = Query(None), found_version_ids: list[str] | None = Query(None),
                    planned_version_ids: list[str] | None = Query(None), statuses: list[WkdStatus] | None = Query(None),
                    execution_types: list[ExecutionType] | None = Query(None), activity_scenes: list[str] | None = Query(None),
                    measure_types: list[str] | None = Query(None), owner_ids: list[str] | None = Query(None),
                    handler_ids: list[str] | None = Query(None), stages: list[Stage] | None = Query(None),
                    keyword: str | None = Query(None, max_length=100), date_field: str = 'created',
                    start_date: str | None = None, end_date: str | None = None):
    return locals()


@router.get('/statistics/options', summary='获取全部统计筛选项（所有已登录用户）')
def statistics_options(db: Session = Depends(get_db), user: User = Depends(current_user)):
    def rows(model):
        return [{column.name: getattr(item, column.name) for column in item.__table__.columns}
                for item in db.scalars(select(model)).all()]
    return {'projects': rows(Project), 'versions': rows(Version), 'machines': rows(Machine),
            'subsystems': rows(Subsystem), 'roles': [],
            'users': [{'id': item.id, 'username': item.username, 'employee_id': item.employee_id, 'department': item.department}
                      for item in db.scalars(select(User).where(User.is_active.is_(True))).all()]}


@router.get('/statistics', summary='项目内或全局多维统计（所有已登录用户，多选筛选、趋势与分布）')
def statistics(filters: dict = Depends(query_arguments), db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows, start, end = scoped_wkds(db, **filters)
    status_counts = {status.value: sum(x.status == status for x in rows) for status in WkdStatus}
    wkd_ids = [x.id for x in rows]
    approvals = list(db.scalars(select(WkdHistory).where(WkdHistory.wkd_id.in_(wkd_ids), WkdHistory.action == 'APPROVE')).all()) if wkd_ids else []
    first_approvals = {}
    for history in sorted(approvals, key=lambda x: x.created_at):
        first_approvals.setdefault(history.wkd_id, history.created_at)
    durations = [(first_approvals[x.id] - x.created_at).total_seconds() / 86400 for x in rows if x.id in first_approvals]
    granularity, trend = trend_data(rows, approvals, start, end)
    project_counts = Counter(x.project.name for x in rows)
    execution_counts = Counter(x.execution_type.value for x in rows)
    return {'scope': filters['scope'], 'total': len(rows), 'approved': status_counts['APPROVED'],
            'pending': sum(status_counts[status] for status in ('VERIFY', 'REVIEW', 'DISABLE_CONFIRM')),
            'approval_rate': round(status_counts['APPROVED'] / len(rows) * 100, 1) if rows else 0,
            'average_processing_days': round(sum(durations) / len(durations), 1) if durations else 0,
            'covered_subsystems': len({x.subsystem_id for x in rows}), 'status_counts': status_counts,
            'project_counts': [{'name': name, 'value': value} for name, value in project_counts.most_common()],
            'execution_counts': [{'name': name, 'value': value} for name, value in execution_counts.items()],
            'trend_granularity': granularity, 'trend': trend,
            'items': [wkd_out(x) for x in sorted(rows, key=lambda x: x.updated_at, reverse=True)]}


@router.get('/statistics/export', summary='按相同条件导出完整统计明细 CSV（所有已登录用户）')
def export_statistics(filters: dict = Depends(query_arguments), db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows, _, _ = scoped_wkds(db, **filters)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['WKD编号', '标题', '项目', '所属版本', '问题发现版本', '规划解决版本', '机台', '子系统', '责任人',
                     '当前处理人', '执行类型', '活动场景', '措施类型', '执行阶段', '自定义阶段', '状态', '创建时间', '更新时间'])
    for x in rows:
        writer.writerow([x.number, x.title, x.project.name, x.version.number, x.found_version.number if x.found_version else '',
                         x.planned_version.number if x.planned_version else '', ','.join(m.name for m in x.machines),
                         x.subsystem.name, x.owner.username, x.current_handler.username if x.current_handler else '', x.execution_type.value,
                         x.activity_scene, x.measure_type, x.stage.value if x.stage else '', x.custom_stage_name or '',
                         x.status.value, x.created_at, x.updated_at])
    content = '\ufeff' + output.getvalue()
    return StreamingResponse(iter([content.encode('utf-8')]), media_type='text/csv',
                             headers={'Content-Disposition': 'attachment; filename=wmp-statistics.csv'})

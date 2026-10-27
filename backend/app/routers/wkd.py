from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import accessible_project_ids, authorize, current_user
from ..models import Machine, User, Wkd, WkdHistory, WkdStatus
from ..schemas import CreateWkdInput, TransitionInput
from ..services import apply_wkd, audit, commit, diff_snapshots, history, next_wkd_number, payload_audit_snapshot, validate_relations, wkd_audit_snapshot, wkd_out

router = APIRouter(prefix='/wkds', tags=['WKD 全生命周期'])

@router.get('', summary='查询 WKD 列表（搜索、标签及机台、子系统、责任人、阶段、状态多选筛选）')
def list_wkds(project_id: str | None = None, version_id: str | None = None, machine_id: str | None = None,
              subsystem_id: str | None = None, status: WkdStatus | None = None, q: str | None = None,
              machine_ids: list[str] | None = Query(None), subsystem_ids: list[str] | None = Query(None),
              owner_ids: list[str] | None = Query(None), stages: list[str] | None = Query(None),
              statuses: list[WkdStatus] | None = Query(None), tab: str = 'all',
              page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'wkd.view', project_id)
    if tab not in ('all', 'created', 'pending', 'handled'):
        raise HTTPException(422, '未知列表标签')
    base = select(Wkd)
    if project_id:
        base = base.where(Wkd.project_id == project_id)
    else:
        allowed_projects = accessible_project_ids(db, user)
        if allowed_projects is not None:
            base = base.where(Wkd.project_id.in_(allowed_projects))
    if version_id: base = base.where(Wkd.version_id == version_id)
    if subsystem_id: base = base.where(Wkd.subsystem_id == subsystem_id)
    if status: base = base.where(Wkd.status == status)
    if machine_id: base = base.where(Wkd.machines.any(id=machine_id))
    if machine_ids: base = base.where(Wkd.machines.any(Machine.id.in_(machine_ids)))
    if subsystem_ids: base = base.where(Wkd.subsystem_id.in_(subsystem_ids))
    if owner_ids: base = base.where(Wkd.owner_id.in_(owner_ids))
    if statuses: base = base.where(Wkd.status.in_(statuses))
    if stages:
        stage_conditions = []
        stage_values = [item for item in stages if item != 'MANUAL']
        if stage_values: stage_conditions.append(Wkd.stage.in_(stage_values))
        if 'MANUAL' in stages: stage_conditions.append(Wkd.execution_type == 'MANUAL')
        base = base.where(or_(*stage_conditions))
    if q: base = base.where(or_(Wkd.number.ilike(f'%{q}%'), Wkd.title.ilike(f'%{q}%')))

    def with_tab(query, name: str):
        if name == 'created': return query.where(Wkd.owner_id == user.id)
        if name == 'pending': return query.where(Wkd.current_handler_id == user.id)
        if name == 'handled': return query.where(Wkd.id.in_(select(WkdHistory.wkd_id).where(WkdHistory.operator_id == user.id)))
        return query

    tab_counts = {name: len(db.scalars(with_tab(base, name)).unique().all()) for name in ('all', 'created', 'pending', 'handled')}
    query = with_tab(base, tab)
    total = tab_counts[tab]
    items = db.scalars(query.order_by(Wkd.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {'items': [wkd_out(x) for x in items], 'total': total, 'page': page, 'page_size': page_size, 'tab_counts': tab_counts}

def eligible_reviewers(db: Session, project_id: str) -> list[User]:
    from ..models import ProjectMember, Role, RolePermission
    query = (select(User)
             .join(ProjectMember, ProjectMember.user_id == User.id)
             .join(Role, Role.id == ProjectMember.role_id)
             .join(RolePermission, RolePermission.role_id == Role.id)
             .where(ProjectMember.project_id == project_id, RolePermission.permission_code == 'wkd.review', User.is_active.is_(True))
             .distinct().order_by(User.name))
    return list(db.scalars(query).unique().all())

@router.post('', status_code=201, summary='首次创建 WKD，保存完整数据与新建说明')
def create_wkd(payload: CreateWkdInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    authorize(db, user, 'wkd.create', payload.project_id)
    machines = validate_relations(db, payload)
    wkd = Wkd(number=next_wkd_number(db), owner_id=user.id, current_handler=user, status=WkdStatus.NEW_WKD)
    apply_wkd(db, wkd, payload, machines)
    db.add(wkd)
    db.flush()
    history(db, wkd, user, 'CREATE', None, payload.note)
    audit(db, user, 'WKD_CREATE', 'wkd', wkd.id, {'number': wkd.number})
    commit(db)
    return wkd_out(wkd)

@router.get('/reviewers', summary='查询当前项目可指派的软件经理')
def list_reviewers(project_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    try:
        authorize(db, user, 'wkd.submit', project_id)
    except HTTPException:
        authorize(db, user, 'wkd.disable', project_id)
    return [{'id': item.id, 'name': item.name, 'employee_id': item.employee_id, 'email': item.email} for item in eligible_reviewers(db, project_id)]

@router.get('/{wkd_id}', summary='获取 WKD 详情、操作编排和字段属性')
def get_wkd(wkd_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    wkd = db.get(Wkd, wkd_id)
    if not wkd: raise HTTPException(404, 'WKD 不存在')
    authorize(db, user, 'wkd.view', wkd.project_id)
    return wkd_out(wkd)

@router.post('/{wkd_id}/transitions/{action}', summary='状态流转；提交类操作携带完整数据，指派类操作必须传入 manager_id')
def transition(wkd_id: str, action: str, payload: TransitionInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    wkd = db.get(Wkd, wkd_id)
    if not wkd: raise HTTPException(404, 'WKD 不存在')
    from ..lifecycle import RULES, transition_rule
    if action not in RULES: raise HTTPException(404, '未知流转操作')
    rule = transition_rule(action, wkd.status)
    if not rule: raise HTTPException(409, f'{wkd.status.value} 状态不允许执行 {action}')
    target, permission, note_required = rule
    authorize(db, user, permission, wkd.project_id)
    handler_bound = {'submit_verify', 'submit_review', 'approve', 'reject', 'disable', 'confirm_disable', 'reject_disable'}
    if action in handler_bound and not user.is_superuser and wkd.current_handler_id != user.id:
        raise HTTPException(403, '仅当前处理人可以执行该流转操作')
    if payload.lock_version is not None and payload.lock_version != wkd.lock_version:
        raise HTTPException(409, '数据已被他人修改，请刷新')
    if note_required and not payload.note: raise HTTPException(422, '该操作必须填写说明或原因')

    previous = wkd.status
    changes = []
    if action in ('submit_verify', 'submit_review'):
        if not payload.data: raise HTTPException(422, '提交状态流转时必须携带完整 WKD 数据')
        if payload.data.project_id != wkd.project_id or payload.data.version_id != wkd.version_id:
            raise HTTPException(409, '所属项目和所属版本在创建后不可修改')
        machines = validate_relations(db, payload.data)
        before = wkd_audit_snapshot(wkd)
        after = payload_audit_snapshot(db, payload.data, machines)
        apply_wkd(db, wkd, payload.data, machines)
        changes = diff_snapshots(before, after)

    next_handler = None
    if action in ('submit_verify', 'reject'):
        next_handler = db.get(User, wkd.owner_id)
    elif action in ('submit_review', 'request_disable'):
        if not payload.manager_id: raise HTTPException(422, '指派软件经理前必须选择软件经理')
        next_handler = next((item for item in eligible_reviewers(db, wkd.project_id) if item.id == payload.manager_id), None)
        if not next_handler: raise HTTPException(422, '所选用户不是当前项目可指派的软件经理')

    previous_handler_id = wkd.current_handler_id
    previous_handler_name = wkd.current_handler.name if wkd.current_handler else None
    if action in ('disable', 'request_disable'):
        wkd.disabled_from = previous
        wkd.disabled_reason = payload.note
    elif action == 'reject_disable':
        wkd.disabled_from = None
        wkd.disabled_reason = None
    wkd.status = target
    wkd.current_handler = next_handler
    wkd.lock_version += 1
    if previous_handler_id != (next_handler.id if next_handler else None):
        changes.append({'field': 'current_handler', 'label': '当前处理人', 'before': previous_handler_name,
                        'after': next_handler.name if next_handler else None})
    history(db, wkd, user, action.upper(), previous, payload.note, changes=changes)
    audit(db, user, f'WKD_{action.upper()}', 'wkd', wkd.id, {'current_handler_id': next_handler.id if next_handler else None, 'changes': changes})
    commit(db)
    return wkd_out(wkd)

@router.get('/{wkd_id}/history', summary='查询状态流转、属性变更和说明历史', description='每条记录可包含 note 富文本说明，以及 changes 属性变更数组；changes 元素包含 field、label、before、after。')
def get_history(wkd_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    wkd = db.get(Wkd, wkd_id)
    if not wkd: raise HTTPException(404, 'WKD 不存在')
    authorize(db, user, 'wkd.view', wkd.project_id)
    rows = db.scalars(select(WkdHistory).where(WkdHistory.wkd_id == wkd_id).order_by(WkdHistory.created_at.desc())).all()
    return [{'id': x.id, 'action': x.action, 'from_status': x.from_status.value if x.from_status else None,
             'to_status': x.to_status.value, 'note': x.note, 'changes': x.changes or [],
             'operator': x.operator.name, 'created_at': x.created_at} for x in rows]


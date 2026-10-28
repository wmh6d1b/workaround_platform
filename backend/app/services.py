from datetime import date, datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models import AuditLog, BuildArtifact, Machine, User, Version, Wkd, WkdDailySequence, WkdHistory, WkdOperation, WkdStatus

def audit(db: Session, user: User | None, action: str, resource_type: str, resource_id: str | None = None, detail: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=action, resource_type=resource_type, resource_id=resource_id, detail=detail or {}))

def next_wkd_number(db: Session) -> str:
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    today = date.today()
    statement = pg_insert(WkdDailySequence).values(day=today, value=1)
    statement = statement.on_conflict_do_update(index_elements=[WkdDailySequence.day],
        set_={'value': WkdDailySequence.value + 1}).returning(WkdDailySequence.value)
    value = db.scalar(statement)
    if value is None or value > 9999:
        raise HTTPException(409, '当日 WKD 序号已达到上限')
    return f"WKD{today:%Y%m%d}{value:04d}"

def validate_relations(db: Session, payload) -> list[Machine]:
    from .models import ProjectMember, Subsystem
    version = db.get(Version, payload.version_id)
    if not version or version.project_id != payload.project_id:
        raise HTTPException(422, '目标版本不属于所选项目')
    for related_id in (payload.found_version_id, payload.planned_version_id):
        if related_id and (not db.get(Version, related_id) or db.get(Version, related_id).project_id != payload.project_id):
            raise HTTPException(422, '关联版本不属于所选项目')
    subsystem = db.get(Subsystem, payload.subsystem_id)
    if not subsystem or subsystem.project_id != payload.project_id:
        raise HTTPException(422, '子系统不存在或不属于所选项目')
    machines = db.scalars(select(Machine).where(Machine.id.in_(payload.machine_ids))).all()
    if len(machines) != len(set(payload.machine_ids)) or any(x.project_id != payload.project_id for x in machines):
        raise HTTPException(422, '机台不存在或不属于所选项目')
    if payload.owner_id:
        owner = db.get(User, payload.owner_id)
        membership = db.scalar(select(ProjectMember).where(ProjectMember.project_id == payload.project_id, ProjectMember.user_id == payload.owner_id))
        if not owner or not owner.is_active or (not owner.is_superuser and not membership):
            raise HTTPException(422, '责任人不存在、已停用或不是当前项目成员')
    return machines

def apply_wkd(db: Session, wkd: Wkd, payload, machines: list[Machine]) -> None:
    values = payload.model_dump(exclude={'machine_ids', 'operations', 'lock_version', 'owner_id', 'note', 'attachment_ids', 'idempotency_key'})
    for key, value in values.items():
        setattr(wkd, key, value)
    wkd.machines = machines
    wkd.operations = [WkdOperation(position=index + 1, type=item.type, params=item.params) for index, item in enumerate(payload.operations)]

AUDIT_FIELD_LABELS = {
    'title': 'WKD 标题', 'description': '规避措施描述', 'issue_no': '问题单号', 'requirement_no': '需求单号',
    'found_version': '问题发现版本', 'planned_version': '规划解决版本', 'subsystem': '所属子系统',
    'machines': '关联机台', 'execution_type': '执行类型', 'activity_scene': '活动场景',
    'measure_type': '类型', 'remark': '备注', 'stage': '执行阶段', 'custom_stage_name': '自定义阶段名称',
    'operations': '原子操作编排',
}
OPERATION_LABELS = {'UPLOAD_FILE': '上传文件', 'LINUX_COMMAND': 'Linux 命令', 'SCRIPT': 'Python / Shell 脚本'}
STAGE_LABELS = {'pre_upgrade': '升级前', 'post_upgrade': '升级后', 'post_start': '启动后', 'post_init': '初始化后', 'custom': '自定义'}
EXECUTION_LABELS = {'AUTOMATED': '自动化执行', 'MANUAL': '人工操作'}


def operation_audit_params(operation_type: str, params: dict) -> str:
    summary = dict(params)
    if operation_type == 'UPLOAD_FILE':
        summary['files'] = [{'name': item.get('name'), 'size': item.get('size')} for item in params.get('files', [])]
    return '，'.join(f'{key}={value}' for key, value in sorted(summary.items()))


def wkd_audit_snapshot(wkd: Wkd) -> dict:
    stage = wkd.stage.value if wkd.stage else None
    execution_type = wkd.execution_type.value if wkd.execution_type else None
    operations = []
    for index, operation in enumerate(wkd.operations, 1):
        params = operation_audit_params(operation.type.value, operation.params)
        operations.append(f'{index:02d} {OPERATION_LABELS.get(operation.type.value, operation.type.value)} · {params}')
    return {
        'title': wkd.title, 'description': wkd.description, 'issue_no': wkd.issue_no, 'requirement_no': wkd.requirement_no,
        'found_version': wkd.found_version.number if wkd.found_version else None,
        'planned_version': wkd.planned_version.number if wkd.planned_version else None,
        'subsystem': wkd.subsystem.name if wkd.subsystem else None,
        'machines': sorted(machine.name for machine in wkd.machines),
        'execution_type': EXECUTION_LABELS.get(execution_type, execution_type),
        'activity_scene': wkd.activity_scene, 'measure_type': wkd.measure_type, 'remark': wkd.remark,
        'stage': STAGE_LABELS.get(stage, stage), 'custom_stage_name': wkd.custom_stage_name, 'operations': operations,
    }

def payload_audit_snapshot(db: Session, payload, machines: list[Machine]) -> dict:
    from .models import Subsystem
    found_version = db.get(Version, payload.found_version_id) if payload.found_version_id else None
    planned_version = db.get(Version, payload.planned_version_id) if payload.planned_version_id else None
    subsystem = db.get(Subsystem, payload.subsystem_id)
    stage = payload.stage.value if payload.stage else None
    operations = []
    for index, operation in enumerate(payload.operations, 1):
        params = operation_audit_params(operation.type, operation.params)
        operations.append(f'{index:02d} {OPERATION_LABELS.get(operation.type, operation.type)} · {params}')
    return {
        'title': payload.title, 'description': payload.description, 'issue_no': payload.issue_no, 'requirement_no': payload.requirement_no,
        'found_version': found_version.number if found_version else None,
        'planned_version': planned_version.number if planned_version else None,
        'subsystem': subsystem.name if subsystem else None, 'machines': sorted(machine.name for machine in machines),
        'execution_type': EXECUTION_LABELS.get(payload.execution_type.value, payload.execution_type.value),
        'activity_scene': payload.activity_scene, 'measure_type': payload.measure_type, 'remark': payload.remark,
        'stage': STAGE_LABELS.get(stage, stage), 'custom_stage_name': payload.custom_stage_name, 'operations': operations,
    }

def diff_snapshots(before: dict, after: dict) -> list[dict]:
    return [
        {'field': field, 'label': label, 'before': before.get(field), 'after': after.get(field)}
        for field, label in AUDIT_FIELD_LABELS.items() if before.get(field) != after.get(field)
    ]

def history(db: Session, wkd: Wkd, user: User, action: str, from_status: WkdStatus | None,
            note: str | None = None, changes: list[dict] | None = None) -> None:
    db.add(WkdHistory(wkd_id=wkd.id, action=action, from_status=from_status, to_status=wkd.status,
                      note=note, changes=changes or [], operator_id=user.id))

def commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        message = str(exc.orig)
        if 'custom_stage_name' in message:
            raise HTTPException(409, '当前版本下已存在同名自定义阶段') from None
        if 'issue_or_requirement' in message or 'found_version_required' in message:
            raise HTTPException(422, '问题单号、需求单号或问题发现版本不符合填写规则') from None
        raise HTTPException(409, '数据冲突，请刷新后重试') from None

def wkd_out(wkd: Wkd) -> dict:
    return {
        'id': wkd.id, 'number': wkd.number, 'title': wkd.title, 'description': wkd.description,
        'issue_no': wkd.issue_no, 'requirement_no': wkd.requirement_no,
        'project_id': wkd.project_id, 'project': wkd.project.name,
        'version_id': wkd.version_id, 'version': wkd.version.number,
        'found_version_id': wkd.found_version_id, 'found_version': wkd.found_version.number if wkd.found_version else None,
        'planned_version_id': wkd.planned_version_id, 'planned_version': wkd.planned_version.number if wkd.planned_version else None,
        'subsystem_id': wkd.subsystem_id, 'subsystem': wkd.subsystem.name,
        'owner_id': wkd.owner_id, 'owner': wkd.owner.username,
        'current_handler_id': wkd.current_handler_id, 'current_handler': wkd.current_handler.username if wkd.current_handler else None,
        'machine_ids': [x.id for x in wkd.machines], 'machines': [{'id': x.id, 'name': x.name} for x in wkd.machines],
        'execution_type': wkd.execution_type.value, 'activity_scene': wkd.activity_scene, 'measure_type': wkd.measure_type,
        'remark': wkd.remark, 'status': wkd.status.value, 'stage': wkd.stage.value if wkd.stage else None,
        'custom_stage_name': wkd.custom_stage_name, 'lock_version': wkd.lock_version,
        'disabled_reason': wkd.disabled_reason, 'disabled_from': wkd.disabled_from.value if wkd.disabled_from else None,
        'operations': [{'id': x.id, 'position': x.position, 'type': x.type.value, 'params': x.params} for x in wkd.operations],
        'created_at': wkd.created_at, 'updated_at': wkd.updated_at,
    }

def artifact_out(artifact: BuildArtifact) -> dict:
    return {'id': artifact.id, 'number': artifact.number, 'filename': artifact.filename, 'project_id': artifact.project_id,
            'machine_id': artifact.machine_id, 'type': artifact.type.value, 'size': artifact.size, 'sha256': artifact.sha256,
            'builder_id': artifact.builder_id, 'created_at': artifact.created_at,
            'items': [{'wkd_id': x.wkd_id, 'position': x.position, 'snapshot': x.snapshot} for x in artifact.items]}

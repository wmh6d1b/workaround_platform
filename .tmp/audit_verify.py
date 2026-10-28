"""Independent, mock-based checks for the v1.6 design/code review.
Does not connect to PostgreSQL/RustFS and does not modify business data.
"""
import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.attachment_service import create_session
from app.deps import accessible_project_ids, authorize, user_permissions
from app.models import ExecutionType, OperationType, Stage, WkdStatus
from app.routers.statistics import export_statistics
from app.schemas import UploadSessionInput, WkdInput
from app.services import validate_relations, wkd_out


def empty_unique_result():
    result = Mock()
    result.unique.return_value.all.return_value = []
    result.all.return_value = []
    return result


def check_global_role_is_inert():
    role = SimpleNamespace(permissions=[SimpleNamespace(code='wkd.view')])
    user = SimpleNamespace(id='global-user', is_superuser=False, global_role=role)
    db = Mock()
    db.scalars.return_value = empty_unique_result()
    try:
        authorize(db, user, 'wkd.view', 'project-without-membership')
        authorized = True
    except HTTPException as exc:
        authorized = False
        assert exc.status_code == 403
    projects = accessible_project_ids(db, user)
    permissions = user_permissions(db, user, 'project-without-membership')
    assert not authorized and projects == set() and permissions == set()
    print('CONFIRMED global role: assigned role is ignored; project access remains empty')


def check_terminal_attachment_session():
    user = SimpleNamespace(id='uploader')
    accepted = []
    for status in (WkdStatus.APPROVED, WkdStatus.DISABLE_CONFIRM, WkdStatus.DISABLED):
        wkd = SimpleNamespace(id=f'wkd-{status.value}', project_id='p1', status=status)
        db = Mock()
        db.get.return_value = wkd
        with patch('app.attachment_service.authorize'):
            session = create_session(db, user, UploadSessionInput(project_id='p1', wkd_id=wkd.id))
        assert session.wkd_id == wkd.id
        accepted.append(status.value)
    print('CONFIRMED attachments: upload sessions accepted for ' + ', '.join(accepted))


def check_inactive_business_relations():
    payload = SimpleNamespace(project_id='p1', version_id='v1', found_version_id=None,
                              planned_version_id=None, subsystem_id='s1', machine_ids=['m1'], owner_id=None)
    version = SimpleNamespace(id='v1', project_id='p1', status='ARCHIVED')
    subsystem = SimpleNamespace(id='s1', project_id='p1', status='DISABLED')
    machine = SimpleNamespace(id='m1', project_id='p1', status='STOPPED')
    db = Mock()
    db.get.side_effect = lambda model, _id: version if model.__name__ == 'Version' else subsystem
    result = Mock()
    result.all.return_value = [machine]
    db.scalars.return_value = result
    machines = validate_relations(db, payload)
    assert machines == [machine]
    print('CONFIRMED business status: ARCHIVED version + DISABLED subsystem + STOPPED machine accepted')


def check_list_payload_contains_operation_file():
    raw = b'x' * (1024 * 1024)
    encoded = base64.b64encode(raw).decode()
    wkd = SimpleNamespace(
        id='w1', number='WKD1', title='title', description='description', issue_no=None,
        requirement_no='REQ-1', project_id='p1', project=SimpleNamespace(name='project'),
        version_id='v1', version=SimpleNamespace(number='V1'), found_version_id=None, found_version=None,
        planned_version_id=None, planned_version=None, subsystem_id='s1', subsystem=SimpleNamespace(name='subsystem'),
        owner_id='u1', owner=SimpleNamespace(username='owner'), current_handler_id=None, current_handler=None,
        machines=[], execution_type=ExecutionType.AUTOMATED, activity_scene='常规版本升级',
        measure_type='事前规避措施', remark=None, status=WkdStatus.VERIFY, stage=Stage.POST_START,
        custom_stage_name=None, lock_version=1, disabled_reason=None, disabled_from=None,
        operations=[SimpleNamespace(id='op1', position=1, type=OperationType.UPLOAD_FILE,
                    params={'target_path': '/tmp', 'files': [{'name': 'x.bin', 'content': encoded, 'encoding': 'base64'}]})],
        created_at=None, updated_at=None,
    )
    output = wkd_out(wkd)
    assert output['operations'][0]['params']['files'][0]['content'] == encoded
    serialized_size = len(json.dumps(output))
    assert serialized_size > len(raw)
    print(f'CONFIRMED list DTO: 1 MiB operation file is returned as Base64; JSON size={serialized_size:,} bytes')


def check_operation_validation_gaps():
    base = dict(title='title', description='description', requirement_no='REQ-1', project_id='p1',
                version_id='v1', subsystem_id='s1', machine_ids=['m1'], execution_type=ExecutionType.AUTOMATED,
                activity_scene='常规版本升级', measure_type='事前规避措施', stage=Stage.POST_START,
                custom_stage_name='unexpected-on-standard-stage',
                operations=[{'type': 'LINUX_COMMAND', 'params': {'command': 'true', 'timeout': 'not-a-number', 'exit_code': 'not-an-integer'}}])
    result = WkdInput(**base)
    assert result.custom_stage_name == 'unexpected-on-standard-stage'
    assert result.operations[0].params['timeout'] == 'not-a-number'
    print('CONFIRMED validation: standard stage accepts custom name; invalid timeout/exit code reaches build/runtime')


def check_csv_formula_passthrough():
    dangerous = '=1+1'
    row = SimpleNamespace(
        number='WKD1', title=dangerous, project=SimpleNamespace(name='project'),
        version=SimpleNamespace(number='V1'), found_version=None, planned_version=None,
        machines=[], subsystem=SimpleNamespace(name='subsystem'), owner=SimpleNamespace(username='owner'),
        current_handler=None, execution_type=ExecutionType.MANUAL, activity_scene='常规版本升级',
        measure_type='事前规避措施', stage=None, custom_stage_name=None, status=WkdStatus.NEW_WKD,
        created_at=None, updated_at=None,
    )
    with patch('app.routers.statistics.scoped_wkds', return_value=([row], None, None)):
        response = export_statistics({}, Mock(), SimpleNamespace(id='u1'))
    async def read_body():
        return b''.join([chunk async for chunk in response.body_iterator]).decode('utf-8-sig')
    content = asyncio.run(read_body())
    assert dangerous in content
    print('CONFIRMED CSV export: formula-leading title is exported without neutralization')


if __name__ == '__main__':
    check_global_role_is_inert()
    check_terminal_attachment_session()
    check_inactive_business_relations()
    check_list_payload_contains_operation_file()
    check_operation_validation_gaps()
    check_csv_formula_passthrough()
    print('AUDIT CHECKS COMPLETE')

import os
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.attachment_service import authorize_wkd_upload, owned_session
from app.config import Settings, validate_production_settings
from app.deps import accessible_project_ids, user_permissions
from app.models import ExecutionType, Machine, WkdStatus
from app.routers.auth import login
from app.routers.statistics import statistics, xlsx_safe
from app.routers.wkd import transition
from app.schemas import BuildInput, EntityInput, LoginInput, TransitionInput, WkdInput
from app.seed import PERMISSIONS, seed
from app.services import artifact_out, wkd_list_out


class Rows:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items

    def unique(self):
        return self


class GlobalRoleFallbackTests(unittest.TestCase):
    def setUp(self):
        self.global_role = SimpleNamespace(permissions=[SimpleNamespace(code='wkd.review')])
        self.user = SimpleNamespace(id='user-1', is_superuser=False, global_role_id='role-global', global_role=self.global_role)

    def test_project_role_takes_precedence_over_global_role(self):
        member = SimpleNamespace(role=SimpleNamespace(permissions=[SimpleNamespace(code='wkd.view')]))
        db = Mock()
        db.scalars.return_value = Rows([member])
        self.assertEqual(user_permissions(db, self.user, 'project-1'), {'wkd.view'})

    def test_global_role_applies_without_project_membership(self):
        db = Mock()
        db.scalars.return_value = Rows([])
        self.assertEqual(user_permissions(db, self.user, 'project-1'), {'wkd.review'})
        self.assertIsNone(accessible_project_ids(db, self.user))

    def test_unscoped_permissions_merge_both_sources(self):
        member = SimpleNamespace(role=SimpleNamespace(permissions=[SimpleNamespace(code='wkd.view')]))
        db = Mock()
        db.scalars.return_value = Rows([member])
        self.assertEqual(user_permissions(db, self.user), {'wkd.view', 'wkd.review'})


class AttachmentStateBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.user = SimpleNamespace(id='user-1', is_superuser=False)
        self.wkd = SimpleNamespace(id='wkd-1', project_id='project-1', current_handler_id='user-1', status=WkdStatus.NEW_WKD)

    @patch('app.attachment_service.ensure_operational_project')
    @patch('app.attachment_service.authorize')
    def test_approved_allows_upload_without_edit_permission(self, authorize, _operational):
        self.wkd.status = WkdStatus.APPROVED
        authorize_wkd_upload(self.db, self.user, self.wkd)
        authorize.assert_called_once_with(self.db, self.user, 'files.upload', 'project-1')

    @patch('app.attachment_service.ensure_operational_project')
    @patch('app.attachment_service.authorize')
    def test_review_confirm_disable_and_disabled_reject_upload(self, authorize, _operational):
        for status in (WkdStatus.REVIEW, WkdStatus.DISABLE_CONFIRM, WkdStatus.DISABLED):
            with self.subTest(status=status), self.assertRaises(HTTPException) as raised:
                self.wkd.status = status
                authorize_wkd_upload(self.db, self.user, self.wkd)
            self.assertEqual(raised.exception.status_code, 409)
        authorize.assert_not_called()

    @patch('app.attachment_service.ensure_operational_project')
    @patch('app.attachment_service.authorize')
    def test_old_session_is_revalidated_and_wkd_is_locked(self, authorize, _operational):
        session = SimpleNamespace(id='session-1', owner_id='user-1', project_id='project-1', wkd_id='wkd-1',
                                  status='OPEN', expires_at=datetime.utcnow() + timedelta(hours=1))
        self.wkd.status = WkdStatus.REVIEW
        self.db.get.return_value = session
        self.db.scalar.return_value = self.wkd
        with self.assertRaises(HTTPException) as raised:
            owned_session(self.db, self.user, session.id)
        self.assertEqual(raised.exception.status_code, 409)
        self.db.get.assert_called_once_with(unittest.mock.ANY, session.id)
        self.db.scalar.assert_called_once()


class ConcurrencyAndConfigurationTests(unittest.TestCase):
    def test_transition_lock_version_is_required_and_positive(self):
        with self.assertRaises(ValidationError):
            TransitionInput()
        with self.assertRaises(ValidationError):
            TransitionInput(lock_version=0)

    def test_transition_loads_wkd_with_row_lock(self):
        wkd = SimpleNamespace(status=WkdStatus.NEW_WKD)
        db = Mock()
        db.scalar.return_value = wkd
        with self.assertRaises(HTTPException):
            transition('wkd-1', 'not-an-action', TransitionInput(lock_version=1), db, SimpleNamespace())
        db.scalar.assert_called_once()

    def test_production_rejects_default_credentials(self):
        with self.assertRaisesRegex(RuntimeError, '生产环境配置校验失败'):
            validate_production_settings(Settings(environment='production'))

    def test_production_accepts_explicit_strong_credentials(self):
        settings = Settings(environment='production', jwt_secret='x' * 32, bootstrap_admin_password='a-strong-password',
                            database_url='postgresql+psycopg://wmp:private@db:5432/wmp',
                            rustfs_access_key='private-access', rustfs_secret_key='private-secret')
        validate_production_settings(settings)


class InputAndExportRegressionTests(unittest.TestCase):
    def base_wkd(self):
        return dict(title='测试', description='测试描述', requirement_no='REQ-1', project_id='project-1', version_id='version-1',
                    subsystem_id='subsystem-1', machine_ids=['machine-1'], execution_type='AUTOMATED',
                    activity_scene='常规版本升级', measure_type='事前规避措施', stage='post_start', custom_stage_name='stale',
                    operations=[{'type': 'LINUX_COMMAND', 'params': {'command': 'true', 'workdir': '/tmp', 'timeout': '30', 'exit_code': '0'}}])

    def test_normal_stage_clears_custom_name_and_normalizes_numbers(self):
        result = WkdInput(**self.base_wkd())
        self.assertIsNone(result.custom_stage_name)
        self.assertEqual(result.operations[0].params['timeout'], 30)
        self.assertEqual(result.operations[0].params['exit_code'], 0)

    def test_unsafe_operation_parameters_are_rejected(self):
        for changes in ({'workdir': '../tmp'}, {'timeout': 0}, {'timeout': 86401}, {'exit_code': 256}):
            payload = self.base_wkd()
            payload['operations'][0]['params'].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                WkdInput(**payload)

    def test_build_rejects_duplicate_wkd_ids(self):
        with self.assertRaises(ValidationError):
            BuildInput(project_id='project-1', machine_id='machine-1', wkd_ids=['wkd-1', 'wkd-1'])

    def test_xlsx_formula_prefixes_are_neutralized(self):
        for value in ('=1+1', '+CMD', '-2+3', '@SUM(A1)', '  =HYPERLINK("x")', '\t=1'):
            with self.subTest(value=value):
                self.assertTrue(xlsx_safe(value).startswith("'"))
        self.assertEqual(xlsx_safe('正常文本'), '正常文本')


class LightweightReadModelTests(unittest.TestCase):
    def test_list_output_does_not_access_operations(self):
        wkd = SimpleNamespace(id='wkd-1', number='WKD1', title='标题', description='描述', issue_no=None, requirement_no='REQ',
            project_id='project-1', project=SimpleNamespace(name='项目'), version_id='version-1', version=SimpleNamespace(number='V1'),
            found_version_id=None, found_version=None, planned_version_id=None, planned_version=None,
            subsystem_id='subsystem-1', subsystem=SimpleNamespace(name='子系统'), owner_id='user-1', owner=SimpleNamespace(username='用户'),
            current_handler_id=None, current_handler=None, machines=[], execution_type=ExecutionType.MANUAL,
            activity_scene='常规版本升级', measure_type='事前规避措施', remark=None, status=WkdStatus.APPROVED,
            stage=None, custom_stage_name=None, lock_version=1, disabled_reason=None, disabled_from=None,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        result = wkd_list_out(wkd)
        self.assertNotIn('operations', result)

    def test_artifact_summary_does_not_access_snapshot(self):
        artifact = SimpleNamespace(id='artifact-1', number='BUILD1', filename='build.tar.gz', project_id='project-1',
            machine_id='machine-1', type=SimpleNamespace(value='DEBUG'), size=10, sha256='abc', builder_id='user-1',
            created_at=datetime.utcnow(), items=[SimpleNamespace(wkd_id='wkd-1', position=1)])
        result = artifact_out(artifact, include_snapshots=False)
        self.assertEqual(result['items'], [{'wkd_id': 'wkd-1', 'position': 1}])

    @patch('app.routers.statistics.scoped_wkds')
    def test_approval_trend_uses_event_period_not_creation_period(self, scoped):
        start, end = date.today() - timedelta(days=13), date.today()
        scoped.side_effect = [([], start, end), ([SimpleNamespace(id='old-wkd')], start, end)]
        approval = SimpleNamespace(wkd_id='old-wkd', created_at=datetime.now(), action='APPROVE')
        db = Mock()
        db.scalars.return_value = Rows([approval])
        result = statistics({'scope': 'global'}, db, SimpleNamespace())
        self.assertEqual(sum(item['approved'] for item in result['trend']), 1)
        self.assertIsNone(scoped.call_args_list[1].kwargs['start_date'])
        self.assertIsNone(scoped.call_args_list[1].kwargs['end_date'])


class ResourceStatusValidationTests(unittest.TestCase):
    @patch('app.routers.admin.commit')
    @patch('app.routers.admin.audit')
    @patch('app.routers.admin.authorize')
    def test_machine_accepts_running_and_maintenance(self, _authorize, _audit, _commit):
        from app.routers.admin import create_business
        db = Mock()
        for status in ('RUNNING', 'MAINTENANCE', 'STOPPED'):
            result = create_business('machines', EntityInput(name='机台一', project_id='project-1', status=status), db, SimpleNamespace())
            self.assertEqual(result['status'], status)

    @patch('app.routers.admin.authorize')
    def test_machine_rejects_status_of_other_resources(self, _authorize):
        from app.routers.admin import create_business, update_business
        db = Mock()
        for status in ('ENABLED', 'DEVELOPING', 'RELEASED'):
            with self.subTest(status=status), self.assertRaises(HTTPException) as raised:
                create_business('machines', EntityInput(name='机台一', project_id='project-1', status=status), db, SimpleNamespace())
            self.assertEqual(raised.exception.status_code, 422)
        item = Machine(project_id='project-1', name='机台一')
        db.get.side_effect = [item, SimpleNamespace(code='P1', status='ENABLED')]
        with self.assertRaises(HTTPException) as raised:
            update_business('machines', item.id, EntityInput(name='机台一', project_id='project-1', status='DEVELOPING'), db, SimpleNamespace())
        self.assertEqual(raised.exception.status_code, 422)
        self.assertNotEqual(item.status, 'DEVELOPING')

    @patch('app.routers.admin.authorize')
    def test_version_and_project_status_sets_are_separate(self, _authorize):
        from app.routers.admin import create_business
        db = Mock()
        with self.assertRaises(HTTPException) as raised:
            create_business('versions', EntityInput(name='V1.0.0', project_id='project-1', status='RUNNING'), db, SimpleNamespace())
        self.assertEqual(raised.exception.status_code, 422)
        with self.assertRaises(HTTPException) as raised:
            create_business('projects', EntityInput(name='项目一', code='P1', status='RUNNING'), db, SimpleNamespace(id='admin', is_superuser=True))
        self.assertEqual(raised.exception.status_code, 422)


class AccountSafetyTests(unittest.TestCase):
    def tearDown(self):
        from app.config import get_settings
        get_settings.cache_clear()

    def test_duplicate_username_requires_employee_id(self):
        db = Mock()
        db.scalar.return_value = None
        db.scalars.return_value = Rows([SimpleNamespace(), SimpleNamespace()])
        with self.assertRaises(HTTPException) as raised:
            login(LoginInput(username='duplicate', password='secret'), db)
        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn('工号', raised.exception.detail)

    def test_same_name_normal_user_is_not_promoted(self):
        from app.config import get_settings
        from app.models import Permission
        get_settings.cache_clear()
        permissions = [Permission(code=code, module=code.split('.')[0], description=description)
                       for code, description in PERMISSIONS.items()]
        ordinary = SimpleNamespace(id='ordinary', is_superuser=False)
        db = Mock()
        db.get.side_effect = lambda model, code: next(item for item in permissions if item.code == code)
        db.scalars.side_effect = [Rows(permissions), Rows([])]
        db.scalar.side_effect = [None, ordinary]
        with patch.dict(os.environ, {'SEED_DEMO_DATA': 'false'}):
            get_settings.cache_clear()
            with self.assertRaisesRegex(RuntimeError, '不会自动提权'):
                seed(db)
        self.assertFalse(ordinary.is_superuser)


if __name__ == '__main__':
    unittest.main()

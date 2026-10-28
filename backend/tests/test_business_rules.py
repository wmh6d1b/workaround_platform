import unittest
from types import SimpleNamespace
from pydantic import ValidationError
from app.lifecycle import transition_rule
from app.models import ExecutionType, Stage, WkdStatus
from app.schemas import StateNoteInput, TransitionInput, WkdInput
from app.security import hash_password, verify_password
from app.services import apply_wkd, diff_snapshots

BASE = dict(title='测试 WKD', description='规避措施描述', requirement_no='REQ-1', project_id='p1', version_id='v1',
            subsystem_id='s1', machine_ids=['m1'], execution_type=ExecutionType.MANUAL,
            activity_scene='常规版本升级', measure_type='事前规避措施')

class WkdInputTests(unittest.TestCase):
    def test_manual_clears_operations_and_stage(self):
        payload = WkdInput(**BASE, stage=Stage.POST_START)
        self.assertIsNone(payload.stage)
        self.assertEqual(payload.operations, [])

    def test_automated_requires_stage_and_operation(self):
        with self.assertRaises(ValidationError):
            WkdInput(**{**BASE, 'execution_type': ExecutionType.AUTOMATED})

    def test_custom_stage_requires_name(self):
        with self.assertRaises(ValidationError):
            WkdInput(**{**BASE, 'execution_type': ExecutionType.AUTOMATED, 'stage': Stage.CUSTOM,
                        'operations': [{'type': 'LINUX_COMMAND', 'params': {'command': 'true'}}]})

    def test_issue_requires_found_version(self):
        with self.assertRaises(ValidationError):
            WkdInput(**{**BASE, 'issue_no': 'BUG-1'})

    def test_issue_or_requirement_required(self):
        data = {**BASE, 'requirement_no': None}
        with self.assertRaises(ValidationError):
            WkdInput(**data)

    def test_blank_issue_and_requirement_are_rejected(self):
        with self.assertRaises(ValidationError):
            WkdInput(**{**BASE, 'requirement_no': '   ', 'issue_no': '  '})

    def test_linux_environment_variables_are_rejected(self):
        with self.assertRaises(ValidationError):
            WkdInput(**{**BASE, 'execution_type': ExecutionType.AUTOMATED, 'stage': Stage.PRE_UPGRADE,
                        'operations': [{'type': 'LINUX_COMMAND', 'params': {'command': 'true', 'env': {}}}]})

    def test_upload_operation_supports_multiple_files(self):
        result = WkdInput(**{**BASE, 'execution_type': ExecutionType.AUTOMATED, 'stage': Stage.POST_START,
                            'operations': [{'type': 'UPLOAD_FILE', 'params': {'target_path': '/root/temp', 'permission': '0644',
                                'files': [{'name': 'hello.py', 'content': 'print("hello")'}, {'name': 'world.py', 'content': 'print("world")'}]}}]})
        self.assertEqual(len(result.operations[0].params['files']), 2)

    def test_upload_operation_validates_base64_binary_content(self):
        data = {**BASE, 'execution_type': ExecutionType.AUTOMATED, 'stage': Stage.POST_START,
                'operations': [{'type': 'UPLOAD_FILE', 'params': {'target_path': '/root/temp',
                    'files': [{'name': 'payload.bin', 'content': 'AAECAwQ=', 'encoding': 'base64'}]}}]}
        result = WkdInput(**data)
        self.assertEqual(result.operations[0].params['files'][0]['size'], 5)
        data['operations'][0]['params']['files'][0]['content'] = 'not base64'
        with self.assertRaises(ValidationError):
            WkdInput(**data)

    def test_upload_operation_rejects_missing_or_unsafe_files(self):
        for files in ([], [{'name': '../hello.py', 'content': 'bad'}], [{'name': 'a.py', 'content': ''}, {'name': 'a.py', 'content': ''}]):
            with self.subTest(files=files), self.assertRaises(ValidationError):
                WkdInput(**{**BASE, 'execution_type': ExecutionType.AUTOMATED, 'stage': Stage.POST_START,
                            'operations': [{'type': 'UPLOAD_FILE', 'params': {'target_path': '/root/temp', 'files': files}}]})

    def test_empty_operation_parameters_are_rejected(self):
        for operation_type in ('UPLOAD_FILE', 'LINUX_COMMAND', 'SCRIPT'):
            with self.subTest(operation_type=operation_type), self.assertRaises(ValidationError):
                WkdInput(**{**BASE, 'execution_type': ExecutionType.AUTOMATED, 'stage': Stage.PRE_UPGRADE,
                            'operations': [{'type': operation_type, 'params': {}}]})

class InputValidationTests(unittest.TestCase):
    def test_transition_note_is_trimmed(self):
        self.assertIsNone(TransitionInput(note='   ').note)
        self.assertEqual(TransitionInput(note='  审核通过  ').note, '审核通过')

    def test_blank_state_note_is_rejected(self):
        with self.assertRaises(ValidationError):
            StateNoteInput(content='   ')
        self.assertEqual(StateNoteInput(content='  已自验证  ').content, '已自验证')

    def test_review_manager_id_is_trimmed(self):
        self.assertIsNone(TransitionInput(manager_id='   ').manager_id)
        self.assertEqual(TransitionInput(manager_id='  manager-1  ').manager_id, 'manager-1')

    def test_transition_can_carry_complete_wkd_data(self):
        result = TransitionInput(data={**BASE, 'title': '流转时提交的完整标题'}, note='自验证完成')
        self.assertEqual(result.data.title, '流转时提交的完整标题')
        self.assertEqual(result.note, '自验证完成')

class RichTextTests(unittest.TestCase):
    def test_dangerous_html_is_removed(self):
        result = StateNoteInput(content='<p onclick="alert(1)">安全</p><script>alert(1)</script>')
        self.assertEqual(result.content, '<p>安全</p>')

    def test_color_and_pasted_image_are_preserved(self):
        image = 'data:image/png;base64,iVBORw0KGgo='
        result = StateNoteInput(content=f'<span style="color:#d92d20;position:fixed">红色</span><img src="{image}" onerror="alert(1)">')
        self.assertIn('style="color:#d92d20"', result.content)
        self.assertIn(f'src="{image}"', result.content)
        self.assertNotIn('onerror', result.content)
        self.assertNotIn('position', result.content)

    def test_empty_html_is_rejected(self):
        with self.assertRaises(ValidationError):
            StateNoteInput(content='<p><br></p>')

class OwnerTests(unittest.TestCase):
    def test_owner_cannot_be_changed_when_saving(self):
        payload = WkdInput(**{**BASE, 'owner_id': 'another-user'})
        wkd = SimpleNamespace(owner_id='creator')
        apply_wkd(None, wkd, payload, [])
        self.assertEqual(wkd.owner_id, 'creator')

class PropertyHistoryTests(unittest.TestCase):
    def test_field_changes_include_before_and_after_values(self):
        before = {'title': '旧标题', 'machines': ['AQ-2000'], 'stage': '启动后'}
        after = {'title': '新标题', 'machines': ['AQ-2000', 'AQ-3000'], 'stage': '启动后'}
        changes = diff_snapshots(before, after)
        self.assertEqual([item['field'] for item in changes], ['title', 'machines'])
        self.assertEqual(changes[0]['label'], 'WKD 标题')
        self.assertEqual(changes[0]['before'], '旧标题')
        self.assertEqual(changes[0]['after'], '新标题')

    def test_unchanged_properties_produce_no_history_changes(self):
        snapshot = {'title': '标题', 'operations': [], 'remark': None}
        self.assertEqual(diff_snapshots(snapshot, snapshot.copy()), [])

class LifecycleTests(unittest.TestCase):
    def test_happy_path(self):
        target, _, _ = transition_rule('submit_verify', WkdStatus.NEW_WKD)
        self.assertEqual(target, WkdStatus.VERIFY)
        target, _, _ = transition_rule('submit_review', WkdStatus.VERIFY)
        self.assertEqual(target, WkdStatus.REVIEW)
        target, _, required = transition_rule('approve', WkdStatus.REVIEW)
        self.assertEqual(target, WkdStatus.APPROVED)
        self.assertTrue(required)

    def test_reject_returns_to_verify(self):
        self.assertEqual(transition_rule('reject', WkdStatus.REVIEW)[0], WkdStatus.VERIFY)

    def test_review_cannot_be_disabled(self):
        self.assertIsNone(transition_rule('disable', WkdStatus.REVIEW))

    def test_approved_must_enter_disable_confirmation(self):
        self.assertIsNone(transition_rule('disable', WkdStatus.APPROVED))
        target, permission, required = transition_rule('request_disable', WkdStatus.APPROVED)
        self.assertEqual(target, WkdStatus.DISABLE_CONFIRM)
        self.assertEqual(permission, 'wkd.disable')
        self.assertTrue(required)

    def test_confirm_disable_is_independent_from_review(self):
        self.assertIsNone(transition_rule('approve', WkdStatus.DISABLE_CONFIRM))
        self.assertIsNone(transition_rule('reject', WkdStatus.DISABLE_CONFIRM))
        self.assertEqual(transition_rule('confirm_disable', WkdStatus.DISABLE_CONFIRM)[0], WkdStatus.DISABLED)
        self.assertEqual(transition_rule('reject_disable', WkdStatus.DISABLE_CONFIRM)[0], WkdStatus.APPROVED)

    def test_disabled_is_terminal(self):
        for action in ('submit_verify', 'submit_review', 'approve', 'reject', 'request_disable', 'confirm_disable', 'reject_disable', 'disable'):
            self.assertIsNone(transition_rule(action, WkdStatus.DISABLED))

    def test_approved_cannot_return_to_verify(self):
        self.assertIsNone(transition_rule('reject', WkdStatus.APPROVED))

class SecurityTests(unittest.TestCase):
    def test_password_hash_roundtrip(self):
        stored = hash_password('secret')
        self.assertTrue(verify_password('secret', stored))
        self.assertFalse(verify_password('wrong', stored))

if __name__ == '__main__':
    unittest.main()

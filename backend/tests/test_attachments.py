import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.attachment_service import (
    cleanup_expired_attachments,
    complete_upload,
    create_session,
    validate_binding_rows,
)
from app.models import ExecutionType
from app.routers.wkd import create_wkd
from app.schemas import CreateWkdInput, SessionUploadCompleteInput, SessionUploadInput, UploadSessionInput

BASE = dict(title='测试 WKD', description='规避措施描述', requirement_no='REQ-1', project_id='p1', version_id='v1',
            subsystem_id='s1', machine_ids=['m1'], execution_type=ExecutionType.MANUAL,
            activity_scene='常规版本升级', measure_type='事前规避措施')


def ready_attachment(**changes):
    session = SimpleNamespace(project_id='p1', wkd_id=None, status='OPEN',
        expires_at=datetime.utcnow() + timedelta(hours=1))
    values = dict(id='a1', uploader_id='u1', wkd_id=None, status='READY', original_filename='a.txt', session=session)
    values.update(changes)
    return SimpleNamespace(**values)


class UploadInputTests(unittest.TestCase):
    def test_create_wkd_accepts_explicit_attachments_and_idempotency_key(self):
        result = CreateWkdInput(**BASE, attachment_ids=['a1', 'a2'], idempotency_key='request-1234')
        self.assertEqual(result.attachment_ids, ['a1', 'a2'])

    def test_frontend_content_hash_idempotency_key_is_accepted(self):
        # 与前端 creationIdempotencyKey() 的生成格式保持契约一致：create-{16进制哈希}
        key = 'create-' + 'a1b2c3d4e5f60718'
        result = CreateWkdInput(**BASE, idempotency_key=key)
        self.assertEqual(result.idempotency_key, key)

    def test_idempotency_key_rejects_uuid_concatenation_over_64_chars(self):
        # 防回归：不得把用户/项目 UUID 拼进幂等键（超长且含非法结构，v1.8 曾因此无法创建 WKD）
        with self.assertRaises(ValidationError):
            CreateWkdInput(**BASE, idempotency_key='create-' + 'u' * 36 + '-' + 'p' * 36 + '-' + 'h' * 16)

    def test_create_wkd_rejects_duplicate_attachment_ids(self):
        with self.assertRaises(ValidationError):
            CreateWkdInput(**BASE, attachment_ids=['a1', 'a1'])

    def test_upload_filename_must_not_contain_path_or_control_characters(self):
        for filename in ('../a.txt', '/tmp/a.txt', 'a\\b.txt', 'a\n.txt'):
            with self.subTest(filename=filename), self.assertRaises(ValidationError):
                SessionUploadInput(filename=filename, size=1)

    def test_completion_checksum_must_be_sha256(self):
        with self.assertRaises(ValidationError):
            SessionUploadCompleteInput(sha256='not-a-sha256')


class AttachmentBindingTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id='u1')
        self.wkd = SimpleNamespace(id='w1', project_id='p1')

    def test_ready_owned_same_project_attachment_can_be_bound(self):
        validate_binding_rows([ready_attachment()], ['a1'], self.user, self.wkd)

    def test_other_users_or_unfinished_attachments_cannot_be_bound(self):
        for item in (ready_attachment(uploader_id='u2'), ready_attachment(status='UPLOADING')):
            with self.subTest(item=item), self.assertRaises(HTTPException) as raised:
                validate_binding_rows([item], ['a1'], self.user, self.wkd)
            self.assertEqual(raised.exception.status_code, 409)

    def test_cross_project_or_bound_attachments_cannot_be_bound(self):
        cross_project = ready_attachment()
        cross_project.session.project_id = 'p2'
        for item in (cross_project, ready_attachment(wkd_id='other-wkd')):
            with self.subTest(item=item), self.assertRaises(HTTPException):
                validate_binding_rows([item], ['a1'], self.user, self.wkd)

    def test_expired_upload_session_cannot_be_bound(self):
        item = ready_attachment()
        item.session.expires_at = datetime.utcnow() - timedelta(seconds=1)
        with self.assertRaises(HTTPException) as raised:
            validate_binding_rows([item], ['a1'], self.user, self.wkd)
        self.assertEqual(raised.exception.status_code, 410)

    def test_missing_attachment_is_rejected(self):
        with self.assertRaises(HTTPException) as raised:
            validate_binding_rows([], ['a1'], self.user, self.wkd)
        self.assertEqual(raised.exception.status_code, 422)


class UploadCompletionTests(unittest.TestCase):
    def settings(self):
        return SimpleNamespace(attachment_multipart_part_size=16, max_attachment_size=500 * 1024 * 1024)

    def multipart_item(self):
        return SimpleNamespace(id='a1', status='UPLOADING', multipart=True, size=40, object_key='attachments/s1/a1',
            storage_upload_id='upload-1', sha256=None, updated_at=None)

    @patch('app.attachment_service.head_size')
    @patch('app.attachment_service.complete_multipart_upload')
    @patch('app.attachment_service.get_settings')
    def test_multipart_requires_complete_ordered_parts(self, get_settings, complete_storage, _head):
        get_settings.return_value = self.settings()
        payload = SessionUploadCompleteInput(parts=[{'part_number': 1, 'etag': 'one'}, {'part_number': 2, 'etag': 'two'}])
        with self.assertRaises(HTTPException) as raised:
            complete_upload(Mock(), self.multipart_item(), payload)
        self.assertEqual(raised.exception.status_code, 422)
        complete_storage.assert_not_called()

    @patch('app.attachment_service.head_size', return_value=40)
    @patch('app.attachment_service.complete_multipart_upload')
    @patch('app.attachment_service.get_settings')
    def test_valid_multipart_completion_marks_ready_and_checksum(self, get_settings, complete_storage, _head):
        get_settings.return_value = self.settings()
        item = self.multipart_item()
        payload = SessionUploadCompleteInput(sha256='A' * 64, parts=[
            {'part_number': 1, 'etag': 'one'}, {'part_number': 2, 'etag': 'two'}, {'part_number': 3, 'etag': 'three'},
        ])
        complete_upload(Mock(), item, payload)
        self.assertEqual(item.status, 'READY')
        self.assertEqual(item.sha256, 'a' * 64)
        complete_storage.assert_called_once()

    def test_single_upload_rejects_parts(self):
        item = SimpleNamespace(status='UPLOADING', multipart=False)
        payload = SessionUploadCompleteInput(parts=[{'part_number': 1, 'etag': 'one'}])
        with self.assertRaises(HTTPException):
            complete_upload(Mock(), item, payload)


class UploadSessionAndCleanupTests(unittest.TestCase):
    @patch('app.attachment_service.authorize')
    def test_new_wkd_session_requires_create_permission(self, authorize):
        db = Mock()
        user = SimpleNamespace(id='u1')
        session = create_session(db, user, UploadSessionInput(project_id='p1'))
        authorize.assert_called_once_with(db, user, 'wkd.create', 'p1')
        self.assertIsNone(session.wkd_id)
        db.add.assert_called_once_with(session)

    @patch('app.attachment_service.delete_object')
    def test_expired_unbound_attachment_is_deleted_and_session_closed(self, delete_object):
        item = SimpleNamespace(status='READY', multipart=False, storage_upload_id=None, object_key='attachments/s1/a1')
        session = SimpleNamespace(status='OPEN')
        db = Mock()
        db.scalars.side_effect = [SimpleNamespace(all=lambda: [item]), SimpleNamespace(all=lambda: [session])]
        count = cleanup_expired_attachments(db)
        self.assertEqual(count, 1)
        self.assertEqual(session.status, 'EXPIRED')
        delete_object.assert_called_once_with(item.object_key)
        db.delete.assert_called_once_with(item)
        db.commit.assert_called_once()


class WkdCreationIdempotencyTests(unittest.TestCase):
    @patch('app.routers.wkd.wkd_out', return_value={'id': 'w1'})
    @patch('app.routers.wkd.authorize')
    def test_same_idempotent_request_returns_existing_wkd(self, _authorize, _out):
        payload = CreateWkdInput(**BASE, idempotency_key='request-1234')
        fingerprint = __import__('hashlib').sha256(payload.model_dump_json(exclude={'idempotency_key'}).encode()).hexdigest()
        existing = SimpleNamespace(creation_hash=fingerprint)
        db = Mock()
        db.scalar.return_value = existing
        result = create_wkd(payload, db, SimpleNamespace(id='u1'))
        self.assertEqual(result, {'id': 'w1'})
        db.add.assert_not_called()

    @patch('app.routers.wkd.authorize')
    def test_same_key_with_different_payload_is_rejected(self, _authorize):
        payload = CreateWkdInput(**BASE, idempotency_key='request-1234')
        db = Mock()
        db.scalar.return_value = SimpleNamespace(creation_hash='different')
        with self.assertRaises(HTTPException) as raised:
            create_wkd(payload, db, SimpleNamespace(id='u1'))
        self.assertEqual(raised.exception.status_code, 409)


if __name__ == '__main__':
    unittest.main()

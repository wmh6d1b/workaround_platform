from datetime import datetime, timedelta
from math import ceil
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import get_settings
from .deps import authorize
from .models import Attachment, UploadSession, User, Wkd
from .schemas import SessionUploadCompleteInput, SessionUploadInput, UploadSessionInput
from .storage import (
    abort_multipart_upload,
    abort_stale_multipart_uploads,
    complete_multipart_upload,
    create_multipart_upload,
    delete_object,
    head_size,
    upload_part_url,
    upload_url,
)


def attachment_out(item: Attachment) -> dict:
    return {
        'id': item.id,
        'filename': item.original_filename,
        'size': item.size,
        'content_type': item.content_type,
        'sha256': item.sha256,
        'status': item.status,
        'multipart': item.multipart,
        'upload_session_id': item.upload_session_id,
        'created_at': item.created_at,
    }


def session_out(session: UploadSession, attachments: list[Attachment]) -> dict:
    return {
        'id': session.id,
        'project_id': session.project_id,
        'wkd_id': session.wkd_id,
        'status': session.status,
        'expires_at': session.expires_at,
        'attachments': [attachment_out(item) for item in attachments],
    }


def create_session(db: Session, user: User, payload: UploadSessionInput) -> UploadSession:
    project_id = payload.project_id
    if payload.wkd_id:
        wkd = db.get(Wkd, payload.wkd_id)
        if not wkd:
            raise HTTPException(404, 'WKD 不存在')
        if wkd.project_id != project_id:
            raise HTTPException(422, '上传会话项目与 WKD 所属项目不一致')
        authorize(db, user, 'files.upload', project_id)
    else:
        authorize(db, user, 'wkd.create', project_id)
    session = UploadSession(project_id=project_id, owner_id=user.id, wkd_id=payload.wkd_id,
        expires_at=datetime.utcnow() + timedelta(hours=get_settings().attachment_session_expire_hours))
    db.add(session)
    db.flush()
    return session


def owned_session(db: Session, user: User, session_id: str, permission: str = 'files.upload') -> UploadSession:
    session = db.get(UploadSession, session_id)
    if not session or session.owner_id != user.id:
        raise HTTPException(404, '上传会话不存在')
    if session.status != 'OPEN' or session.expires_at <= datetime.utcnow():
        raise HTTPException(410, '上传会话已过期，请重新创建')
    authorize(db, user, permission, session.project_id)
    return session


def list_session_attachments(db: Session, session_id: str) -> list[Attachment]:
    return list(db.scalars(select(Attachment).where(Attachment.upload_session_id == session_id)
        .order_by(Attachment.created_at)).all())


def initiate_upload(db: Session, session: UploadSession, payload: SessionUploadInput, force_single: bool = False) -> Attachment:
    settings = get_settings()
    if payload.size > settings.max_attachment_size:
        raise HTTPException(413, '单个附件不能超过 500 MB')
    count = db.scalar(select(func.count()).select_from(Attachment).where(Attachment.upload_session_id == session.id)) or 0
    if count >= 100:
        raise HTTPException(409, '每个上传会话最多包含 100 个附件')
    item = Attachment(id=str(uuid4()), upload_session_id=session.id, wkd_id=session.wkd_id,
        original_filename=payload.filename, size=payload.size, content_type=payload.content_type,
        sha256=None, category='WKD', status='UPLOADING', uploader_id=session.owner_id,
        multipart=not force_single and payload.size >= settings.attachment_multipart_threshold)
    item.object_key = f'attachments/{session.id}/{item.id}'
    if item.multipart:
        item.storage_upload_id = create_multipart_upload(item.object_key, item.content_type)
    db.add(item)
    db.flush()
    return item


def upload_start_out(item: Attachment) -> dict:
    result = attachment_out(item)
    result.update({'object_key': item.object_key, 'expires_in': get_settings().presign_expire_seconds})
    if item.multipart:
        part_size = get_settings().attachment_multipart_part_size
        result.update({'upload_id': item.storage_upload_id, 'part_size': part_size,
            'part_count': ceil(item.size / part_size)})
    else:
        result['upload_url'] = upload_url(item.object_key, item.content_type)
    return result


def owned_upload(db: Session, user: User, attachment_id: str) -> Attachment:
    item = db.get(Attachment, attachment_id)
    if not item or not item.upload_session_id:
        raise HTTPException(404, '附件上传任务不存在')
    owned_session(db, user, item.upload_session_id)
    return item


def complete_upload(db: Session, item: Attachment, payload: SessionUploadCompleteInput) -> None:
    if item.status == 'READY':
        return
    if item.status != 'UPLOADING':
        raise HTTPException(409, '当前附件状态不允许完成上传')
    if item.multipart:
        part_size = get_settings().attachment_multipart_part_size
        expected = list(range(1, ceil(item.size / part_size) + 1))
        numbers = [part.part_number for part in payload.parts]
        if numbers != expected:
            raise HTTPException(422, '分片列表不完整或顺序不正确')
        complete_multipart_upload(item.object_key, item.storage_upload_id,
            [{'PartNumber': part.part_number, 'ETag': part.etag.strip()} for part in payload.parts])
    elif payload.parts:
        raise HTTPException(422, '单文件上传不能携带分片信息')
    actual_size = head_size(item.object_key)
    if actual_size != item.size or actual_size > get_settings().max_attachment_size:
        raise HTTPException(422, '文件大小校验失败')
    item.status = 'READY'
    item.sha256 = payload.sha256.lower() if payload.sha256 else None
    item.updated_at = datetime.utcnow()


def validate_binding_rows(rows: list[Attachment], attachment_ids: list[str], user: User, wkd: Wkd) -> None:
    if len(rows) != len(attachment_ids):
        raise HTTPException(422, '部分附件不存在，请刷新附件列表')
    for item in rows:
        session = item.session
        if item.uploader_id != user.id or item.wkd_id is not None or item.status != 'READY':
            raise HTTPException(409, f'附件「{item.original_filename}」不属于当前用户、已绑定或尚未上传完成')
        if not session or session.project_id != wkd.project_id or session.wkd_id is not None:
            raise HTTPException(409, f'附件「{item.original_filename}」与当前 WKD 项目或上传会话不匹配')
        if session.status != 'OPEN' or session.expires_at <= datetime.utcnow():
            raise HTTPException(410, f'附件「{item.original_filename}」所在上传会话已过期')


def bind_attachments(db: Session, user: User, wkd: Wkd, attachment_ids: list[str]) -> list[Attachment]:
    if not attachment_ids:
        return []
    rows = list(db.scalars(select(Attachment).where(Attachment.id.in_(attachment_ids)).with_for_update(of=Attachment)).all())
    validate_binding_rows(rows, attachment_ids, user, wkd)
    by_id = {item.id: item for item in rows}
    ordered = [by_id[item_id] for item_id in attachment_ids]
    for item in ordered:
        item.wkd_id = wkd.id
        item.updated_at = datetime.utcnow()
    return ordered


def cancel_upload(db: Session, item: Attachment) -> None:
    if item.wkd_id and item.status == 'READY':
        raise HTTPException(409, '已绑定 WKD 的附件不能通过上传会话删除')
    if item.status == 'UPLOADING' and item.multipart and item.storage_upload_id:
        abort_multipart_upload(item.object_key, item.storage_upload_id)
    delete_object(item.object_key)
    db.delete(item)


def cleanup_expired_attachments(db: Session) -> int:
    now = datetime.utcnow()
    rows = list(db.scalars(select(Attachment).join(UploadSession, Attachment.upload_session_id == UploadSession.id)
        .where(UploadSession.expires_at <= now, UploadSession.status == 'OPEN')
        .where((Attachment.wkd_id.is_(None)) | (Attachment.status != 'READY'))).all())
    for item in rows:
        try:
            if item.status == 'UPLOADING' and item.multipart and item.storage_upload_id:
                abort_multipart_upload(item.object_key, item.storage_upload_id)
            delete_object(item.object_key)
        except Exception:
            # 对象可能尚未上传或已被生命周期策略清理；数据库记录仍可安全移除。
            pass
        db.delete(item)
    sessions = list(db.scalars(select(UploadSession).where(UploadSession.expires_at <= now,
        UploadSession.status == 'OPEN')).all())
    for session in sessions:
        session.status = 'EXPIRED'
    db.commit()
    return len(rows)


def cleanup_attachment_storage(db: Session) -> dict[str, int]:
    expired = cleanup_expired_attachments(db)
    cutoff = datetime.utcnow() - timedelta(hours=get_settings().attachment_session_expire_hours)
    stale_parts = abort_stale_multipart_uploads('attachments/', cutoff)
    return {'expired_attachments': expired, 'stale_multipart_uploads': stale_parts}

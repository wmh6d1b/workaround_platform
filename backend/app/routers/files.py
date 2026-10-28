from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..attachment_service import (
    attachment_out, cancel_upload, complete_upload as finish_session_upload,
    create_session, initiate_upload, list_session_attachments, owned_session, owned_upload,
    session_out, upload_start_out,
)
from ..config import get_settings
from ..db import get_db
from ..deps import authorize, current_user
from ..models import Attachment, User, Wkd
from ..schemas import (
    SessionUploadCompleteInput, SessionUploadInput, UploadCompleteInput, UploadInput,
    UploadPartInput, UploadSessionInput,
)
from ..services import audit, commit
from ..storage import download_url, upload_part_url, upload_url

router = APIRouter(prefix='/files', tags=['附件与 RustFS 存储'])


@router.post('/upload-sessions', status_code=201, summary='创建草稿或既有 WKD 附件上传会话')
def create_upload_session(payload: UploadSessionInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = create_session(db, user, payload)
    commit(db)
    return session_out(session, [])


@router.get('/upload-sessions/{session_id}', summary='恢复本人上传会话及附件状态')
def get_upload_session(session_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = owned_session(db, user, session_id)
    return session_out(session, list_session_attachments(db, session.id))


@router.post('/upload-sessions/{session_id}/uploads', status_code=201, summary='初始化附件直传或分片上传')
def start_session_upload(session_id: str, payload: SessionUploadInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    session = owned_session(db, user, session_id)
    item = initiate_upload(db, session, payload)
    audit(db, user, 'ATTACHMENT_UPLOAD_START', 'attachment', item.id, {'size': item.size, 'multipart': item.multipart})
    commit(db)
    return upload_start_out(item)


@router.post('/uploads/{attachment_id}/part-url', summary='获取本人附件的单个分片预签名地址')
def get_upload_part_url(attachment_id: str, payload: UploadPartInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned_upload(db, user, attachment_id)
    if not item.multipart or not item.storage_upload_id or item.status != 'UPLOADING':
        raise HTTPException(409, '该附件不是进行中的分片上传')
    from math import ceil
    if payload.part_number > ceil(item.size / get_settings().attachment_multipart_part_size):
        raise HTTPException(422, '分片序号超出文件范围')
    return {'upload_url': upload_part_url(item.object_key, item.storage_upload_id, payload.part_number),
        'expires_in': get_settings().presign_expire_seconds}


@router.post('/uploads/{attachment_id}/complete', summary='核验对象并完成本人附件上传')
def complete_session_upload(attachment_id: str, payload: SessionUploadCompleteInput,
                            db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned_upload(db, user, attachment_id)
    finish_session_upload(db, item, payload)
    audit(db, user, 'ATTACHMENT_UPLOAD', 'attachment', item.id, {'size': item.size, 'sha256': item.sha256})
    commit(db)
    return attachment_out(item)


@router.delete('/uploads/{attachment_id}', status_code=204, summary='取消未绑定附件并清理存储对象')
def delete_session_upload(attachment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = owned_upload(db, user, attachment_id)
    cancel_upload(db, item)
    audit(db, user, 'ATTACHMENT_UPLOAD_CANCEL', 'attachment', attachment_id)
    commit(db)
    return Response(status_code=204)


@router.post('/upload-url', summary='兼容接口：为既有 WKD 创建单次上传地址', deprecated=True)
def create_upload(payload: UploadInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not payload.wkd_id:
        raise HTTPException(422, '新建 WKD 附件必须使用上传会话接口')
    wkd = db.get(Wkd, payload.wkd_id)
    if not wkd:
        raise HTTPException(404, 'WKD 不存在')
    session = create_session(db, user, UploadSessionInput(project_id=wkd.project_id, wkd_id=wkd.id))
    item = initiate_upload(db, session, SessionUploadInput(filename=payload.filename, size=payload.size,
        content_type=payload.content_type), force_single=True)
    commit(db)
    return {'object_key': item.object_key, 'upload_url': upload_url(item.object_key, item.content_type),
        'attachment_id': item.id, 'upload_session_id': session.id, 'expires_in': get_settings().presign_expire_seconds}


@router.post('/complete', status_code=201, summary='兼容接口：完成既有 WKD 单次上传', deprecated=True)
def complete_upload(payload: UploadCompleteInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if not payload.wkd_id:
        raise HTTPException(422, '新建 WKD 附件必须使用上传会话接口')
    item = db.scalar(select(Attachment).where(Attachment.object_key == payload.object_key,
        Attachment.uploader_id == user.id, Attachment.wkd_id == payload.wkd_id))
    if not item or not item.upload_session_id:
        raise HTTPException(404, '附件上传任务不存在')
    owned_session(db, user, item.upload_session_id)
    if payload.size != item.size or payload.filename != item.original_filename:
        raise HTTPException(422, '附件元数据与上传任务不一致')
    finish_session_upload(db, item, SessionUploadCompleteInput(sha256=payload.sha256))
    audit(db, user, 'ATTACHMENT_UPLOAD', 'attachment', item.id, {'size': item.size})
    commit(db)
    return attachment_out(item)


@router.get('/attachments', summary='查询 WKD 已完成附件列表')
def attachments(wkd_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    wkd = db.get(Wkd, wkd_id)
    if not wkd:
        raise HTTPException(404, 'WKD 不存在')
    authorize(db, user, 'wkd.view', wkd.project_id)
    rows = db.scalars(select(Attachment).where(Attachment.wkd_id == wkd_id, Attachment.status == 'READY')
        .order_by(Attachment.created_at)).all()
    return [attachment_out(item) for item in rows]


@router.get('/attachments/{attachment_id}/download', summary='鉴权后获取附件预签名下载地址')
def attachment_download(attachment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(Attachment, attachment_id)
    if not item or item.status != 'READY':
        raise HTTPException(404, '附件不存在或尚未上传完成')
    if item.wkd_id:
        wkd = db.get(Wkd, item.wkd_id)
        if not wkd:
            raise HTTPException(404, '附件所属 WKD 不存在')
        authorize(db, user, 'files.download', wkd.project_id)
    elif item.upload_session_id:
        owned_session(db, user, item.upload_session_id, permission='files.download')
    else:
        raise HTTPException(404, '附件不存在')
    audit(db, user, 'ATTACHMENT_DOWNLOAD', 'attachment', item.id)
    db.commit()
    return {'url': download_url(item.object_key, item.original_filename), 'expires_in': get_settings().presign_expire_seconds}

from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..deps import authorize, current_user
from ..models import Attachment, User, Wkd
from ..schemas import UploadCompleteInput, UploadInput
from ..services import audit, commit
from ..storage import download_url, head_size, upload_url

router = APIRouter(prefix='/files', tags=['附件与 RustFS 存储'])

@router.post('/upload-url', summary='鉴权并创建附件预签名上传地址')
def create_upload(payload: UploadInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    settings = get_settings()
    if payload.size > settings.max_attachment_size: raise HTTPException(413, '单个附件不能超过 500 MB')
    project_id = None
    if payload.wkd_id:
        wkd = db.get(Wkd, payload.wkd_id)
        if not wkd: raise HTTPException(404, 'WKD 不存在')
        project_id = wkd.project_id
    authorize(db, user, 'files.upload', project_id)
    key = f'wkd/{payload.wkd_id or "unassigned"}/attachments/{uuid4()}'
    return {'object_key': key, 'upload_url': upload_url(key, payload.content_type), 'expires_in': settings.presign_expire_seconds}

@router.post('/complete', status_code=201, summary='校验 RustFS 文件并保存附件元数据')
def complete_upload(payload: UploadCompleteInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if payload.size > get_settings().max_attachment_size: raise HTTPException(413, '单个附件不能超过 500 MB')
    project_id = None
    if payload.wkd_id:
        wkd = db.get(Wkd, payload.wkd_id)
        if not wkd: raise HTTPException(404, 'WKD 不存在')
        project_id = wkd.project_id
    authorize(db, user, 'files.upload', project_id)
    expected_prefix = f'wkd/{payload.wkd_id or "unassigned"}/attachments/'
    if not payload.object_key.startswith(expected_prefix):
        raise HTTPException(422, '附件对象地址与 WKD 不匹配')
    actual_size = head_size(payload.object_key)
    if actual_size != payload.size or actual_size > get_settings().max_attachment_size: raise HTTPException(422, '文件大小校验失败')
    item = Attachment(**payload.model_dump(), uploader_id=user.id)
    db.add(item)
    db.flush()
    audit(db, user, 'ATTACHMENT_UPLOAD', 'attachment', item.id, {'size': item.size})
    commit(db)
    return {'id': item.id, 'object_key': item.object_key, 'filename': item.original_filename, 'size': item.size}

@router.get('/attachments', summary='查询 WKD 附件列表')
def attachments(wkd_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    wkd = db.get(Wkd, wkd_id)
    if not wkd: raise HTTPException(404, 'WKD 不存在')
    authorize(db, user, 'wkd.view', wkd.project_id)
    from sqlalchemy import select
    rows = db.scalars(select(Attachment).where(Attachment.wkd_id == wkd_id)).all()
    return [{'id': x.id, 'filename': x.original_filename, 'size': x.size, 'content_type': x.content_type, 'created_at': x.created_at} for x in rows]

@router.get('/attachments/{attachment_id}/download', summary='鉴权后获取附件预签名下载地址')
def attachment_download(attachment_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(Attachment, attachment_id)
    if not item: raise HTTPException(404, '附件不存在')
    project_id = None
    if item.wkd_id:
        wkd = db.get(Wkd, item.wkd_id)
        project_id = wkd.project_id if wkd else None
    authorize(db, user, 'files.download', project_id)
    audit(db, user, 'ATTACHMENT_DOWNLOAD', 'attachment', item.id)
    db.commit()
    return {'url': download_url(item.object_key, item.original_filename), 'expires_in': get_settings().presign_expire_seconds}

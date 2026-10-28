import hashlib
from datetime import datetime
from tempfile import TemporaryFile
from uuid import uuid4
from ..builder import write_executable_package
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, defer, noload, selectinload
from ..attachment_service import attachment_out
from ..db import get_db
from ..deps import accessible_project_ids, authorize, current_user, ensure_operational_project
from ..models import ArtifactType, Attachment, BuildArtifact, BuildArtifactItem, Machine, User, Wkd, WkdStatus
from ..schemas import BuildInput
from ..services import artifact_out, audit, commit, wkd_list_out, wkd_out
from ..storage import client, delete_object, download_url, read_object
from ..config import get_settings

router = APIRouter(tags=['调试构建、正式构建与制品'])

@router.get('/builds/eligible', summary='查询轻量可构建 WKD 列表，不返回 operations；正式构建仅返回 APPROVED')
def eligible(kind: str = 'DEBUG', project_id: str | None = None, machine_id: str | None = None,
             db: Session = Depends(get_db), user: User = Depends(current_user)):
    if kind not in ('DEBUG', 'RELEASE'): raise HTTPException(422, '未知构建类型')
    permission = 'build.release.view' if kind == 'RELEASE' else 'build.debug.view'
    authorize(db, user, permission, project_id)
    query = select(Wkd).options(noload(Wkd.operations))
    if project_id:
        query = query.where(Wkd.project_id == project_id)
    else:
        allowed_projects = accessible_project_ids(db, user)
        if allowed_projects is not None: query = query.where(Wkd.project_id.in_(allowed_projects))
    if machine_id: query = query.where(Wkd.machines.any(id=machine_id))
    query = query.where(Wkd.status == WkdStatus.APPROVED) if kind == 'RELEASE' else query.where(Wkd.status.not_in([WkdStatus.NEW_WKD, WkdStatus.DISABLE_CONFIRM, WkdStatus.DISABLED]))
    rows = db.scalars(query.order_by(Wkd.created_at)).unique().all()
    return {'items': [wkd_list_out(x) for x in rows], 'default_selected_ids': [x.id for x in rows]}

@router.post('/builds/{kind}', status_code=201, summary='同步执行构建；1～200 个不重复 WKD，普通附件总量默认不超过 2 GB')
def build(kind: str, payload: BuildInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if kind not in ('debug', 'release'): raise HTTPException(404, '未知构建类型')
    authorize(db, user, f'build.{kind}.build', payload.project_id)
    ensure_operational_project(db, payload.project_id)
    rows = db.scalars(select(Wkd).where(Wkd.id.in_(payload.wkd_ids))).unique().all()
    if len(rows) != len(set(payload.wkd_ids)): raise HTTPException(422, '存在无效 WKD')
    allowed = {WkdStatus.APPROVED} if kind == 'release' else {WkdStatus.VERIFY, WkdStatus.REVIEW, WkdStatus.APPROVED}
    if any(x.status not in allowed or x.project_id != payload.project_id or not any(m.id == payload.machine_id for m in x.machines) for x in rows):
        raise HTTPException(409, '构建内容包含状态、项目或机台不符合要求的 WKD')
    rows.sort(key=lambda x: x.created_at)
    artifact_id = str(uuid4())
    snapshots = [wkd_out(x) for x in rows]
    attachment_rows = db.scalars(select(Attachment).where(
        Attachment.wkd_id.in_([x.id for x in rows]), Attachment.status == 'READY').order_by(Attachment.created_at)).all()
    attachments = {}
    for item in attachment_rows:
        metadata = attachment_out(item)
        metadata['object_key'] = item.object_key
        attachments.setdefault(item.wkd_id, []).append(metadata)
    settings = get_settings()
    if sum(item.size for item in attachment_rows) > settings.max_build_attachment_bytes:
        raise HTTPException(413, '本次构建的普通附件总大小超过 2 GB 预算，请分批构建')
    key = f'artifacts/{payload.project_id}/{payload.machine_id}/{artifact_id}.tar.gz'
    with TemporaryFile(prefix='wmp-build-', suffix='.tar.gz') as output:
        try:
            write_executable_package(output, artifact_id=artifact_id, kind=kind, project_id=payload.project_id,
                                     machine_id=payload.machine_id, wkds=snapshots, attachments=attachments,
                                     attachment_reader=read_object)
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, f'WKD 构建内容无法打包：{exc}') from None
        size = output.tell()
        output.seek(0)
        digest = hashlib.sha256()
        while chunk := output.read(1024 * 1024):
            digest.update(chunk)
        output.seek(0)
        client.upload_fileobj(output, settings.rustfs_bucket, key,
                              ExtraArgs={'ContentType': 'application/gzip'})
    try:
        artifact = BuildArtifact(id=artifact_id, number=f"BUILD-{datetime.utcnow():%Y%m%d%H%M%S}-{artifact_id[:6]}",
            filename=f'WMP_{kind.upper()}_{artifact_id[:8]}.tar.gz', object_key=key, project_id=payload.project_id,
            machine_id=payload.machine_id, type=ArtifactType(kind.upper()), size=size,
            sha256=digest.hexdigest(), builder_id=user.id)
        artifact.items = [BuildArtifactItem(wkd_id=x.id, position=i + 1, snapshot=snapshots[i]) for i, x in enumerate(rows)]
        db.add(artifact)
        audit(db, user, f'BUILD_{kind.upper()}', 'artifact', artifact.id,
              {'wkd_count': len(rows), 'attachment_count': len(attachment_rows)})
        commit(db)
    except Exception:
        try:
            delete_object(key)
        except Exception:
            # 补偿失败由对象存储生命周期策略兜底，不能掩盖原始数据库异常。
            pass
        raise
    return artifact_out(artifact)

@router.get('/artifacts', summary='查询轻量制品记录，不返回明细中的 WKD snapshot 正文')
def artifacts(project_id: str | None = None, machine_id: str | None = None, kind: str | None = None,
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    if kind and kind not in ('DEBUG', 'RELEASE'): raise HTTPException(422, '未知制品类型')
    authorize(db, user, 'build.debug.view' if kind == 'DEBUG' else 'build.release.view', project_id)
    query = (select(BuildArtifact)
             .options(selectinload(BuildArtifact.items).options(defer(BuildArtifactItem.snapshot)))
             .order_by(BuildArtifact.created_at.desc()))
    if project_id:
        query = query.where(BuildArtifact.project_id == project_id)
    else:
        allowed_projects = accessible_project_ids(db, user)
        if allowed_projects is not None: query = query.where(BuildArtifact.project_id.in_(allowed_projects))
    if machine_id: query = query.where(BuildArtifact.machine_id == machine_id)
    if kind: query = query.where(BuildArtifact.type == ArtifactType(kind))
    return [artifact_out(x, include_snapshots=False) for x in db.scalars(query).all()]

@router.get('/artifacts/{artifact_id}/download', summary='鉴权后获取制品预签名下载地址')
def artifact_download(artifact_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(BuildArtifact, artifact_id)
    if not item: raise HTTPException(404, '制品不存在')
    permission = 'build.debug.view' if item.type == ArtifactType.DEBUG else 'build.release.download'
    authorize(db, user, permission, item.project_id)
    audit(db, user, 'ARTIFACT_DOWNLOAD', 'artifact', item.id)
    db.commit()
    return {'url': download_url(item.object_key, item.filename), 'expires_in': get_settings().presign_expire_seconds}

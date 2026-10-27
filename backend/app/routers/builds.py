import hashlib
from datetime import datetime
from uuid import uuid4
from ..builder import build_executable_package
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..deps import accessible_project_ids, authorize, current_user
from ..models import ArtifactType, BuildArtifact, BuildArtifactItem, Machine, User, Wkd, WkdStatus
from ..schemas import BuildInput
from ..services import artifact_out, audit, commit, wkd_out
from ..storage import client, download_url
from ..config import get_settings

router = APIRouter(tags=['调试构建、正式构建与制品'])

@router.get('/builds/eligible', summary='查询可构建 WKD；正式构建按项目和机台返回全部 APPROVED')
def eligible(kind: str = 'DEBUG', project_id: str | None = None, machine_id: str | None = None,
             db: Session = Depends(get_db), user: User = Depends(current_user)):
    if kind not in ('DEBUG', 'RELEASE'): raise HTTPException(422, '未知构建类型')
    permission = 'build.release.view' if kind == 'RELEASE' else 'build.debug.view'
    authorize(db, user, permission, project_id)
    query = select(Wkd)
    if project_id:
        query = query.where(Wkd.project_id == project_id)
    else:
        allowed_projects = accessible_project_ids(db, user)
        if allowed_projects is not None: query = query.where(Wkd.project_id.in_(allowed_projects))
    if machine_id: query = query.where(Wkd.machines.any(id=machine_id))
    query = query.where(Wkd.status == WkdStatus.APPROVED) if kind == 'RELEASE' else query.where(Wkd.status.not_in([WkdStatus.NEW_WKD, WkdStatus.DISABLE_CONFIRM, WkdStatus.DISABLED]))
    rows = db.scalars(query.order_by(Wkd.created_at)).unique().all()
    return {'items': [wkd_out(x) for x in rows], 'default_selected_ids': [x.id for x in rows]}

@router.post('/builds/{kind}', status_code=201, summary='执行调试或正式构建，生成 tar.gz 并上传 RustFS')
def build(kind: str, payload: BuildInput, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if kind not in ('debug', 'release'): raise HTTPException(404, '未知构建类型')
    authorize(db, user, f'build.{kind}.build', payload.project_id)
    rows = db.scalars(select(Wkd).where(Wkd.id.in_(payload.wkd_ids))).unique().all()
    if len(rows) != len(set(payload.wkd_ids)): raise HTTPException(422, '存在无效 WKD')
    allowed = {WkdStatus.APPROVED} if kind == 'release' else {WkdStatus.VERIFY, WkdStatus.REVIEW, WkdStatus.APPROVED}
    if any(x.status not in allowed or x.project_id != payload.project_id or not any(m.id == payload.machine_id for m in x.machines) for x in rows):
        raise HTTPException(409, '构建内容包含状态、项目或机台不符合要求的 WKD')
    rows.sort(key=lambda x: x.created_at)
    artifact_id = str(uuid4())
    snapshots = [wkd_out(x) for x in rows]
    try:
        content = build_executable_package(artifact_id=artifact_id, kind=kind, project_id=payload.project_id,
                                           machine_id=payload.machine_id, wkds=snapshots)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, f'WKD 原子操作配置无法构建：{exc}') from None
    settings = get_settings()
    key = f'artifacts/{payload.project_id}/{payload.machine_id}/{artifact_id}.tar.gz'
    client.put_object(Bucket=settings.rustfs_bucket, Key=key, Body=content, ContentType='application/gzip')
    artifact = BuildArtifact(id=artifact_id, number=f"BUILD-{datetime.utcnow():%Y%m%d%H%M%S}-{artifact_id[:6]}",
        filename=f'WMP_{kind.upper()}_{artifact_id[:8]}.tar.gz', object_key=key, project_id=payload.project_id,
        machine_id=payload.machine_id, type=ArtifactType(kind.upper()), size=len(content),
        sha256=hashlib.sha256(content).hexdigest(), builder_id=user.id)
    artifact.items = [BuildArtifactItem(wkd_id=x.id, position=i + 1, snapshot=wkd_out(x)) for i, x in enumerate(rows)]
    db.add(artifact)
    audit(db, user, f'BUILD_{kind.upper()}', 'artifact', artifact.id, {'wkd_count': len(rows)})
    commit(db)
    return artifact_out(artifact)

@router.get('/artifacts', summary='查询基线制品或构建记录')
def artifacts(project_id: str | None = None, machine_id: str | None = None, kind: str | None = None,
              db: Session = Depends(get_db), user: User = Depends(current_user)):
    if kind and kind not in ('DEBUG', 'RELEASE'): raise HTTPException(422, '未知制品类型')
    authorize(db, user, 'build.debug.view' if kind == 'DEBUG' else 'build.release.view', project_id)
    query = select(BuildArtifact).order_by(BuildArtifact.created_at.desc())
    if project_id:
        query = query.where(BuildArtifact.project_id == project_id)
    else:
        allowed_projects = accessible_project_ids(db, user)
        if allowed_projects is not None: query = query.where(BuildArtifact.project_id.in_(allowed_projects))
    if machine_id: query = query.where(BuildArtifact.machine_id == machine_id)
    if kind: query = query.where(BuildArtifact.type == ArtifactType(kind))
    return [artifact_out(x) for x in db.scalars(query).all()]

@router.get('/artifacts/{artifact_id}/download', summary='鉴权后获取制品预签名下载地址')
def artifact_download(artifact_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    item = db.get(BuildArtifact, artifact_id)
    if not item: raise HTTPException(404, '制品不存在')
    permission = 'build.debug.view' if item.type == ArtifactType.DEBUG else 'build.release.download'
    authorize(db, user, permission, item.project_id)
    audit(db, user, 'ARTIFACT_DOWNLOAD', 'artifact', item.id)
    db.commit()
    return {'url': download_url(item.object_key, item.filename), 'expires_in': get_settings().presign_expire_seconds}

import enum
import uuid
from datetime import date, datetime
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, Integer, BigInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def uid() -> str:
    return str(uuid.uuid4())

class WkdStatus(str, enum.Enum):
    NEW_WKD = 'NEW_WKD'
    VERIFY = 'VERIFY'
    REVIEW = 'REVIEW'
    APPROVED = 'APPROVED'
    DISABLE_CONFIRM = 'DISABLE_CONFIRM'
    DISABLED = 'DISABLED'

class ExecutionType(str, enum.Enum):
    AUTOMATED = 'AUTOMATED'
    MANUAL = 'MANUAL'

class Stage(str, enum.Enum):
    PRE_UPGRADE = 'pre_upgrade'
    POST_UPGRADE = 'post_upgrade'
    POST_START = 'post_start'
    POST_INIT = 'post_init'
    CUSTOM = 'custom'

class OperationType(str, enum.Enum):
    UPLOAD_FILE = 'UPLOAD_FILE'
    LINUX_COMMAND = 'LINUX_COMMAND'
    SCRIPT = 'SCRIPT'

class ArtifactType(str, enum.Enum):
    DEBUG = 'DEBUG'
    RELEASE = 'RELEASE'

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(80), index=True)
    employee_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    department: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160))
    password_hash: Mapped[str | None] = mapped_column(String(256))
    oauth_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    global_role_id: Mapped[str | None] = mapped_column(String(36), ForeignKey('roles.id', ondelete='RESTRICT'), nullable=True)
    global_role: Mapped['Role | None'] = relationship(lazy='joined', foreign_keys=[global_role_id])
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Role(Base):
    __tablename__ = 'roles'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(255), default='')
    built_in: Mapped[bool] = mapped_column(Boolean, default=False)
    permissions: Mapped[list['Permission']] = relationship(secondary='role_permissions', lazy='selectin')

class Permission(Base):
    __tablename__ = 'permissions'
    code: Mapped[str] = mapped_column(String(100), primary_key=True)
    module: Mapped[str] = mapped_column(String(60))
    description: Mapped[str] = mapped_column(String(255))

class RolePermission(Base):
    __tablename__ = 'role_permissions'
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey('permissions.code'), primary_key=True)

class Project(Base):
    __tablename__ = 'projects'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(30), default='ENABLED')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ProjectMember(Base):
    __tablename__ = 'project_members'
    __table_args__ = (UniqueConstraint('project_id', 'user_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'))
    user: Mapped[User] = relationship(lazy='joined')
    role: Mapped[Role] = relationship(lazy='joined')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Version(Base):
    __tablename__ = 'versions'
    __table_args__ = (UniqueConstraint('project_id', 'number'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    number: Mapped[str] = mapped_column(String(60))
    baseline_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default='DEVELOPING')
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Machine(Base):
    __tablename__ = 'machines'
    __table_args__ = (UniqueConstraint('project_id', 'name'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100), default='')
    location: Mapped[str] = mapped_column(String(160), default='')
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(30), default='RUNNING')

class Subsystem(Base):
    __tablename__ = 'subsystems'
    __table_args__ = (UniqueConstraint('project_id', 'name'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    code: Mapped[str] = mapped_column(String(80))
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(30), default='ENABLED')

class Wkd(Base):
    __tablename__ = 'wkds'
    __table_args__ = (
        CheckConstraint('issue_no IS NOT NULL OR requirement_no IS NOT NULL', name='ck_wkd_issue_or_requirement'),
        CheckConstraint('issue_no IS NULL OR found_version_id IS NOT NULL', name='ck_wkd_found_version_required'),
        UniqueConstraint('version_id', 'custom_stage_name', name='uq_wkd_custom_stage_per_version'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    number: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    issue_no: Mapped[str | None] = mapped_column(String(100))
    requirement_no: Mapped[str | None] = mapped_column(String(100))
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey('versions.id'), index=True)
    found_version_id: Mapped[str | None] = mapped_column(ForeignKey('versions.id'))
    planned_version_id: Mapped[str | None] = mapped_column(ForeignKey('versions.id'))
    subsystem_id: Mapped[str] = mapped_column(ForeignKey('subsystems.id'))
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    current_handler_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), index=True)
    execution_type: Mapped[ExecutionType] = mapped_column(Enum(ExecutionType))
    activity_scene: Mapped[str] = mapped_column(String(60))
    measure_type: Mapped[str] = mapped_column(String(60))
    remark: Mapped[str | None] = mapped_column(Text)
    status: Mapped[WkdStatus] = mapped_column(Enum(WkdStatus), default=WkdStatus.NEW_WKD, index=True)
    stage: Mapped[Stage | None] = mapped_column(Enum(Stage))
    custom_stage_name: Mapped[str | None] = mapped_column(String(100))
    lock_version: Mapped[int] = mapped_column(Integer, default=1)
    disabled_reason: Mapped[str | None] = mapped_column(Text)
    disabled_from: Mapped[WkdStatus | None] = mapped_column(Enum(WkdStatus))
    creation_key: Mapped[str | None] = mapped_column(String(64))
    creation_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    project: Mapped[Project] = relationship(lazy='joined')
    version: Mapped[Version] = relationship(lazy='joined', foreign_keys=[version_id])
    found_version: Mapped[Version | None] = relationship(lazy='joined', foreign_keys=[found_version_id])
    planned_version: Mapped[Version | None] = relationship(lazy='joined', foreign_keys=[planned_version_id])
    subsystem: Mapped[Subsystem] = relationship(lazy='joined')
    owner: Mapped[User] = relationship(lazy='joined', foreign_keys=[owner_id])
    current_handler: Mapped[User | None] = relationship(lazy='joined', foreign_keys=[current_handler_id])
    machines: Mapped[list[Machine]] = relationship(secondary='wkd_machines', lazy='selectin')
    operations: Mapped[list['WkdOperation']] = relationship(back_populates='wkd', cascade='all, delete-orphan', order_by='WkdOperation.position', lazy='selectin')

class WkdMachine(Base):
    __tablename__ = 'wkd_machines'
    wkd_id: Mapped[str] = mapped_column(ForeignKey('wkds.id', ondelete='CASCADE'), primary_key=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey('machines.id'), primary_key=True)

class WkdOperation(Base):
    __tablename__ = 'wkd_operations'
    __table_args__ = (UniqueConstraint('wkd_id', 'position'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    wkd_id: Mapped[str] = mapped_column(ForeignKey('wkds.id', ondelete='CASCADE'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    type: Mapped[OperationType] = mapped_column(Enum(OperationType))
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    wkd: Mapped[Wkd] = relationship(back_populates='operations')

class WkdDailySequence(Base):
    __tablename__ = 'wkd_daily_sequences'
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)

class WkdHistory(Base):
    __tablename__ = 'wkd_history'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    wkd_id: Mapped[str] = mapped_column(ForeignKey('wkds.id', ondelete='CASCADE'), index=True)
    action: Mapped[str] = mapped_column(String(50))
    from_status: Mapped[WkdStatus | None] = mapped_column(Enum(WkdStatus))
    to_status: Mapped[WkdStatus] = mapped_column(Enum(WkdStatus))
    note: Mapped[str | None] = mapped_column(Text)
    changes: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    operator_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    operator: Mapped[User] = relationship(lazy='joined')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UploadSession(Base):
    __tablename__ = 'upload_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id', ondelete='CASCADE'), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    wkd_id: Mapped[str | None] = mapped_column(ForeignKey('wkds.id', ondelete='CASCADE'), index=True)
    status: Mapped[str] = mapped_column(String(20), default='OPEN', index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Attachment(Base):
    __tablename__ = 'attachments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    wkd_id: Mapped[str | None] = mapped_column(ForeignKey('wkds.id', ondelete='CASCADE'), index=True)
    upload_session_id: Mapped[str | None] = mapped_column(ForeignKey('upload_sessions.id', ondelete='SET NULL'), index=True)
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger)
    content_type: Mapped[str | None] = mapped_column(String(150))
    sha256: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(40), default='WKD')
    status: Mapped[str] = mapped_column(String(20), default='READY', index=True)
    multipart: Mapped[bool] = mapped_column(Boolean, default=False)
    storage_upload_id: Mapped[str | None] = mapped_column(String(255))
    uploader_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    session: Mapped[UploadSession | None] = relationship(lazy='joined', foreign_keys=[upload_session_id])
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class BuildArtifact(Base):
    __tablename__ = 'build_artifacts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    number: Mapped[str] = mapped_column(String(60), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), index=True)
    machine_id: Mapped[str] = mapped_column(ForeignKey('machines.id'), index=True)
    type: Mapped[ArtifactType] = mapped_column(Enum(ArtifactType), index=True)
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    builder_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list['BuildArtifactItem']] = relationship(cascade='all, delete-orphan', order_by='BuildArtifactItem.position', lazy='selectin')

class BuildArtifactItem(Base):
    __tablename__ = 'build_artifact_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    artifact_id: Mapped[str] = mapped_column(ForeignKey('build_artifacts.id', ondelete='CASCADE'), index=True)
    wkd_id: Mapped[str] = mapped_column(ForeignKey('wkds.id'))
    position: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSONB)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100), index=True)
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

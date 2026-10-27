from datetime import datetime
from pathlib import PurePosixPath
import re
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .models import ExecutionType, Stage, WkdStatus
from .richtext import rich_text_has_content, sanitize_rich_text

class LoginInput(BaseModel):
    username: str
    password: str

class OAuthCallbackInput(BaseModel):
    code: str = Field(min_length=1)
    state: str = Field(min_length=1)

class OperationInput(BaseModel):
    type: Literal['UPLOAD_FILE', 'LINUX_COMMAND', 'SCRIPT']
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_parameters(self):
        if self.type == 'UPLOAD_FILE':
            target_path = str(self.params.get('target_path', '')).strip()
            path = PurePosixPath(target_path)
            if not target_path or not path.is_absolute() or '..' in path.parts:
                raise ValueError('上传文件操作必须填写不包含 .. 的绝对目标路径')
            files = self.params.get('files')
            if not isinstance(files, list) or not files:
                raise ValueError('上传文件操作至少需要一个文件')
            names = []
            for item in files:
                if not isinstance(item, dict):
                    raise ValueError('上传文件配置格式不正确')
                name = str(item.get('name', '')).strip()
                if not name or name in ('.', '..') or PurePosixPath(name).name != name or '/' in name or '\\' in name:
                    raise ValueError(f'上传文件名不安全：{name or "空文件名"}')
                if not isinstance(item.get('content', ''), str):
                    raise ValueError(f'文件 {name} 的内容必须是文本')
                item['name'] = name
                item.setdefault('content', '')
                names.append(name)
            if len(names) != len(set(names)):
                raise ValueError('同一上传操作内文件名不能重复')
            permission = str(self.params.get('permission', '0644'))
            if not re.fullmatch(r'0?[0-7]{3}', permission):
                raise ValueError('文件权限必须是三位或四位八进制，例如 0644')
        if self.type == 'LINUX_COMMAND':
            if not str(self.params.get('command', '')).strip():
                raise ValueError('Linux 命令操作必须填写执行命令')
            if {'env', 'environment', 'environment_variables'} & set(self.params):
                raise ValueError('Linux 命令操作不支持环境变量参数')
        if self.type == 'SCRIPT' and not str(self.params.get('script', '')).strip():
            raise ValueError('脚本操作必须填写脚本内容')
        return self

class WkdInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    issue_no: str | None = None
    requirement_no: str | None = None
    project_id: str
    version_id: str
    found_version_id: str | None = None
    planned_version_id: str | None = None
    subsystem_id: str
    machine_ids: list[str] = Field(min_length=1)
    owner_id: str | None = None
    execution_type: ExecutionType
    activity_scene: Literal['首版本部署', 'ES集成活动', '常规版本升级']
    measure_type: Literal['事前规避措施', '事后恢复措施']
    remark: str | None = None
    stage: Stage | None = None
    custom_stage_name: str | None = None
    operations: list[OperationInput] = Field(default_factory=list)
    lock_version: int | None = None

    @model_validator(mode='after')
    def validate_business_rules(self):
        self.title = self.title.strip()
        self.description = self.description.strip()
        if not self.title or not self.description:
            raise ValueError('WKD 标题和规避措施描述不能为空')
        for field in ('issue_no', 'requirement_no', 'found_version_id', 'planned_version_id', 'owner_id', 'remark', 'custom_stage_name'):
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, value.strip() or None)
        if not self.issue_no and not self.requirement_no:
            raise ValueError('问题单号和需求单号不能同时为空')
        if self.issue_no and not self.found_version_id:
            raise ValueError('填写问题单号时，问题发现版本必填')
        if self.execution_type == ExecutionType.AUTOMATED:
            if not self.stage:
                raise ValueError('自动化执行必须选择执行阶段')
            if not self.operations:
                raise ValueError('自动化执行至少编排一个原子操作')
            if self.stage == Stage.CUSTOM and not self.custom_stage_name:
                raise ValueError('自定义阶段必须填写阶段名称')
        else:
            self.stage = None
            self.custom_stage_name = None
            self.operations = []
        return self

class CreateWkdInput(WkdInput):
    note: str | None = Field(default=None, max_length=10_000_000)

    @field_validator('note')
    @classmethod
    def sanitize_note(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        value = sanitize_rich_text(value)
        return value if rich_text_has_content(value) else None

class TransitionInput(BaseModel):
    note: str | None = Field(default=None, max_length=10_000_000)
    lock_version: int | None = None
    manager_id: str | None = None
    data: WkdInput | None = None

    @field_validator('note')
    @classmethod
    def sanitize_note(cls, value: str | None) -> str | None:
        if not isinstance(value, str):
            return value
        value = sanitize_rich_text(value)
        return value if rich_text_has_content(value) else None

    @field_validator('manager_id')
    @classmethod
    def trim_manager_id(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

class StateNoteInput(BaseModel):
    content: str = Field(min_length=1, max_length=10_000_000)

    @field_validator('content')
    @classmethod
    def sanitize_content(cls, value: str) -> str:
        value = sanitize_rich_text(value)
        if not rich_text_has_content(value):
            raise ValueError('状态说明不能为空')
        return value

class BuildInput(BaseModel):
    project_id: str
    machine_id: str
    wkd_ids: list[str] = Field(min_length=1)

class UploadInput(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    size: int = Field(gt=0)
    content_type: str | None = None
    wkd_id: str | None = None
    category: str = 'WKD'

class UploadCompleteInput(BaseModel):
    object_key: str
    filename: str
    size: int
    content_type: str | None = None
    sha256: str | None = None
    wkd_id: str | None = None
    category: str = 'WKD'

class EntityInput(BaseModel):
    name: str
    code: str | None = None
    project_id: str | None = None
    owner_id: str | None = None
    status: str = 'ENABLED'
    number: str | None = None
    model: str | None = None
    location: str | None = None
    baseline_date: str | None = None

class MemberInput(BaseModel):
    user_id: str
    role_id: str

class UserInput(BaseModel):
    username: str
    employee_id: str
    name: str
    email: str | None = None

class RoleInput(BaseModel):
    name: str
    description: str = ''
    permissions: list[str] = Field(default_factory=list)

class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class UserOut(ApiModel):
    id: str
    username: str
    employee_id: str
    name: str
    email: str | None
    is_superuser: bool

class TokenOut(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    user: UserOut
    permissions: list[str]

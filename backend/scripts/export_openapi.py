import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.main import app

DOCS = ROOT / 'docs'
DOCS.mkdir(exist_ok=True)
schema = app.openapi()
(DOCS / 'openapi.json').write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding='utf-8')

groups = defaultdict(list)
for path, operations in schema['paths'].items():
    for method, operation in operations.items():
        if method.lower() not in {'get', 'post', 'put', 'patch', 'delete'}:
            continue
        tags = operation.get('tags') or ['其他']
        groups[tags[0]].append((method.upper(), path, operation.get('summary') or operation.get('operationId', '')))

lines = [
    '# WMP 接口文档', '',
    f"- 后端版本：`{schema['info']['version']}`",
    '- API 前缀：`/api/v1`', '- Swagger UI：`/docs`', '- ReDoc：`/redoc`', '- OpenAPI：`/openapi.json`', '',
    '## 鉴权约定', '',
    '除本地登录、OIDC 登录发起/回调和健康检查外，所有接口均要求请求头 `Authorization: Bearer <token>`。',
    '项目内接口按“当前项目有效角色 → 按钮权限点”鉴权：具体项目成员角色优先；没有该项目成员关系时，回退到 `users.global_role_id` 对应的全局角色。全局角色使用户可访问所有正常项目，但不覆盖已经明确分配的项目角色。全局系统管理员拥有全部权限，前端隐藏按钮不能替代服务端鉴权。', '',
    '项目创建、修改、删除，平台用户预创建，全局角色模板增删改和全局审计日志仅允许系统管理员。项目管理员只能维护当前项目的版本、机台、子系统、成员及角色分配，角色模板仅可只读查看。', '',
    '非系统管理员查询项目内业务数据、平台用户目录、角色和权限时必须传入 `project_id`。业务数据不允许转移到其他项目；系统管理员和初始化用户角色不可作为项目或全局角色分配，项目管理员也不能修改或移除已有系统管理员成员，且项目必须至少保留一名项目管理员。停用项目和“用户初始化”项目禁止新建、流转和构建等实际业务。', '',
    '## 通用响应', '',
    '- `401`：未登录、令牌无效或用户停用。',
    '- `403`：非项目成员或缺少按钮权限点。',
    '- `409`：状态流转冲突、数据重复或乐观锁冲突。',
    '- `422`：字段约束或业务参数校验失败。', '',
]
for tag, endpoints in groups.items():
    lines.extend([f'## {tag}', '', '| 方法 | 路径 | 说明 |', '|---|---|---|'])
    lines.extend(f'| `{method}` | `{path}` | {summary} |' for method, path, summary in endpoints)
    lines.append('')

api_path = DOCS / 'api.md'
manual_marker = '## 数据统计作用域与筛选'
existing = api_path.read_text(encoding='utf-8') if api_path.exists() else ''
if manual_marker not in existing:
    raise RuntimeError(f'{api_path} 缺少 {manual_marker}，已停止以避免覆盖手工维护的接口说明')
manual_tail = existing.split(manual_marker, 1)[1]
api_path.write_text('\n'.join(lines) + '\n' + manual_marker + manual_tail, encoding='utf-8')
print(f'Exported {sum(map(len, groups.values()))} endpoints to {DOCS}')

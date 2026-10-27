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
lines = ['# WMP 接口文档', '', f"- 后端版本：`{schema['info']['version']}`", '- API 前缀：`/api/v1`', '- Swagger UI：`/docs`', '- ReDoc：`/redoc`', '- OpenAPI：`/openapi.json`', '', '## 鉴权约定', '', '除本地登录、OIDC 登录发起/回调和健康检查外，所有接口均要求请求头 `Authorization: Bearer <token>`。', '服务端按“项目成员 → 项目角色 → 按钮权限点”鉴权；全局系统管理员拥有全部权限。前端隐藏按钮不能替代服务端鉴权。', '', '## 通用响应', '', '- `401`：未登录、令牌无效或用户停用。', '- `403`：非项目成员或缺少按钮权限点。', '- `409`：状态流转冲突、数据重复或乐观锁冲突。', '- `422`：字段约束或业务参数校验失败。', '']
for tag, endpoints in groups.items():
    lines.extend([f'## {tag}', '', '| 方法 | 路径 | 说明 |', '|---|---|---|'])
    lines.extend(f'| `{method}` | `{path}` | {summary} |' for method, path, summary in endpoints)
    lines.append('')
lines.extend(['## 企业 OIDC 登录', '', '`POST /api/v1/auth/oauth/login` 返回企业授权地址，并通过 HttpOnly、SameSite=Lax Cookie 保存有时效的 State 和 Nonce。浏览器跳转企业 IdP 后，前端回调页将 `code`、`state` 提交到 `POST /api/v1/auth/oauth/callback`。', '', '后端校验 State、Nonce、ID Token 签名、Issuer、Audience 和有效期，再将 OIDC `sub` 绑定到已导入的 WMP 用户。未知用户不自动注册；系统管理员不能通过 OAuth 登录；普通用户登录后仍按 WMP 项目角色和按钮权限点鉴权。', '', 'OIDC 通过 `OAUTH_*` 环境变量配置。生产回调必须使用 HTTPS，测试和生产应使用独立 IdP Client。', '', '## 保存与提交边界', '', '首次创建使用 `POST /api/v1/wkds`。创建后的普通“保存”仅是浏览器本地草稿，不调用后端，也不产生后端历史。只有状态流转才正式提交数据。', '', '`submit_verify`、`submit_review` 的请求体必须同时携带 `data`（完整 WKD 字段和原子操作）、`note`、`lock_version`；`submit_review` 还必须携带 `manager_id`。后端在同一事务中校验并写入业务数据、处理人、状态历史和属性差异。', '', '## 历史记录结构', '', '`GET /api/v1/wkds/{wkd_id}/history` 返回状态流转、状态说明和属性变更记录。`note` 为安全富文本说明；`changes` 为属性变更数组，无变更时为空数组。', '', '```json', '{', '  "field": "title",', '  "label": "WKD 标题",', '  "before": "旧标题",', '  "after": "新标题"', '}', '```', '', '数组元素中的 `before`、`after` 可能是字符串、字符串数组或 `null`。本地草稿不生成历史；属性差异随正式状态流转记录。', '', '## 六状态状态机约束', '', '```text', 'NEW_WKD --提交自验证--> VERIFY --提交审核--> REVIEW', '   |                       |                  |', '   |                       |                  +--审核通过--> APPROVED', '   |                       |                  |                   |', '   |                       |                  +--驳回--> VERIFY    +--发起禁用--> DISABLE_CONFIRM', '   |                       |                                            |            |', '   +-------禁用------------+-------禁用-----------> DISABLED <---确认禁用--+            +--拒绝禁用--> APPROVED', '```', '', '`REVIEW` 仅允许审核通过或驳回；`DISABLE_CONFIRM` 仅允许确认禁用或拒绝禁用。两类状态完全独立，审核或确认意见均必填。`APPROVED` 不允许直接禁用，`DISABLED` 为最终只读状态。', '', '`NEW_WKD`、`VERIFY` 的当前处理人为责任人；`REVIEW`、`DISABLE_CONFIRM` 为指派软件经理；`APPROVED`、`DISABLED` 不保留待处理人。`submit_review`、`request_disable` 必须通过 `manager_id` 指派具备 `wkd.review` 权限的项目成员。非系统管理员只能由当前处理人执行其状态允许的流转。', '', '## 原子操作与构建制品', '', '`UPLOAD_FILE` 的 `params.files` 至少包含一个文件，支持同一操作上传多个文件；每项包含 `name` 与 `content`，公共参数为 `target_path`、`overwrite`、`permission`。`LINUX_COMMAND` 不包含环境变量参数。', '', '调试构建与正式构建返回真实 `tar.gz` 制品，包含通用入口 `wmp_entry.py`、`MANIFEST.json`、`WKD_LIST.json` 和 `packages/<WKD编号>/` 下的执行清单及实际上传文件。目标机使用 `python3 wmp_entry.py <WKD编号> <阶段参数>` 执行；入口仅依赖 Python 标准库，操作失败返回非零退出码。', ''])
(DOCS / 'api.md').write_text('\n'.join(lines), encoding='utf-8')
print(f'Exported {sum(map(len, groups.values()))} endpoints to {DOCS}')

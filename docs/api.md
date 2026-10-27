# WMP 接口文档

- 后端版本：`1.4.0`
- API 前缀：`/api/v1`
- Swagger UI：`/docs`
- ReDoc：`/redoc`
- OpenAPI：`/openapi.json`

## 鉴权约定

除本地登录、OIDC 登录发起/回调和健康检查外，所有接口均要求请求头 `Authorization: Bearer <token>`。
服务端按“项目成员 → 项目角色 → 按钮权限点”鉴权；全局系统管理员拥有全部权限。前端隐藏按钮不能替代服务端鉴权。

## 通用响应

- `401`：未登录、令牌无效或用户停用。
- `403`：非项目成员或缺少按钮权限点。
- `409`：状态流转冲突、数据重复或乐观锁冲突。
- `422`：字段约束或业务参数校验失败。

## 认证与用户

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/auth/login` | 本地账号登录（开发调试或生产系统管理员） |
| `POST` | `/api/v1/auth/oauth/login` | 创建企业 OIDC 授权地址并写入防 CSRF 状态 Cookie |
| `POST` | `/api/v1/auth/oauth/callback` | 校验 OIDC 回调并绑定已导入的 WMP 用户 |
| `GET` | `/api/v1/auth/me` | 获取当前用户 |
| `GET` | `/api/v1/auth/permissions` | 获取当前用户按钮权限点；传项目 ID 时按项目角色计算 |
| `POST` | `/api/v1/auth/logout` | 退出登录并记录审计 |
| `POST` | `/api/v1/auth/password/forgot` | 忘记密码入口 |

## 首页、通知与数据统计

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/dashboard/summary` | 首页指标、最近更新与待办数据 |
| `GET` | `/api/v1/notifications` | 查询当前用户通知 |
| `POST` | `/api/v1/notifications/read` | 将全部通知标记为已读 |
| `GET` | `/api/v1/statistics` | 按项目、版本、机台、子系统和日期查询统计数据及流转趋势 |
| `GET` | `/api/v1/statistics/export` | 鉴权并导出统计明细 CSV |
| `GET` | `/api/v1/audit-logs` | 查询重要操作审计日志 |

## WKD 全生命周期

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/wkds` | 查询 WKD 列表（搜索、标签及机台、子系统、责任人、阶段、状态多选筛选） |
| `POST` | `/api/v1/wkds` | 首次创建 WKD，保存完整数据与新建说明 |
| `GET` | `/api/v1/wkds/reviewers` | 查询当前项目可指派的软件经理 |
| `GET` | `/api/v1/wkds/{wkd_id}` | 获取 WKD 详情、操作编排和字段属性 |
| `POST` | `/api/v1/wkds/{wkd_id}/transitions/{action}` | 状态流转；提交类操作携带完整数据，指派类操作必须传入 manager_id |
| `GET` | `/api/v1/wkds/{wkd_id}/history` | 查询状态流转、属性变更和说明历史 |

## 调试构建、正式构建与制品

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/builds/eligible` | 查询可构建 WKD；正式构建按项目和机台返回全部 APPROVED |
| `POST` | `/api/v1/builds/{kind}` | 执行调试或正式构建，生成 tar.gz 并上传 RustFS |
| `GET` | `/api/v1/artifacts` | 查询基线制品或构建记录 |
| `GET` | `/api/v1/artifacts/{artifact_id}/download` | 鉴权后获取制品预签名下载地址 |

## 附件与 RustFS 存储

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/files/upload-url` | 鉴权并创建附件预签名上传地址 |
| `POST` | `/api/v1/files/complete` | 校验 RustFS 文件并保存附件元数据 |
| `GET` | `/api/v1/files/attachments` | 查询 WKD 附件列表 |
| `GET` | `/api/v1/files/attachments/{attachment_id}/download` | 鉴权后获取附件预签名下载地址 |

## 系统管理与基础数据

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/bootstrap/options` | 获取可访问项目及版本、机台、子系统、责任人与角色选项 |
| `GET` | `/api/v1/business/{resource}` | 查询项目、版本、机台或子系统列表 |
| `POST` | `/api/v1/business/{resource}` | 新增项目、版本、机台或子系统 |
| `PUT` | `/api/v1/business/{resource}/{item_id}` | 修改业务基础数据 |
| `DELETE` | `/api/v1/business/{resource}/{item_id}` | 删除未被引用的业务基础数据 |
| `GET` | `/api/v1/users` | 按姓名、用户名或工号查询平台用户 |
| `POST` | `/api/v1/users` | 预创建本地用户（不自动分配项目权限） |
| `GET` | `/api/v1/projects/{project_id}/members` | 查询项目成员及项目角色 |
| `POST` | `/api/v1/projects/{project_id}/members` | 添加项目成员并分配角色 |
| `PUT` | `/api/v1/projects/{project_id}/members/{member_id}` | 调整成员在当前项目中的角色 |
| `DELETE` | `/api/v1/projects/{project_id}/members/{member_id}` | 将成员移出项目 |
| `GET` | `/api/v1/roles` | 查询角色及按钮权限点 |
| `POST` | `/api/v1/roles` | 新增自定义角色 |
| `GET` | `/api/v1/permissions` | 获取全部可配置按钮权限点 |
| `PUT` | `/api/v1/roles/{role_id}` | 编辑角色及按钮权限 |
| `DELETE` | `/api/v1/roles/{role_id}` | 删除未被使用的自定义角色 |

## 系统

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 服务健康检查 |

## 企业 OIDC 登录

`POST /api/v1/auth/oauth/login` 返回企业授权地址，并通过 HttpOnly、SameSite=Lax Cookie 保存有时效的 State 和 Nonce。浏览器跳转企业 IdP 后，前端回调页将 `code`、`state` 提交到 `POST /api/v1/auth/oauth/callback`。

后端校验 State、Nonce、ID Token 签名、Issuer、Audience 和有效期，再将 OIDC `sub` 绑定到已导入的 WMP 用户。未知用户不自动注册；系统管理员不能通过 OAuth 登录；普通用户登录后仍按 WMP 项目角色和按钮权限点鉴权。

OIDC 通过 `OAUTH_*` 环境变量配置。生产回调必须使用 HTTPS，测试和生产应使用独立 IdP Client。

## 保存与提交边界

首次创建使用 `POST /api/v1/wkds`。创建后的普通“保存”仅是浏览器本地草稿，不调用后端，也不产生后端历史。只有状态流转才正式提交数据。

`submit_verify`、`submit_review` 的请求体必须同时携带 `data`（完整 WKD 字段和原子操作）、`note`、`lock_version`；`submit_review` 还必须携带 `manager_id`。后端在同一事务中校验并写入业务数据、处理人、状态历史和属性差异。

## 历史记录结构

`GET /api/v1/wkds/{wkd_id}/history` 返回状态流转、状态说明和属性变更记录。`note` 为安全富文本说明；`changes` 为属性变更数组，无变更时为空数组。

```json
{
  "field": "title",
  "label": "WKD 标题",
  "before": "旧标题",
  "after": "新标题"
}
```

数组元素中的 `before`、`after` 可能是字符串、字符串数组或 `null`。本地草稿不生成历史；属性差异随正式状态流转记录。

## 六状态状态机约束

```text
NEW_WKD --提交自验证--> VERIFY --提交审核--> REVIEW
   |                       |                  |
   |                       |                  +--审核通过--> APPROVED
   |                       |                  |                   |
   |                       |                  +--驳回--> VERIFY    +--发起禁用--> DISABLE_CONFIRM
   |                       |                                            |            |
   +-------禁用------------+-------禁用-----------> DISABLED <---确认禁用--+            +--拒绝禁用--> APPROVED
```

`REVIEW` 仅允许审核通过或驳回；`DISABLE_CONFIRM` 仅允许确认禁用或拒绝禁用。两类状态完全独立，审核或确认意见均必填。`APPROVED` 不允许直接禁用，`DISABLED` 为最终只读状态。

`NEW_WKD`、`VERIFY` 的当前处理人为责任人；`REVIEW`、`DISABLE_CONFIRM` 为指派软件经理；`APPROVED`、`DISABLED` 不保留待处理人。`submit_review`、`request_disable` 必须通过 `manager_id` 指派具备 `wkd.review` 权限的项目成员。非系统管理员只能由当前处理人执行其状态允许的流转。

## 原子操作与构建制品

`UPLOAD_FILE` 的 `params.files` 至少包含一个文件，支持同一操作上传多个文件；每项包含 `name` 与 `content`，公共参数为 `target_path`、`overwrite`、`permission`。`LINUX_COMMAND` 不包含环境变量参数。

调试构建与正式构建返回真实 `tar.gz` 制品，包含通用入口 `wmp_entry.py`、`MANIFEST.json`、`WKD_LIST.json` 和 `packages/<WKD编号>/` 下的执行清单及实际上传文件。目标机使用 `python3 wmp_entry.py <WKD编号> <阶段参数>` 执行；入口仅依赖 Python 标准库，操作失败返回非零退出码。

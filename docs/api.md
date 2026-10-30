# WMP 接口文档

- 后端版本：`1.8.0`
- API 前缀：`/api/v1`
- Swagger UI：`/docs`
- ReDoc：`/redoc`
- OpenAPI：`/openapi.json`

## 鉴权约定

除本地登录、OIDC 登录发起/回调和健康检查外，所有接口均要求请求头 `Authorization: Bearer <token>`。
项目内接口按“当前项目有效角色 → 按钮权限点”鉴权：具体项目成员角色优先；没有该项目成员关系时，回退到 `users.global_role_id` 对应的全局角色。全局角色使用户可访问所有正常项目，但不覆盖已经明确分配的项目角色。全局系统管理员拥有全部权限，前端隐藏按钮不能替代服务端鉴权。

项目创建、修改、删除，平台用户预创建，全局角色模板增删改和全局审计日志仅允许系统管理员。项目管理员只能维护当前项目的版本、机台、子系统、成员及角色分配，角色模板仅可只读查看。

非系统管理员查询项目内业务数据、平台用户目录、角色和权限时必须传入 `project_id`。业务数据不允许转移到其他项目；系统管理员和初始化用户角色不可作为项目或全局角色分配，项目管理员也不能修改或移除已有系统管理员成员，且项目必须至少保留一名项目管理员。停用项目和“用户初始化”项目禁止新建、流转和构建等实际业务。

## 通用响应

- `401`：未登录、令牌无效或用户停用。
- `403`：非项目成员或缺少按钮权限点。
- `409`：状态流转冲突、数据重复或乐观锁冲突。
- `422`：字段约束或业务参数校验失败。

## 认证与用户

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/auth/login` | 本地账号登录，支持用户名或唯一工号；用户名重名时须用工号（开发调试或生产系统管理员） |
| `POST` | `/api/v1/auth/oauth/login` | 创建企业 OIDC 授权地址并写入防 CSRF 状态 Cookie |
| `POST` | `/api/v1/auth/oauth/callback` | 校验 OIDC 回调并绑定或自动注册 WMP 用户 |
| `GET` | `/api/v1/auth/me` | 获取当前用户 |
| `GET` | `/api/v1/auth/permissions` | 获取当前用户按钮权限点；传项目 ID 时按项目角色计算 |
| `POST` | `/api/v1/auth/logout` | 退出登录并记录审计 |
| `POST` | `/api/v1/auth/password/forgot` | 忘记密码入口 |

## 首页与通知

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/dashboard/summary` | 首页指标、最近更新与待办数据 |
| `GET` | `/api/v1/notifications` | 查询当前用户通知 |
| `POST` | `/api/v1/notifications/read` | 将全部通知标记为已读 |
| `GET` | `/api/v1/audit-logs` | 查询全局重要操作审计日志（仅系统管理员） |

## 数据统计

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/statistics/options` | 获取全部统计筛选项（所有已登录用户） |
| `GET` | `/api/v1/statistics` | 项目内或全局多维统计（所有已登录用户，多选筛选、趋势与分布） |
| `GET` | `/api/v1/statistics/export` | 按相同条件导出完整统计明细 XLSX（所有已登录用户） |

## WKD 全生命周期

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/wkds` | 查询轻量 WKD 列表，不返回 operations；支持搜索、标签及多维多选筛选 |
| `POST` | `/api/v1/wkds` | 首次创建 WKD，幂等绑定已完成草稿附件 |
| `GET` | `/api/v1/wkds/reviewers` | 查询当前项目可指派的软件经理，包含有效的全局软件经理 |
| `GET` | `/api/v1/wkds/{wkd_id}` | 获取 WKD 详情、完整操作编排和字段属性 |
| `POST` | `/api/v1/wkds/{wkd_id}/transitions/{action}` | 状态流转；所有操作必须携带 lock_version，提交类携带完整数据，指派类携带 manager_id |
| `GET` | `/api/v1/wkds/{wkd_id}/history` | 查询状态流转、属性变更和说明历史 |

## 调试构建、正式构建与制品

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/builds/eligible` | 查询轻量可构建 WKD 列表，不返回 operations；正式构建仅返回 APPROVED |
| `POST` | `/api/v1/builds/{kind}` | 同步执行构建；1～200 个不重复 WKD，普通附件总量默认不超过 2 GB |
| `GET` | `/api/v1/artifacts` | 查询轻量制品记录，不返回明细中的 WKD snapshot 正文 |
| `GET` | `/api/v1/artifacts/{artifact_id}/download` | 鉴权后获取制品预签名下载地址 |

## 附件与 RustFS 存储

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/v1/files/upload-sessions` | 创建草稿或既有 WKD 附件上传会话 |
| `GET` | `/api/v1/files/upload-sessions/{session_id}` | 恢复本人上传会话及附件状态 |
| `POST` | `/api/v1/files/upload-sessions/{session_id}/uploads` | 初始化附件直传或分片上传 |
| `POST` | `/api/v1/files/uploads/{attachment_id}/part-url` | 获取本人附件的单个分片预签名地址 |
| `POST` | `/api/v1/files/uploads/{attachment_id}/complete` | 核验对象并完成本人附件上传 |
| `DELETE` | `/api/v1/files/uploads/{attachment_id}` | 取消未绑定附件并清理存储对象 |
| `POST` | `/api/v1/files/upload-url` | 兼容接口：为既有 WKD 创建单次上传地址 |
| `POST` | `/api/v1/files/complete` | 兼容接口：完成既有 WKD 单次上传 |
| `GET` | `/api/v1/files/attachments` | 查询 WKD 已完成附件列表 |
| `GET` | `/api/v1/files/attachments/{attachment_id}/download` | 鉴权后获取附件预签名下载地址 |

## 系统管理与基础数据

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/bootstrap/options` | 获取可访问项目及版本、机台、子系统、责任人与可分配角色选项 |
| `GET` | `/api/v1/business/{resource}` | 查询项目、版本、机台或子系统列表 |
| `POST` | `/api/v1/business/{resource}` | 新增项目、版本、机台或子系统 |
| `PUT` | `/api/v1/business/{resource}/{item_id}` | 修改业务基础数据 |
| `DELETE` | `/api/v1/business/{resource}/{item_id}` | 删除未被引用的业务基础数据 |
| `GET` | `/api/v1/users` | 按用户名、工号或部门搜索可加入当前项目的平台用户 |
| `POST` | `/api/v1/users` | 预创建本地用户（仅系统管理员，不自动分配项目权限） |
| `GET` | `/api/v1/global-access/users` | 查询平台用户的所有项目角色授权（仅系统管理员） |
| `PUT` | `/api/v1/users/{user_id}/global-role` | 授予或撤销用户的所有项目角色（仅系统管理员） |
| `GET` | `/api/v1/projects/{project_id}/members` | 查询项目成员及项目角色 |
| `POST` | `/api/v1/projects/{project_id}/members` | 添加项目成员并分配非全局项目角色 |
| `GET` | `/api/v1/projects/{project_id}/members/import-template` | 下载项目用户批量初始化 Excel 模板 |
| `POST` | `/api/v1/projects/{project_id}/members/bulk-preview` | 解析并校验批量初始化文件，返回逐行预览 |
| `POST` | `/api/v1/projects/{project_id}/members/bulk-import` | 确认批量创建平台用户并初始化当前项目成员 |
| `PUT` | `/api/v1/projects/{project_id}/members/{member_id}` | 调整成员在当前项目中的角色 |
| `DELETE` | `/api/v1/projects/{project_id}/members/{member_id}` | 将成员移出项目 |
| `GET` | `/api/v1/roles` | 查询全局角色模板及按钮权限点（项目成员只读） |
| `POST` | `/api/v1/roles` | 新增全局自定义角色（仅系统管理员） |
| `GET` | `/api/v1/permissions` | 获取全部可配置项目权限点（项目成员只读） |
| `PUT` | `/api/v1/roles/{role_id}` | 编辑全局角色及按钮权限（仅系统管理员） |
| `DELETE` | `/api/v1/roles/{role_id}` | 删除未被使用的全局自定义角色（仅系统管理员） |

## 系统

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 服务健康检查 |

## 数据统计作用域与筛选

`GET /api/v1/statistics`、`GET /api/v1/statistics/options` 与 `GET /api/v1/statistics/export` 对所有已登录用户开放，不配置角色权限点；未登录访问仍返回 `401`。项目统计（`scope=project`）必须且只能传入一个 `project_ids`；全局统计（`scope=global`）可传多个项目或不传项目查询全部。页面、筛选项和导出均不校验项目成员或角色。

多选参数包括项目、所属版本、问题发现版本、规划解决版本、机台、子系统、状态、执行类型、活动场景、措施类型、责任人、当前处理人与执行阶段。`keyword` 匹配 WKD 编号、标题、问题单号和需求单号；`date_field=created|updated` 配合 `start_date`、`end_date` 筛选创建或更新时间，单次统计周期不超过 366 天。所有筛选同时作用于指标、趋势、分布、项目对比、明细和导出。

新增趋势按 WKD 创建事件统计；审核趋势按 APPROVE 历史事件的发生周期独立统计，以前创建、本周期审核的记录也会计入。`approval_rate` 表示“当前审核通过占比”，不是历史流转转化率。统计明细使用轻量 WKD DTO，不返回 `operations`。

导出接口返回标准 `.xlsx` 文件，媒体类型为 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`，下载文件名为 `wmp-statistics.xlsx`。工作表名为“统计明细”，包含 18 列，首行冻结并启用筛选；后端使用临时文件缓冲并流式响应，用户可控文本会中和公式危险前缀。前端演示模式同样生成真实 XLSX，不提供 CSV 导出。

## 所有项目授权

`GET /api/v1/global-access/users` 查询平台用户的全局角色，`PUT /api/v1/users/{user_id}/global-role` 授予、调整或撤销全局角色，两个接口均仅允许系统管理员。全局角色保存于 `users.global_role_id`，不创建项目成员关系，不覆盖已明确分配的项目角色；角色仍被全局授权使用时不可删除。没有项目成员关系时，全局角色参与实际鉴权并开放所有正常项目；全局软件经理可进入审核人候选。

## 企业 OIDC 登录

`POST /api/v1/auth/oauth/login` 返回企业授权地址，并通过 HttpOnly、SameSite=Lax Cookie 保存有时效的 State 和 Nonce。浏览器跳转企业 IdP 后，前端回调页将 `code`、`state` 提交到 `POST /api/v1/auth/oauth/callback`。

后端校验 State、Nonce、ID Token 签名、Issuer、Audience 和有效期。已导入用户首次只按工号绑定 OIDC `sub`，后续按 `sub` 识别；用户名允许重复，缺少工号时不能按用户名绑定。未注册的企业用户会自动创建平台账号，并加入“用户初始化”占位项目。该项目的内置“初始化用户”角色仅有 `home.view`，不能用于实际业务，也不能通过普通授权接口分配或修改。真实项目权限由项目管理员后续分配；系统管理员不能通过 OAuth 登录。

OIDC 通过 `OAUTH_*` 环境变量配置。生产回调必须使用 HTTPS，测试和生产应使用独立 IdP Client。

## 项目成员批量初始化

`GET /api/v1/projects/{project_id}/members/import-template` 下载五列 Excel 模板：工号（必填、唯一）、用户名（必填、允许重复）、所属部门（选填）、项目角色（选填）、邮箱（选填）。`POST /api/v1/projects/{project_id}/members/bulk-preview` 以 multipart 上传 `default_role_id` 和 `.xlsx/.csv` 文件，返回汇总及逐行错误；单次最多 5000 行、文件最大 10 MB。

全部行无错误后，前端将预览数据提交到 `POST /api/v1/projects/{project_id}/members/bulk-import`。确认接口会重新鉴权和逐行校验，不信任预览结果；已有项目成员保留原角色，已有平台用户仅新增成员关系，新用户按工号创建。三个接口均要求目标项目的 `project.member.manage` 权限，系统管理员和初始化用户角色不可通过导入分配。

## 草稿附件与分片上传

新建 WKD 前，先调用 `POST /api/v1/files/upload-sessions` 创建当前项目的上传会话，再通过会话初始化附件。小于 64 MB 默认单次直传，达到阈值后按 16 MB 分片；分片地址逐片申请，完成后由后端核验 RustFS 对象和大小并保存 SHA-256。

草稿附件仅上传人可恢复、下载、取消和绑定。创建 WKD 时通过 `attachment_ids` 显式选择已完成附件，并携带 `idempotency_key` 防止重试重复创建。跨项目、他人、未绑定状态不正确或已过期的附件都会被拒绝。

上传会话默认 24 小时过期，后端每小时清理过期未绑定附件和分片。`/files/upload-url` 与 `/files/complete` 仅作为既有 WKD 的兼容接口保留，不再接受未关联 WKD 的上传。

既有 WKD 的上传权限按状态独立控制：`NEW_WKD`、`VERIFY` 仅当前处理人可上传，且要求 `wkd.edit` 与 `files.upload`；`APPROVED` 允许具有 `files.upload` 的项目用户受控补传；`REVIEW`、`DISABLE_CONFIRM`、`DISABLED` 禁止上传并返回 `409`。会话初始化、分片地址申请和完成上传都会重新校验状态并锁定 WKD，旧会话不能跨状态完成上传。

## 保存与提交边界

首次创建使用 `POST /api/v1/wkds`，可同时携带 `attachment_ids` 与 `idempotency_key`。创建后的“保存本地草稿”仅写当前标签页的浏览器存储，不调用后端，也不产生后端历史。只有状态流转才正式提交数据。

所有状态流转的请求体必须携带 `lock_version >= 1`；后端使用 `SELECT ... FOR UPDATE` 锁定 WKD 后比较版本，版本冲突返回 `409`。`submit_verify`、`submit_review` 还必须携带 `data`（完整 WKD 字段和原子操作）及 `note`；`submit_review` 还必须携带 `manager_id`。后端在同一事务中校验并写入业务数据、处理人、状态历史和属性差异。

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

`REVIEW` 仅允许审核通过或驳回；`DISABLE_CONFIRM` 仅允许确认禁用或拒绝禁用。两类状态完全独立，审核或确认意见均必填。`APPROVED` 不允许直接禁用，业务字段只读但允许按附件规则补传资料；`DISABLED` 为最终只读状态并禁止上传。

`NEW_WKD`、`VERIFY` 的当前处理人为责任人；`REVIEW`、`DISABLE_CONFIRM` 为指派软件经理；`APPROVED`、`DISABLED` 不保留待处理人。`submit_review`、`request_disable` 必须通过 `manager_id` 指派具有 `wkd.review` 有效权限的启用用户，候选人可以来自项目成员角色或全局角色。非系统管理员只能由当前处理人执行其状态允许的流转。

## 原子操作与构建制品

`UPLOAD_FILE` 的 `params.files` 包含 1～100 个文件，页面通过 Upload 组件从本地多选实际文件，不再手工填写文件名或内容。每项包含 `name`、`content` 和 `size`；新选择文件使用 `encoding=base64` 保存原始字节，兼容无 `encoding` 的 UTF-8 文本历史数据。单文件上限 20 MB、单 WKD 原子文件总量上限 100 MB，同一操作内文件名不可重复，公共参数为 `target_path`、`overwrite`、`permission`。`LINUX_COMMAND` 不包含环境变量参数，工作目录必须是不含 `..` 的绝对路径，超时为 1～86400 秒，期望退出码为 0～255；脚本仅支持 Python 和 Shell。

调试构建与正式构建返回真实 `tar.gz` 制品，包含通用入口 `wmp_entry.py`、`MANIFEST.json`、`WKD_LIST.json` 和 `packages/<WKD编号>/` 下的执行清单、原子操作文件及 WKD 普通附件。人工操作 WKD 同样允许构建；已绑定的 `READY` 普通附件流式写入子包 `attachments/` 并校验大小和 SHA-256，只随包携带、不自动执行。目标机使用 `python3 wmp_entry.py <阶段参数>` 按 `MANIFEST.json` 顺序执行全部匹配 WKD，可用 `--wkd <WKD编号>` 指定单个 WKD、`--list` 查看内容；旧的 `python3 wmp_entry.py <WKD编号> <阶段参数>` 调用保持兼容。入口仅依赖 Python 标准库，默认跳过不匹配阶段的 WKD，无匹配项或任一操作失败返回非零退出码。

# WMP v1.8 后端开发文档

## 1. 技术栈与结构

- Python 3.11／3.12、FastAPI、Uvicorn。
- SQLAlchemy 2、psycopg 3、PostgreSQL。
- Pydantic Settings、PyJWT、HTTPX。
- Boto3 对接 RustFS S3 兼容接口。
- openpyxl 生成统计 XLSX。

```text
backend/app/
├── main.py                 # 应用装配、启动 DDL、种子和清理任务
├── config.py               # 环境配置与生产 fail-closed 校验
├── db.py                   # Engine、Session、Base
├── models.py               # 数据表与关系
├── schemas.py              # 请求/响应模型和业务输入校验
├── deps.py                 # 当前用户、有效角色、权限与项目边界
├── security.py             # 密码哈希和 JWT
├── oauth.py                # OIDC 授权码、State、Nonce、JWKS 与绑定
├── lifecycle.py            # 六状态流转规则
├── services.py             # WKD、权限、历史等业务服务
├── attachment_service.py   # 上传会话、附件绑定和清理
├── storage.py              # RustFS 对象与预签名地址
├── builder.py              # 真实 tar.gz 构建与执行包
├── member_import.py        # 五列成员批量初始化
├── richtext.py             # 富文本白名单清洗
└── routers/                # auth、dashboard、statistics、wkd、builds、files、admin
```

## 2. 本地运行与测试

在工程根目录：

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env
npm run backend:dev
npm run backend:test
npm run docs:api
```

后端默认监听 `8000`，Swagger 为 `/docs`，OpenAPI 为 `/openapi.json`，健康检查为 `/health`。`Settings` 从后端工作目录的 `.env` 读取配置，不要通过修改 `config.py` 默认值写入真实密钥。

本工程自带一套仅用于本地开发的数据库与对象存储（PostgreSQL 17 与 RustFS，位于 `.cache/services/`，数据在 `.cache/services/data/`），可用统一脚本一键管理全部四个本地服务：

```bash
./scripts/dev-services.sh start    # PostgreSQL + RustFS + 后端(8000) + 前端(7100)
./scripts/dev-services.sh status   # 查看状态
./scripts/dev-services.sh stop     # 停止全部
```

脚本带就绪探测（`pg_isready`、RustFS 桶/CORS 自检、`/health`、前端页面），日志在 `.cache/services/logs/`。该目录与脚本仅服务于本地开发，不属于测试/生产部署路径。

## 3. 请求与鉴权约定

除认证和健康检查外，接口通过 `current_user` 获取启用用户。项目按钮使用：

```python
authorize(db, user, 'wkd.edit', project_id)
```

全局操作使用 `require_superuser(user)`，不能用项目角色模拟全局管理权限。

有效角色规则集中在 `deps.user_permissions()`：

- 系统管理员返回 `*`。
- 当前项目有成员记录时，只使用明确项目角色。
- 当前项目无成员记录时，回退到 `users.global_role_id`。
- 不传项目 ID 的权限集合合并项目角色和全局角色。

新增项目接口时必须明确 `project_id` 来源并验证资源归属，禁止只根据前端隐藏按钮授权。写实际业务前调用 `ensure_operational_project()`，停用项目和 `WMP-USER-INIT` 均不得承载新业务。

## 4. WKD 创建与状态流转

- 创建服务负责字段校验、项目内资源关系、责任人、编号、附件绑定和幂等。
- 编号使用当日序列、事务和唯一约束，禁止在应用外自行拼接序号。
- 所有状态流转先读取 `lifecycle.transition_rule()`，再鉴权、检查当前处理人和 `lock_version`。
- 后端使用 `SELECT ... FOR UPDATE` 锁定 WKD；版本过期返回 409，禁止最后写入者无条件覆盖。
- `submit_verify`／`submit_review` 携带完整业务数据，属性变化以结构化 `changes` 写入 `wkd_history`。
- 审核人必须具有当前项目有效 `wkd.review` 权限，可以来自项目成员或全局角色。
- 业务字段、处理人、状态和历史必须在同一数据库事务提交。

新增流转动作时，需要同时修改规则、权限种子、前端状态面板、历史展示和正反向测试，不能只加路由。

## 5. 原子操作与输入校验

请求模型和服务层必须同时保持以下约束：

- 自动化执行要求阶段和至少一个操作；人工执行清空阶段与操作。
- 自定义阶段在所属版本内唯一，并使用安全 ASCII 参数格式。
- Linux 命令无环境变量，工作目录为不含 `..` 的绝对路径。
- 上传目标路径同样为安全绝对路径；文件名为单文件安全名称。
- 原子上传文件支持多文件和 Base64 二进制，限制单文件、单操作数量和 WKD 总量。
- 所有列表输入去重并限制批次，不信任前端提交的资源所属项目。

高风险执行内容只在构建后的隔离目标环境运行；FastAPI 服务本身不执行 WKD 中的 Linux 命令或脚本。

## 6. 附件与 RustFS

- 上传会话区分新建草稿与既有 WKD，记录上传人、项目、状态和过期时间。
- 初始化、分片地址申请和完成上传都重新校验用户、项目和 WKD 状态。
- 后端向 RustFS 核实对象和大小，接收 SHA-256 后才把附件置为 `READY`。
- 创建 WKD 只绑定显式 `attachment_ids` 中属于当前用户、当前项目、未绑定且 `READY` 的附件。
- `REVIEW`、`DISABLE_CONFIRM`、`DISABLED` 禁止上传；`APPROVED` 仅允许受控补传资料。
- 过期清理由后台循环执行，PostgreSQL advisory lock 防止多进程重复清理。
- 对象存储不属于数据库事务；构建和绑定失败需要补偿删除或生命周期兜底。

## 7. 构建服务

- 调试和正式构建共享构建服务，候选状态和按钮权限不同。
- 单次 1～200 个不重复 WKD，普通附件总量受 `MAX_BUILD_ATTACHMENT_BYTES` 限制。
- 制品明细保存 WKD 不可变快照和顺序；默认顺序为创建时间升序。
- 普通附件和原子文件分别写入 `attachments/` 与 `files/`，读取时校验大小和 SHA-256。
- 构建使用流式读写，避免把大附件和完整制品一次性载入内存。
- RustFS 上传成功后数据库失败时补偿删除对象。

当前构建仍是同步请求，没有后台进度和幂等。修改为任务化前，不要移除代理超时、批次限制和补偿逻辑。

## 8. 统计与读模型

- 高频列表不得返回 `operations` 或制品明细中的完整 WKD 快照。
- 工作台计数和首页指标使用 SQL COUNT；详情才加载完整编排。
- 项目统计必须一个项目，全局统计允许多项目；当前产品决策是所有已登录用户均可查询与导出。
- 筛选、指标、趋势、分布、明细和 XLSX 必须共用同一条件。
- 新增趋势按创建事件，审核趋势按 APPROVE 历史事件，不得混用 WKD 创建时间。
- XLSX 使用临时文件缓冲流式返回，并中和公式危险前缀。

统计目前仍在应用层全量聚合，明细未后端分页；新增大字段或复杂筛选前先评估内存和查询成本。

## 9. 数据库与启动任务

`main.py` 当前执行 `Base.metadata.create_all()` 和幂等 `ALTER`／索引语句，然后运行 `seed()`。因此：

- 数据库账号当前需要应用 schema 的 DDL 权限。
- 新列必须考虑旧数据回填、空值、默认值、唯一约束和多实例启动。
- 不要直接修改已发布枚举或历史数据语义。
- 生产升级前必须备份并在测试环境验证；当前尚未引入 Alembic。
- 附件清理由 lifespan 创建和取消，退出时不得遗留未受控任务。

## 10. API 文档与错误约定

新增或修改接口后：

```bash
npm run docs:api
.venv/bin/python -m json.tool docs/openapi.json > /dev/null
```

同步更新 `docs/api.md`、`docs/openapi.json` 和必要的调用方。常用错误：

- 401：未认证、令牌无效、用户停用。
- 403：项目有效角色缺少权限。
- 404：资源不存在或明确不可见。
- 409：状态、唯一性、乐观锁或当前业务冲突。
- 422：字段格式和业务输入校验失败。

## 11. 后端变更检查清单

1. 明确项目边界、当前处理人和权限点。
2. 请求模型与服务层同时校验，不能只依赖前端。
3. 多表写入和状态历史使用事务；并发更新使用行锁／版本。
4. 列表使用轻量 DTO，避免 Base64 和快照放大。
5. 文件和导出考虑流式处理、大小限制、校验与补偿。
6. 重要操作写审计，敏感配置不进入日志。
7. 添加成功、拒绝、边界和并发测试。
8. 执行 `npm run backend:test`、`npm run docs:api`，再执行前端全量回归。

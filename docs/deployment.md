# WMP v1.6 部署文档

本文用于将当前工程部署到已具备 PostgreSQL 和 RustFS 的内网 Linux 服务器，分别说明**测试版本**与**生产版本**。示例系统为 Ubuntu/Debian，其他 Linux 发行版请替换对应的软件包安装命令和 systemd、Nginx 配置路径。

> 适用代码版本：WMP v1.6.0。部署前应固定代码版本或提交号，不要直接用随时变化的工作目录作为生产发布包。

## 1. 架构与部署边界

```text
用户浏览器
   │ HTTPS（测试可为 HTTP）
   ▼
Nginx：前端静态文件 + /api、/docs、/openapi.json 反向代理
   │ 127.0.0.1
   ▼
FastAPI / Uvicorn
   ├── PostgreSQL：用户、权限、WKD、历史、构建记录、Object Key
   └── RustFS：附件和真实 tar.gz 构建制品

用户浏览器 ── 预签名 URL ── RustFS：附件直传、附件/制品下载
```

前端构建后为 `dist/` 静态文件，不需要在生产服务器运行 Vite。后端仅监听 `127.0.0.1`，由 Nginx 对外提供统一入口。

**RustFS 地址必须同时可被后端和用户浏览器访问。** 因为附件上传、附件下载和制品下载使用浏览器直接访问的预签名 URL。如果后端使用 `http://127.0.0.1:9000` 或浏览器无法解析的内网主机名，后端可能可以上传制品，但用户浏览器会下载失败。

## 2. 测试版本与生产版本区别

| 项目 | 测试版本 | 生产版本 |
|---|---|---|
| 主要用途 | 功能联调、接口验证、构建验证 | 正式业务使用 |
| `ENVIRONMENT` | `development` | `production` |
| 本地账号 | 允许已启用账号登录 | 仅系统管理员允许本地登录 |
| OAuth | 可关闭，也可配置独立测试 IdP 验证 | 普通用户通过企业 OIDC 登录，必须配置生产 IdP |
| 数据库 | 独立测试库，如 `wmp_test` | 独立生产库，如 `wmp_prod`，禁止共用 |
| RustFS | 独立测试 Bucket / 账号 | 独立生产 Bucket / 账号，私有访问 |
| 前端协议 | 内网 HTTP 可用于临时测试 | 必须 HTTPS |
| Uvicorn | 单进程，便于排查 | 多进程，不启用 `--reload` |
| Swagger | 可对测试人员开放 | 建议仅内网管理员访问或限制来源 |
| 演示数据 | `SEED_DEMO_DATA=true` 时显式开启 | 必须保持 `SEED_DEMO_DATA=false` |
| 前端 Demo 登录 | 仅在 `npm run dev` 且 `VITE_ENABLE_DEMO_LOGIN=true` 时开启 | 生产构建始终禁用，不预填账号、不提供角色选择或 Demo 降级 |
| 密钥 | 使用独立随机密钥，不使用示例默认值 | 独立高强度密钥，纳入受控密钥管理 |
| 数据安全 | 可重置，重置前仍应备份 | 必须备份、监控、审计并准备回滚方案 |

**测试和生产至少分离数据库、Bucket、JWT 密钥、OIDC Client 和管理员密码。** 不建议在同一应用服务器上共用端口或数据目录；本文测试示例使用端口 `18000/8080`，生产使用 `8000/443`。

## 3. 当前版本的部署约束

1. **OIDC 负责身份认证，WMP 负责业务授权。** 已导入用户首次登录只按工号绑定 OIDC `sub`，后续按 `sub` 识别；用户名可以重复，不能作为账号绑定依据，IdP 必须返回工号。未注册的企业用户会自动创建 WMP 账号，并加入按需创建的“用户初始化”占位项目。该项目的“初始化用户”角色仅有首页权限，真实项目角色和按钮权限仍由 WMP 项目管理员分配。系统管理员不能通过 OAuth 登录，必须使用本地管理员账号。
2. **IdP 必须支持标准 OIDC 授权码流程。** 需要提供发现文档、授权/令牌接口、JWKS，并支持 ID Token 的 Issuer、Audience、Nonce 和签名校验。当前令牌认证支持 `client_secret_basic`、`client_secret_post`，默认签名算法为 `RS256`。
3. **演示业务数据默认关闭。** 权限、预设角色和系统管理员仍会初始化；只有 `SEED_DEMO_DATA=true` 且数据库没有任何项目时，才创建演示项目、版本、机台、子系统和一个已审核通过的 WKD。生产必须保持 `false`。
4. **数据库尚未引入 Alembic。** 后端启动时执行 `create_all` 和部分 `ALTER` 语句，数据库账号需要建表、修改表和修改枚举的权限。从 v1.5 升级到 v1.6 没有数据库结构变化；如果从更早版本升级，应先核对 v1.5 的用户部门、用户名唯一约束和旧 `users.name` 列变更。生产升级与回滚必须先在测试环境验证并备份，不能假设任意旧代码都能直接回滚到已升级的数据结构。
5. **管理员密码环境变量主要用于首次初始化。** 管理员已经存在后，仅修改 `BOOTSTRAP_ADMIN_PASSWORD` 不会自动重置其密码。首次启动前就应设置高强度密码。当前版本没有自助修改密码页面或密码重置 API；已有管理员密码需由运维在后端通过受控脚本更新 PostgreSQL 中的 `users.password_hash`，具体方法见 10.5 节。
6. **项目成员支持 Excel／CSV 批量初始化。** 系统管理员可导入任意项目，项目管理员只能导入具有 `project.member.manage` 权限的项目。页面下载的五列模板为工号、用户名、所属部门、项目角色、邮箱；工号和用户名必填，其他字段选填，角色为空时使用页面默认角色。单次最多 5000 行，必须先校验预览，全部无错误后才能确认；已有成员保留原角色。
7. **生产配置采用 fail-closed。** 启动时会拒绝默认或过短的 JWT 密钥、管理员初始密码，以及默认数据库和 RustFS 凭证；配置不合法时进程直接退出，应先查看日志并修正 `.env`，不能通过关闭校验绕过。
8. **管理员按唯一工号初始化。** `BOOTSTRAP_ADMIN_EMPLOYEE_ID` 默认 `E0001`，用于避免普通同名账号被误提权；本地登录支持用户名或唯一工号，用户名重名时必须使用工号。测试和生产应使用独立且受控的管理员工号。
9. **构建仍有同步请求边界。** 单次最多 200 个 WKD，普通附件总量默认 2 GB；当前没有后台任务、进度查询和构建幂等。Nginx 示例读取超时提高到 600 秒只是缓解，超大或慢构建仍应控制批次，后续需任务化。

## 4. 部署前检查清单

准备以下信息，本文以占位符表示，不要把真实密码写入代码仓库或本文档：

| 配置项 | 测试示例 | 生产示例 |
|---|---|---|
| 应用访问地址 | `http://10.10.0.20:8080` | `https://wmp.example.internal` |
| PostgreSQL 地址 | `10.10.0.30:5432` | `10.10.0.40:5432` |
| 数据库 | `wmp_test` | `wmp_prod` |
| RustFS S3 地址 | `http://10.10.0.30:9000` | `https://rustfs.example.internal` |
| Bucket | `wmp-test` | `wmp-prod` |
| 应用目录 | `/opt/wmp-test/app` | `/opt/wmp/app` |
| 后端监听 | `127.0.0.1:18000` | `127.0.0.1:8000` |

服务器依赖：

- Linux x86_64 或 arm64；Python 3.11 或 3.12。
- Node.js 22 LTS 和 npm，仅用于构建前端。
- Nginx、systemd。
- 已运行且可访问的 PostgreSQL、RustFS。
- 生产环境需要有效 TLS 证书、时间同步、备份和日志采集。

网络放通：

- 用户到 Nginx：测试 `8080`，生产 `443`。
- 后端到 PostgreSQL：`5432`，仅允许应用服务器来源。
- 后端和用户浏览器到 RustFS S3 地址：测试示例 `9000`，生产建议 `443`。
- RustFS 控制台 `9001` 只允许管理员网络访问。
- 不对用户直接开放 Uvicorn `18000/8000`，不直接公开 PostgreSQL。

## 5. 制作并上传发布包

在开发机工程根目录执行。不要携带本地虚拟环境、依赖目录、密钥、日志、测试制品或下载的服务程序：

```bash
tar \
  --exclude='./.git' \
  --exclude='./.venv' \
  --exclude='./node_modules' \
  --exclude='./dist' \
  --exclude='./artifacts' \
  --exclude='./backend/.env' \
  --exclude='*.log' \
  -czf /tmp/wmp-v1.6.0.tar.gz .
```

计算校验值并传到目标服务器：

```bash
shasum -a 256 /tmp/wmp-v1.6.0.tar.gz
scp /tmp/wmp-v1.6.0.tar.gz <用户>@<服务器>:/tmp/
```

服务器解压后应核对 SHA-256；Linux 使用 `sha256sum /tmp/wmp-v1.6.0.tar.gz`。发布包中的 `docs/openapi.json` 是接口快照，运行时 Swagger/OpenAPI 由 FastAPI 后端提供。

## 6. 初始化 PostgreSQL 与 RustFS

### 6.1 PostgreSQL

请 DBA 分别创建测试和生产数据库及账号。示例 SQL 中的密码必须替换，且测试与生产不能相同：

```sql
CREATE ROLE wmp_test LOGIN PASSWORD '<独立测试密码>';
CREATE DATABASE wmp_test OWNER wmp_test;

CREATE ROLE wmp_prod LOGIN PASSWORD '<独立生产密码>';
CREATE DATABASE wmp_prod OWNER wmp_prod;
```

账号需能创建和维护本应用自己的表、索引及枚举；当前版本不建议在启动阶段切换为只有增删改查权限的账号。生产账号权限应限定在 `wmp_prod`，不能授予超级用户或其他数据库权限。

如果数据库账号密码包含 `@`、`:`、`/`、`#`、`%` 等字符，写入 `DATABASE_URL` 前必须进行 URL 编码。生产 PostgreSQL 如需 TLS，可按服务器证书配置在连接串中增加 `?sslmode=require`；如要验证证书，应同时配置对应 CA，而不是仅关闭验证。

### 6.2 RustFS

分别创建：

- 私有 Bucket：`wmp-test`、`wmp-prod`。
- 独立访问密钥，仅授予对应 Bucket 所需的对象读写权限。
- 禁止匿名读写。
- 生产启用服务端加密、版本控制或对象保护策略时，应先验证构建覆盖、附件下载和生命周期规则。

为浏览器直接上传和下载配置 Bucket CORS：

- AllowedOrigins：测试为 `http://10.10.0.20:8080`；生产为 `https://wmp.example.internal`。
- AllowedMethods：`GET`、`PUT`。
- AllowedHeaders：至少包含 `Content-Type`，可按 RustFS 配置方式允许必要的签名请求头。
- ExposeHeaders：必须包含 `ETag`，否则浏览器无法提交 Multipart 分片完成信息。
- 不要在生产配置无关的 `*` 来源。

应用每 24 小时使草稿上传会话过期，并默认每小时清理过期未绑定附件和未完成分片。还应在 RustFS Bucket 配置 `attachments/` 前缀的未完成 Multipart 生命周期清理，作为应用清理任务不可用时的兜底；不要对已绑定的正式附件配置自动过期删除。

应用不在数据库中保存附件或制品二进制，只保存 Object Key 和元数据。备份必须同时覆盖 PostgreSQL 与 RustFS，并保证恢复时间点一致。

## 7. 测试版本部署

### 7.1 安装应用

```bash
sudo useradd --system --home /opt/wmp-test --shell /usr/sbin/nologin wmptest
sudo mkdir -p /opt/wmp-test/app
sudo tar -xzf /tmp/wmp-v1.6.0.tar.gz -C /opt/wmp-test/app
sudo chown -R wmptest:wmptest /opt/wmp-test

sudo apt-get update
sudo apt-get install -y python3 python3-venv nginx curl
# 安装 Node.js 22 LTS 后继续；请先确认 node --version、npm --version。
```

安装后端依赖、构建前端：

```bash
cd /opt/wmp-test/app
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install --no-cache-dir -r backend/requirements.txt
npm ci
npm run build
test -f dist/index.html
```

`npm ci` 使用仓库中的 `package-lock.json`，不要用不受锁文件约束的随机依赖版本替代。

### 7.2 配置测试环境

```bash
cp backend/.env.example backend/.env
chmod 600 backend/.env
```

编辑 `/opt/wmp-test/app/backend/.env`：

```dotenv
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://wmp_test:<URL编码后的测试密码>@10.10.0.30:5432/wmp_test
JWT_SECRET=<独立的至少32字节随机值>
JWT_EXPIRE_MINUTES=720
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_EMPLOYEE_ID=E0001
BOOTSTRAP_ADMIN_PASSWORD=<独立测试管理员强密码>
SEED_DEMO_DATA=true
OAUTH_ENABLED=false
CORS_ORIGINS=http://10.10.0.20:8080
RUSTFS_ENDPOINT=http://10.10.0.30:9000
RUSTFS_ACCESS_KEY=<测试访问键>
RUSTFS_SECRET_KEY=<测试密钥>
RUSTFS_BUCKET=wmp-test
RUSTFS_REGION=us-east-1
PRESIGN_EXPIRE_SECONDS=300
MAX_ATTACHMENT_SIZE=524288000
MAX_BUILD_ATTACHMENT_BYTES=2147483648
ATTACHMENT_SESSION_EXPIRE_HOURS=24
ATTACHMENT_MULTIPART_THRESHOLD=67108864
ATTACHMENT_MULTIPART_PART_SIZE=16777216
ATTACHMENT_CLEANUP_INTERVAL_SECONDS=3600
ATTACHMENT_CLEANUP_ENABLED=true
```

可用 `openssl rand -hex 32` 生成 JWT 随机值。不要把 `.env` 打包回代码或提交到 Git。

### 7.3 配置后端服务

创建 `/etc/systemd/system/wmp-test-api.service`：

```ini
[Unit]
Description=WMP Test API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=wmptest
Group=wmptest
WorkingDirectory=/opt/wmp-test/app/backend
ExecStart=/opt/wmp-test/app/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 18000 --workers 1
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0027

[Install]
WantedBy=multi-user.target
```

启动并检查：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wmp-test-api
sudo systemctl status wmp-test-api
curl --fail http://127.0.0.1:18000/health
sudo journalctl -u wmp-test-api -n 100 --no-pager
```

首次启动会建表、初始化权限/角色/管理员；空库还会写入演示业务数据，测试环境可据此检查页面和构建流程。

### 7.4 配置测试 Nginx

创建 `/etc/nginx/conf.d/wmp-test.conf`：

```nginx
server {
    listen 8080;
    server_name 10.10.0.20;

    root /opt/wmp-test/app/dist;
    index index.html;
    client_max_body_size 160m;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:18000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
    }

    location = /health {
        proxy_pass http://127.0.0.1:18000;
    }

    location ~ ^/(docs|redoc|openapi\.json) {
        proxy_pass http://127.0.0.1:18000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

检查并加载。健康检查是后端根路径 `/health`，不属于 `/api/v1`：

```bash
sudo nginx -t
sudo systemctl reload nginx
curl --fail http://127.0.0.1:18000/health
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:8080/openapi.json -o /tmp/wmp-test-openapi.json
```

再访问 `http://<测试服务器>:8080/`。页面应显示真实接口登录模式，而不是“Demo 数据模式”。

## 8. 生产版本部署

### 8.1 先完成上线门禁

- 已在测试 IdP 完成 OIDC 授权码、State/Nonce、签名、用户绑定和权限验证。
- 已验证新企业用户可以自动注册并进入“用户初始化”项目，且没有实际业务权限；真实项目角色和权限仍由 WMP 管理。
- 仅保留一个最高权限系统管理员；其他用户不得设置 `is_superuser=true`。
- 生产 `SEED_DEMO_DATA=false`，不会写入演示项目或演示 WKD。
- 已使用独立生产数据库、Bucket、OIDC Client、密钥、管理员密码和 HTTPS 证书。
- 已完成数据库与 RustFS 备份、监控、容量评估和恢复演练。
- 已用测试环境验证完整构建包下载、解包和隔离执行。

### 8.2 安装与构建

应用路径和运行账号与测试环境隔离：

```bash
sudo useradd --system --home /opt/wmp --shell /usr/sbin/nologin wmp
sudo mkdir -p /opt/wmp/app
sudo tar -xzf /tmp/wmp-v1.6.0.tar.gz -C /opt/wmp/app
sudo chown -R wmp:wmp /opt/wmp
cd /opt/wmp/app
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install --no-cache-dir -r backend/requirements.txt
npm ci
npm run build
cp backend/.env.example backend/.env
chmod 600 backend/.env
```

前端默认请求同源 `/api/v1`，生产不需要设置 `VITE_API_BASE`。只有前后端确实分离域名时才在构建前配置它，并同步修改 CORS、TLS 和 Nginx；推荐保持本文的同源部署方式。生产登录页只提供空白的用户名、密码输入框、本地登录按钮和企业 OAuth 按钮；`npm run build` 始终禁用 Demo 登录与 Demo 会话，即使误设 `VITE_ENABLE_DEMO_LOGIN=true` 也不会生效。后端不可用时只显示登录错误，绝不自动降级为演示管理员。

### 8.3 配置生产环境

编辑 `/opt/wmp/app/backend/.env`：

```dotenv
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://wmp_prod:<URL编码后的生产密码>@10.10.0.40:5432/wmp_prod
JWT_SECRET=<生产独立高强度随机值>
JWT_EXPIRE_MINUTES=720
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_EMPLOYEE_ID=E0001
BOOTSTRAP_ADMIN_PASSWORD=<首次初始化使用的生产管理员强密码>
SEED_DEMO_DATA=false
OAUTH_ENABLED=true
OAUTH_ISSUER_URL=https://idp.example.internal
OAUTH_CLIENT_ID=<生产OIDC客户端ID>
OAUTH_CLIENT_SECRET=<生产OIDC客户端密钥>
OAUTH_REDIRECT_URI=https://wmp.example.internal/oauth/callback
OAUTH_SCOPES=openid profile email
OAUTH_TOKEN_AUTH_METHOD=client_secret_basic
OAUTH_ID_TOKEN_ALGORITHM=RS256
OAUTH_USERNAME_CLAIM=preferred_username
OAUTH_EMPLOYEE_ID_CLAIM=employee_id
OAUTH_DEPARTMENT_CLAIM=department
OAUTH_EMAIL_CLAIM=email
CORS_ORIGINS=https://wmp.example.internal
RUSTFS_ENDPOINT=https://rustfs.example.internal
RUSTFS_ACCESS_KEY=<生产访问键>
RUSTFS_SECRET_KEY=<生产密钥>
RUSTFS_BUCKET=wmp-prod
RUSTFS_REGION=us-east-1
PRESIGN_EXPIRE_SECONDS=300
MAX_ATTACHMENT_SIZE=524288000
MAX_BUILD_ATTACHMENT_BYTES=2147483648
ATTACHMENT_SESSION_EXPIRE_HOURS=24
ATTACHMENT_MULTIPART_THRESHOLD=67108864
ATTACHMENT_MULTIPART_PART_SIZE=16777216
ATTACHMENT_CLEANUP_INTERVAL_SECONDS=3600
ATTACHMENT_CLEANUP_ENABLED=true
```

在企业 IdP 注册 WMP 客户端时：

1. 应用类型选择服务端 Web 应用，授权类型选择 Authorization Code，不启用 Implicit。
2. 回调地址必须逐字配置为 `https://wmp.example.internal/oauth/callback`，与 `OAUTH_REDIRECT_URI` 完全一致。
3. 确认 `https://idp.example.internal/.well-known/openid-configuration` 可从后端访问，且返回的 `issuer` 与 `OAUTH_ISSUER_URL` 一致。
4. 确认 ID Token 或 UserInfo 包含 `sub`、`nonce` 以及映射用户名、工号、部门、邮箱的 Claim；其中用户名和工号必须存在。如果 IdP 使用不同 Claim 名称，修改 `OAUTH_USERNAME_CLAIM`、`OAUTH_EMPLOYEE_ID_CLAIM`、`OAUTH_DEPARTMENT_CLAIM`、`OAUTH_EMAIL_CLAIM`。
5. 如果令牌接口使用请求体传递密钥，将 `OAUTH_TOKEN_AUTH_METHOD` 改为 `client_secret_post`；签名算法必须改为 IdP 实际使用且允许的算法，不能通过关闭验签兼容。
6. 后端需要访问 IdP 的发现、令牌、JWKS 和 UserInfo 地址；用户浏览器需要访问 IdP 授权登录页。生产回调必须使用 HTTPS。
7. 测试 OIDC 时，在测试 `.env` 使用独立的测试 IdP Client 和测试回调 `http://10.10.0.20:8080/oauth/callback`，并保持测试与生产用户库隔离。

生产修改 `JWT_SECRET` 会使现有令牌全部失效，应作为计划内变更执行。不要把真实 `.env` 复制到测试环境，也不要在 shell 历史中明文展开密码。

### 8.4 配置生产后端服务

创建 `/etc/systemd/system/wmp-api.service`：

```ini
[Unit]
Description=WMP Production API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=wmp
Group=wmp
WorkingDirectory=/opt/wmp/app/backend
ExecStart=/opt/wmp/app/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0027
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
```

工作进程可先设置为 `2～4`，再依据 CPU、内存、并发构建耗时和 PostgreSQL 连接数压测调整。不要启用 `--reload`。启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wmp-api
sudo systemctl status wmp-api
curl --fail http://127.0.0.1:8000/health
sudo journalctl -u wmp-api -n 100 --no-pager
```

### 8.5 配置生产 Nginx 与 HTTPS

创建 `/etc/nginx/conf.d/wmp.conf`，替换证书路径：

```nginx
server {
    listen 80;
    server_name wmp.example.internal;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name wmp.example.internal;

    ssl_certificate /etc/nginx/tls/wmp-fullchain.pem;
    ssl_certificate_key /etc/nginx/tls/wmp-private-key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    root /opt/wmp/app/dist;
    index index.html;
    client_max_body_size 160m;

    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options DENY always;
    add_header Referrer-Policy no-referrer always;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 600s;
    }

    location = /health {
        proxy_pass http://127.0.0.1:8000;
    }

    location ~ ^/(docs|redoc|openapi\.json) {
        allow 10.10.0.0/24;
        deny all;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

将 `allow` 网段替换为实际管理员网段。证书私钥仅允许 Nginx 管理账号读取。普通附件通过 RustFS 预签名地址直传，`client_max_body_size 160m` 不限制单个 500 MB 普通附件；该值用于容纳原子操作文件的 Base64 放大、其余 WKD 字段和请求开销。单个原子文件 20 MB、单 WKD 原子文件总量 100 MB，仍由后端校验。`proxy_read_timeout 600s` 仅是同步构建的临时缓解，超过代理或客户端时限的大构建仍可能失败，应控制构建批次并规划后台任务化。

```bash
sudo nginx -t
sudo systemctl reload nginx
curl --fail https://wmp.example.internal/health
```

## 9. 部署后验收

### 9.1 基础与权限

1. 访问应用地址，确认不是 Demo 模式。
2. 使用系统管理员登录，检查首页、项目、版本、机台、子系统、角色和成员。
3. 使用一个未注册的企业账号完成 OAuth 登录，确认账号自动创建、加入“用户初始化”项目，且不能新建 WKD、上传附件、构建或维护业务数据；再用成员管理将其分配到真实项目并核对角色。
4. 在成员管理下载五列模板，先用包含重复工号或无效角色的文件确认逐行错误会阻止导入，再用正确文件完成预览和确认；重复导入时已有成员保留原角色，不生成重复用户或成员，并用项目管理员账号验证不能导入无权限项目。
5. 用非授权账号验证按钮不可用时，服务端同样返回 `403`，不能只检查前端按钮隐藏。
6. 生产环境确认普通本地账号不能绕过 OAuth 登录。
7. 展开“构建 / 发布”子菜单后收起侧栏，确认没有子菜单或内部元素越界；收起状态悬停图标不应自动弹出浮层，点击后应能进入调试构建和正式构建。
8. 检查 `/openapi.json`、`/docs`；生产确认接口文档仅管理员网段可访问。

> Swagger UI 和 ReDoc 的默认前端资源可能来自公共 CDN。完全隔离互联网的内网中，`openapi.json` 和接口调用不受影响，但文档页面样式/脚本可能需要额外做本地静态化；不要将“Swagger 页面打不开”误判为后端接口失败。

### 9.2 WKD 与附件

1. 新建 WKD，确认项目、所属版本来自全局上下文，责任人固定为当前用户。
2. 在首次创建前上传两个不同类型附件，刷新页面确认草稿附件恢复；创建后确认附件已绑定，下载内容一致。
3. 上传一个达到分片阈值的文件，确认失败分片可重试、浏览器能读取 ETag，完成后数据库状态为 `READY` 且保存 SHA-256。
4. 验证问题单号/需求单号、问题发现版本、执行类型和自定义阶段唯一性规则。
5. 编排一个上传操作中的多个文件，再编排 Linux 命令，提交自验证。
6. 检查数据库仅保存 Object Key，RustFS 中存在对应私有对象，匿名 URL 不可直接读取；用另一账号验证不能恢复或绑定他人的草稿附件。

### 9.3 构建制品

1. 在调试构建选择已提交自验证的 WKD 和关联机台，执行构建。
2. 下载制品并核对 API 返回的 SHA-256：
   ```bash
   sha256sum WMP_DEBUG_*.tar.gz
   ```
3. 解包检查：
   ```bash
   mkdir -p /tmp/wmp-package-check
   tar -xzf WMP_DEBUG_*.tar.gz -C /tmp/wmp-package-check
   ls /tmp/wmp-package-check
   cat /tmp/wmp-package-check/MANIFEST.json
   ```
   应包含 `wmp_entry.py`、`MANIFEST.json`、`WKD_LIST.json`、`README.md` 和 `packages/<WKD编号>/`。每个子包的 `files/` 保存原子操作上传文件，`attachments/` 保存已绑定且 `READY` 的 WKD 普通附件；人工操作 WKD 也应有独立子包。普通附件只随包携带，不由入口自动执行。
4. 先列出包内 WKD 和阶段，再在隔离测试目录执行；不得直接对生产设备随意运行 WKD 中的 Linux 命令：
   ```bash
   python3 /tmp/wmp-package-check/wmp_entry.py --list
   python3 /tmp/wmp-package-check/wmp_entry.py <阶段参数> --target-root /tmp/wmp-sandbox
   # 只验证一个 WKD 时：
   python3 /tmp/wmp-package-check/wmp_entry.py <阶段参数> --wkd <WKD编号> --target-root /tmp/wmp-sandbox
   ```
   默认按 `MANIFEST.json` 顺序执行所有匹配阶段的 WKD，并跳过不匹配项；旧的“WKD 编号 + 阶段参数”双位置参数调用仍兼容。`--target-root` 仅用于隔离验证；正式执行前应审查 WKD 内容、命令、目标路径和权限。
5. 验证正式构建只包含所选项目、所选机台下全部已勾选且状态为 `APPROVED` 的 WKD。

## 10. 日常运维、升级与回滚

### 10.1 日志与监控

```bash
sudo systemctl status wmp-api
sudo journalctl -u wmp-api --since "30 minutes ago" --no-pager
sudo tail -f /var/log/nginx/error.log
```

监控进程可用性、`/health`、HTTP 5xx、PostgreSQL 连接与容量、RustFS 容量和错误率、证书有效期。审计日志在数据库中，仍需纳入备份和保留策略。

### 10.2 备份

升级前同时备份：

- PostgreSQL：使用 `pg_dump` 或受控数据库备份系统。
- RustFS：使用其版本控制、复制或对象存储备份能力，确保附件和制品可恢复。
- 应用发布包、`backend/.env`、Nginx 和 systemd 配置；敏感配置应加密保存并限制访问。

示例：

```bash
pg_dump -h 10.10.0.40 -U wmp_prod -d wmp_prod -Fc -f /secure-backup/wmp_prod_before_upgrade.dump
```

恢复演练必须验证数据库记录和 RustFS 对象能对应，而不是只确认备份文件存在。

### 10.3 升级

1. 在测试环境使用同版本发布包和同结构数据先升级。
2. 备份生产数据库、RustFS 和配置，记录当前发布包及 SHA-256。
3. 停止旧服务，部署新代码到独立目录，安装锁定依赖并重新执行 `npm ci && npm run build`。
4. 更新配置后启动，检查迁移日志、健康状态、权限、附件和构建。
5. 验收通过后保留旧发布包一段时间；不要在验收前删除旧备份。

### 10.4 回滚

- 应用代码未改变数据库结构时，可恢复旧发布包并重启。
- 已改变数据库结构或写入新格式数据时，不能仅回滚代码。需要经过验证的兼容迁移，或在停机窗口恢复升级前数据库与对应 RustFS 备份。
- 恢复备份会丢失备份之后的新业务数据，必须先评估并明确变更窗口。
- 当前未引入 Alembic，任何生产升级都必须先在测试环境验证启动时的自动建表/修改语句。

### 10.5 已有系统管理员密码重置

当前版本没有自助修改密码页面或密码重置 API。确需重置时，由运维在生产后端主机执行以下受控脚本；脚本从终端隐藏读取新密码，不要把密码写进命令参数、shell 历史或文档。操作前应备份数据库并记录运维审计。

```bash
cd /opt/wmp/app/backend
../.venv/bin/python - <<'PY'
from getpass import getpass
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User
from app.security import hash_password

username = input('管理员用户名：').strip()
password = getpass('新密码（至少 12 位）：')
if len(password) < 12 or password != getpass('再次输入新密码：'):
    raise SystemExit('密码不足 12 位或两次输入不一致，未做任何修改')
with SessionLocal() as db:
    admins = list(db.scalars(select(User).where(
        User.username == username, User.is_superuser.is_(True))))
    if len(admins) != 1:
        raise SystemExit('必须且只能匹配一名系统管理员，未做任何修改')
    admins[0].password_hash = hash_password(password)
    db.commit()
print('管理员密码已更新')
PY
```

该操作只更新 PostgreSQL 中的 `users.password_hash`，不会撤销已签发的 JWT；如因泄露而重置，还应在计划内轮换 `JWT_SECRET` 并要求重新登录。普通业务用户不通过本地密码维护，应使用企业 OIDC。

## 11. 常见故障定位

| 现象 | 优先检查 |
|---|---|
| 启动即报数据库连接失败 | `DATABASE_URL`、DNS/IP、端口、防火墙、账号密码 URL 编码、TLS 设置 |
| 启动报枚举或表权限错误 | 当前版本启动需要 DDL 权限，检查数据库 owner/权限和已有枚举结构 |
| 页面能打开但 API 全部失败 | Nginx `/api/` 代理、Uvicorn 状态、`CORS_ORIGINS` 是否与应用源完全一致 |
| 返回 401 | 令牌过期、JWT 密钥变更、用户停用；生产普通本地账号会被拒绝 |
| 返回 403 | 用户是否为项目成员、项目角色是否包含对应按钮权限点；初始化用户只有首页权限属预期行为；检查账号是否停用 |
| OAuth 提示 State/Nonce 或令牌校验失败 | 重新从 WMP 登录页发起；检查 IdP 回调、服务器时间、Issuer、Audience、JWKS 和签名算法 |
| OAuth 自动注册失败 | 检查用户名/工号 Claim 是否缺失、超长或与多个本地账号冲突，并确认启动初始化已创建“初始化用户”角色 |
| OAuth 授权码交换失败 | 检查 Client ID/Secret、令牌认证方式、回调地址、后端到 IdP 网络和 TLS 证书 |
| 构建成功但浏览器下载失败 | `RUSTFS_ENDPOINT` 是否可被浏览器访问、DNS、TLS、CORS、预签名 URL 是否过期 |
| 附件直传失败 | RustFS CORS 是否允许应用源的 `PUT` 和 `Content-Type`，对象大小是否超过 500 MB；分片上传还必须暴露 `ETag` |
| 草稿附件提示会话过期 | 默认会话有效期为 24 小时；重新创建会话并上传，过期文件会由清理任务删除 |
| Swagger 页面空白 | 内网是否无法访问公共 CDN；先检查 `/openapi.json` 和 `/health` |
| 首次启动出现演示项目/WKD | 检查是否误设 `SEED_DEMO_DATA=true`；生产必须为 `false`，测试演示数据不要导入生产 |
| 修改管理员密码变量后旧密码仍有效 | 环境变量不会覆盖已存在管理员密码；按 10.5 节由运维在后端受控重置 |

## 12. 上线完成判定

只有同时满足以下条件才建议判定生产部署完成：

- OAuth 和普通用户登录链路完成并通过验收。
- 生产无演示业务数据，OAuth 自动注册、初始化占位项目隔离与真实项目角色分配已核对。
- HTTPS、独立密钥、私有 Bucket、网络访问控制和管理员唯一性符合要求。
- WKD 状态流转、属性历史、附件、调试/正式构建和下载均通过真实服务验证。
- 通过内网实际访问地址验证新建 WKD 时可添加原子操作；不要只用 localhost 验证浏览器兼容性。详情页责任人和当前处理人应显示“用户名 工号”，详细流程的加粗、斜体、下划线和字体颜色应实际生效。
- 制品已解包并在隔离环境执行验证。
- 数据库与 RustFS 均已备份，且至少完成一次恢复演练。
- 监控、日志、升级和回滚责任明确。

# WMP v1.8 前端开发文档

## 1. 技术栈与目录

- Vue 3、TypeScript、Vite、Vue Router。
- Element Plus 与 Element Plus Icons。
- ECharts、Day.js、ExcelJS。
- Vitest：前端单元与竞态回归测试。

```text
src/
├── api.ts                    # fetch 封装、错误处理、DTO 转换、下载
├── store.ts                  # 会话、项目上下文、选项、权限与并发控制
├── router.ts                 # 路由与访问控制
├── permissions.ts            # 菜单和系统管理权限计算
├── layouts/AppLayout.vue     # 全局布局与首屏初始化门禁
├── views/                  # 首页、工作台、详情、构建、统计、系统管理
├── components/               # 表格、列设置、富文本和系统管理组件
├── utils/                    # 草稿、表格偏好、筛选、UUID、Demo 制品
├── types.ts                  # 前端类型
└── store.test.ts             # 项目上下文与权限竞态回归
```

## 2. 本地开发

环境要求：Node.js 22 LTS、npm；后端和基础设施见后端开发与部署文档。

```bash
npm ci
cp .env.example .env            # 仅在需要自定义前端开发配置时
npm run dev
```

默认开发地址为 `http://localhost:7100`，Vite 将 `/api`、`/docs`、`/openapi.json` 代理到 `127.0.0.1:8000`。

常用命令：

```bash
npm run test:frontend   # Vitest 全量前端测试
npm run build           # vue-tsc 类型检查 + 生产构建
npm run preview         # 本地预览生产构建
```

生产构建始终禁用 Demo 登录。只有开发服务器且显式设置 `VITE_ENABLE_DEMO_LOGIN=true` 才允许 Demo 会话，不得在业务代码中新增生产 Demo 降级路径。

## 3. 首屏初始化约定

`AppLayout.vue` 是业务页面挂载门禁，顺序固定为：

1. `refreshIdentity()`：校验并刷新用户。
2. `ensureOptions()`：确定真实项目、版本和基础选项。
3. `refreshPermissions()`：获取当前项目按钮权限。
4. `contextReady=true` 后才渲染 `router-view`。

**禁止新增页面绕过该顺序，在 `setup` 或提前的 `onMounted` 中直接携带 `store.projectId` 请求。** 初始 `demo-project`／`demo-version` 只用于显式 Demo 数据，不得进入真实 API 请求。

`ensureOptions()` 的非强制并发调用共享同一进行中的 Promise；`force=true` 用于项目切换等强制刷新。修改上下文代码时必须保持：

- 只应用最新选项请求结果。
- 权限结果必须匹配最新请求、当前项目和当前会话。
- 业务页面挂载前不得依赖 watcher 来“补救”占位上下文。

## 4. 会话与权限

`store.session` 持久化于 `localStorage`，令牌键为 `wmp-token`。页面使用：

```ts
import { can, store } from '../store'

can('wkd.create')
can('build.release.build')
```

- 前端权限只控制菜单、按钮和只读状态，不能代替后端鉴权。
- 项目切换使用 `selectProject()`，不要直接只改 `projectId`；该函数会刷新选项和权限。
- 401 由 `api.ts` 发送 `wmp:unauthorized`，布局统一清理会话并回登录页。
- 403／409 应展示后端明确原因，不要统一改写为“网络异常”。

## 5. API 开发约定

统一使用 `api.get/post/put/upload/delete/download`，不要散落原生 `fetch`：

```ts
const result = await api.get<Item[]>(`/wkds${queryString({
  project_id: store.projectId,
  version_id: store.versionId,
  statuses: filters.value.status,
})}`)
```

- `queryString` 自动忽略空值并展开数组为多值参数。
- 请求错误使用 `errorMessage(error, '业务操作失败')`。
- 列表使用轻量 DTO；只有详情和实际构建读取完整原子操作。
- 下载附件／制品先获取授权下载地址，再打开预签名 URL。
- 高频列表请求需要递增请求序号，避免旧筛选或旧项目响应覆盖新结果。

## 6. WKD 编辑与草稿

- 新建页首次保存才调用 `POST /wkds`；创建前附件通过上传会话管理。
- 创建后的“保存本地草稿”只写 `sessionStorage`，按用户、WKD 和当前状态次数隔离，不调用后端。
- 正式提交通过状态流转接口，必须携带 `lock_version`；409 冲突时提示刷新，不得静默覆盖。
- 切换自动化／人工执行会影响阶段和编排，必须遵循页面清空确认。
- 富文本继续使用现有清洗和工具栏，不得直接注入未经处理的 HTML。

## 7. 表格与统计

- 工作台、调试构建、正式构建共用 `WkdTable` 和列设置工具。
- 固定列为 WKD 编号与标题；其他偏好按用户和表格类型保存到当前浏览器。
- 表头筛选支持多选、搜索、当前结果全选和清空。
- 工作台筛选由后端执行；构建页在当前候选集合内筛选。
- 统计导出统一使用 XLSX，不新增 CSV 入口；导出必须复用当前全部筛选条件。

## 8. 附件上传

- 新建 WKD 与既有 WKD 都使用上传会话；既有 WKD 受状态和当前处理人约束。
- 前端流式计算 SHA-256；大文件使用分片，完成时提交实际 ETag 和校验信息。
- 原子操作上传文件与普通附件不同：原子文件随操作参数以 Base64 保存，普通附件走 RustFS。
- 上传重试、取消和超时应复用现有工具，不要另写无超时 XHR。
- 非安全内网 HTTP 环境使用 `src/utils/id.ts` 生成 UUID，禁止假设 `crypto.randomUUID` 一定存在。

## 9. 新增页面或按钮检查清单

1. 明确路由、项目上下文和服务端权限点。
2. 业务请求只在布局上下文就绪后发起；组件独立使用时先 `await ensureOptions()`。
3. 列表请求处理旧响应和项目切换。
4. 按钮使用独立权限点，后端同步鉴权。
5. 所有变更处理 401／403／409／422，并保留后端错误信息。
6. 文件、富文本、导出和本地存储遵守既有安全边界。
7. 添加自动化测试，并执行 `npm run test:frontend && npm run build`。

## 10. 当前工程边界

- Element Plus、ECharts 仍有较大 vendor chunk 警告，构建成功但可继续拆包。
- 表格偏好仅当前浏览器保存，不支持跨设备同步。
- 分片上传未实现跨会话断点恢复。
- 真实内网 OAuth、弱网、多标签页和大文件仍需在目标环境验收，不能由 localhost 构建结果替代。

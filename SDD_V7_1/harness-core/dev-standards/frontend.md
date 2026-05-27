
# 前端开发规范

## 1. 总则

**规范说明**

- 开发必须与 **`docs/prototypes/` 下已确认原型**一致：布局、组件位置、配色、间距不得随意发挥；偏离须说明原因并经用户确认。
- 页面结构与信息架构以 PRD + 原型为准，**不可凭感觉改页面规范**。
- 技术栈固定：**Vue 3 + TypeScript + Pinia + Vue Router**（不接受替换）。

---

## 2. 技术栈

**规范说明**

- 框架：Vue 3（Composition API 推荐）
- 语言：TypeScript
- 状态：Pinia
- 路由：Vue Router

（无单独代码示例。）

---

## 3. 目录结构

**规范说明**

- 页面放 `pages/`，可复用块放 `components/`，接口放 `services/`，全局状态放 `stores/`，路由放 `router/`，公共类型放 `types/`，工具放 `utils/`。

**示例（目录树）**

```
frontend/src/
├── components/     # 通用组件（AppHeader.vue, UserAvatar.vue）
├── pages/          # 页面级组件（LoginPage.vue, DashboardPage.vue）
├── stores/         # Pinia 状态管理
├── services/       # API 调用封装
├── router/         # 路由配置
├── types/          # TypeScript 类型定义
└── utils/          # 工具函数
```

---

## 4. 命名规范

**规范说明**

- 页面组件：`PascalCase` + `Page` 后缀。
- 通用组件：`PascalCase`，可加功能前缀（如 `App*`）。
- Store / Service / 类型文件：`camelCase` 文件名。

**示例（对照表）**

| 类型     | 规则                    | 示例                          |
|----------|-------------------------|-------------------------------|
| 页面组件 | PascalCase + Page 后缀  | `LoginPage.vue`, `ItemListPage.vue` |
| 通用组件 | PascalCase + 功能前缀   | `AppHeader.vue`, `UserAvatar.vue`   |
| Store    | camelCase               | `useAuthStore.ts`, `useItemStore.ts` |
| Service  | camelCase               | `authService.ts`, `itemService.ts`   |
| 类型文件 | camelCase               | `auth.ts`, `item.ts`                 |

---

## 5. 环境变量

**规范说明**

- 前端变量放在 `frontend/.env`。
- **必须以 `VITE_` 前缀**，否则 Vite 不会注入到客户端。
- 与后端 **各自独立** `.env`，禁止混用同一文件。

**端口策略（强制）**

- Agent 自动开发 / Tester 自动验证使用冷门端口，避免占用学员常用端口：
  - 前端 Vite：`5199`
  - 后端 Uvicorn：`8099`
- 用户门禁验收指令使用固定演示端口，方便用户自己打开页面复测：
  - 前端 Vite：`5175`
  - 后端 Uvicorn：`8003`
- 前端代码永远使用相对路径 `/api` / `/ws`，不得硬编码后端端口；后端目标端口只允许出现在 `vite.config.ts` 的代理配置或启动命令中。
- Vite 代理必须支持通过环境变量切换后端目标，默认指向 Agent 端口 `8099`；用户门禁时通过命令临时指向 `8003`。

**开发环境 `.env`（强制使用相对路径 + Vite 代理）**

```env
VITE_API_BASE_URL=/api
VITE_USE_MOCK=false
VITE_BACKEND_PROXY_TARGET=http://localhost:8099
```

**禁止**：开发环境把 `VITE_API_BASE_URL` 写成完整后端 URL（如 `http://localhost:8003/api`），这会触发浏览器 CORS 预检，导致本地调试失败。

**示例（`vite.config.ts` 必须配置开发代理）**

```typescript
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const backendTarget = env.VITE_BACKEND_PROXY_TARGET || 'http://localhost:8099'
  const wsTarget = backendTarget.replace(/^http/, 'ws')

  return {
    server: {
      port: 5199,
      proxy: {
        '/api': {
          target: backendTarget,
          changeOrigin: true,
        },
        '/ws': {
          target: wsTarget,
          ws: true,
          changeOrigin: true,
        },
      },
    }
  }
})
```

**规则**：
- 任何需要对接后端 API 的前端项目，**必须**在 `vite.config.ts` 中配置 `/api` 代理
- WebSocket 路径 `/ws` 必须单独配置 `ws: true` 代理，禁止前端代码直接写 `ws://localhost:<port>`
- 修改 `vite.config.ts` 或 `.env` 后**必须重启 Vite 开发服务器**才能生效
- Agent / Tester 启动前端时默认使用：`cd frontend && npm run dev -- --host 127.0.0.1 --port 5199`
- 给用户门禁验收时使用：`cd frontend && VITE_BACKEND_PROXY_TARGET=http://localhost:8003 npm run dev -- --host 127.0.0.1 --port 5175`

**示例（代码中读取）**

```typescript
const baseURL = import.meta.env.VITE_API_BASE_URL
```

---

## 6. API 调用封装

**规范说明**

- 使用 **单一 axios 实例**（如 `services/api.ts`），统一 `baseURL`、`timeout`。
- 在 **请求拦截器** 中附加 Token（若有）。
- 在 **响应拦截器** 中统一处理 401 等；禁止在每个页面重复写一套错误处理。
- 业务接口方法写在 `services/*.ts` 中，**禁止在组件内直接** `axios.get('/...')`。
- `baseURL` **禁止**硬编码 `http://localhost:8000`，须来自 `import.meta.env`。

**示例（`services/api.ts`）**

```typescript
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
```

---

## 7. 路由与导航守卫

**规范说明**

- 需要登录才能访问的路由，使用 `meta.requiresAuth`（或项目内等价约定）。
- 在 **`router/index.ts`** 的 `beforeEach` 中统一校验；未登录跳转登录页。

**示例（`router/index.ts` 片段）**

```typescript
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    next('/login')
  } else {
    next()
  }
})
```

路由表中为需登录页设置 `meta: { requiresAuth: true }`。

---

## 8. 开发计划（`docs/Plan.md`）

**规范说明**

- 进入前端开发后，先读 PRD，在 **`docs/Plan.md`** 中填写**前端部分**，并同步补齐后端开发拆解占位；不得把后端计划等待到用户人工验收之后才补。
- 每个页面须写清：功能点、Mock 数据范围、跳转来源与去向；作为用户与模型的共同依据。
- 开发前对齐清单；**可**在原型已确认后批量开发各页，再统一验收；每完成一页勾选对应项。

**示例（`docs/Plan.md` 模板）**

```markdown
# 开发计划

## 一、前端开发

### 基础设施
- [ ] 项目初始化（Vue 3 + TypeScript + 路由 + 布局组件）

### 页面清单
#### 页面 1：[页面名]
- 功能：[该页面包含的功能点]
- Mock 数据：[列出该页面需要的 Mock 数据内容]
- 跳转：[从哪来、到哪去]
- [ ] 开发完成

#### 页面 2：[页面名]
- 功能：...
- Mock 数据：...
- 跳转：...
- [ ] 开发完成

### 前端自动验收
- [ ] Agent/Tester 已完成页面启动、构建、路由跳转、Mock 数据一致性检查
- [ ] 发现的问题已自动修复或记录为阻塞

## 二、后端开发（前端自动验收通过后继续）
> 前端自动验收通过后，直接按业务功能拆解继续后端开发；不得等待用户人工验收作为门禁
```

---

## 9. Mock 数据

**规范说明**

- 先用 Mock 跑通**全部页面**的交互与跳转，再对接后端。
- **凡在界面上展示的 Mock 数据，须带 `[Mock]` 标识**（或项目统一约定的可见标识），便于与真实数据区分。
- 对接真实接口后，移除 Mock 与标识。

### Mock 数据集中管理（强制）

**Mock 数据必须集中存放在 `frontend/src/mocks/` 目录，禁止散落在各个组件或页面文件中。**

```
frontend/src/mocks/
├── auth.ts        # 登录相关的 Mock 数据
├── items.ts       # 商品相关的 Mock 数据
├── orders.ts      # 订单相关的 Mock 数据
└── index.ts       # 统一导出
```

### Mock 数据格式对齐（强制）

**每个 Mock 文件的数据结构必须与 `docs/api-contracts.md` 中定义的接口响应格式完全一致。**

示例（`mocks/auth.ts`）：

```typescript
// 格式严格遵守 api-contracts.md 中 POST /api/auth/login 的响应定义
export const loginSuccessResponse = {
  code: 200,
  message: "success",
  data: {
    access_token: "mock-token-xxx",
    user: {
      id: 1,
      name: "[Mock] 测试用户",
      email: "test@example.com"
    }
  }
}

export const loginFailResponse = {
  code: 401,
  message: "用户名或密码错误",
  data: null
}
```

**规则：**
- Mock 数据的 code、data 包装层、字段名、字段类型必须和 api-contracts.md 一致
- 后端开发完成替换时，只需要把 Mock 导入换成真实 API 调用，数据结构不用改
- 禁止在组件中硬编码 Mock 数据（如 `const users = [{id: 1, name: "test"}]`）

### Endpoint DTO 收敛（强制）

**内部实体可以是字段超集，但任何 Mock handler 返回给页面的响应必须按 endpoint 显式构造 DTO。**

强制规则：
- 禁止直接返回内部实体对象（如 `return doc`、`return user`、`return item`），必须为每个 endpoint 显式 map 出契约字段
- 禁止用一个宽泛实体类型承接同一功能域下所有接口响应；每个响应形态不同的 endpoint 必须有独立 TypeScript 响应类型
- 如果同一功能域有多个 endpoint（如 upload / list / status / detail），修复契约问题时必须一次性检查该功能域全部 handler 返回体、Mock 数据实体、service 类型和页面接收类型
- `frontend/src/types/` 中应区分内部实体类型与接口响应 DTO，例如 `DocumentEntity`、`KnowledgeDocumentListItem`、`KnowledgeUploadResponse`、`KnowledgeDocumentStatusResponse`
- 列表接口、详情接口、状态接口即使字段相似，也不得默认复用同一个 DTO；以 `docs/api-contracts.md` 的 endpoint 响应为准

**错误示例：**

```typescript
// 错误：直接把内部实体返回给 status endpoint，容易带出 upload_time 等契约外字段
return HttpResponse.json({
  code: 200,
  message: "success",
  data: doc,
})
```

**正确示例：**

```typescript
// 正确：按 GET /api/knowledge/documents/{id}/status 的契约显式构造 DTO
const statusResponse: KnowledgeDocumentStatusResponse = {
  doc_id: doc.doc_id,
  file_name: doc.file_name,
  status: doc.status,
  progress: doc.progress,
  message: doc.message,
  ...(doc.status === "indexed" ? { chunks_count: doc.chunks_count } : {}),
}

return HttpResponse.json({
  code: 200,
  message: "success",
  data: statusResponse,
})
```

---

## 10. 开发节奏与推荐顺序

**规范说明**

- **节奏**：基础设施 → 各页用 Mock 完成 → Agent/Tester 自动验收 → 自动进入后端开发。
- **禁止**：把“请用户验收前端”作为进入后端开发的阻塞门禁；只有业务方向不确定、原型明显偏离、或自动验证无法完成时才暂停询问用户。

**示例（节奏）**

```
基础设施（项目初始化、路由、布局）
  → 全部页面开发（Mock 数据）
  → Agent/Tester 自动验收（启动、构建、路由、Mock 数据一致性）
  → 自动进入后端开发
```

**示例（单页实现顺序）**

```
1. 路由配置（含守卫）
2. 页面骨架
3. API Service（可先对接 Mock / 占位）
4. 状态管理（Pinia store）
5. 组件拆分与优化
```

---

## 11. 原型参考（强制）

**规范说明**

- 开写页面前，先读取 `docs/prototypes/` 下与当前页面对应的原型。
- **Stitch**：阅读 `docs/prototypes/NN-界面名/index.html`（及样式）中的布局与视觉。
- **Pencil**：使用 Pencil MCP 的 `batch_get`、`get_screenshot` 等查看 `docs/prototypes/*.pen`。

（无固定代码示例；以实际原型路径为准。）

---

## 12. 布局与样式易错点

**规范说明**

- **多栏布局**：避免 `grid` / `flex` 默认等高导致某一栏内容撑高整行、破坏整体结构；工作台类页面宜固定视口高度，各栏使用 `min-height: 0` 与独立 `overflow` 滚动。
- **侧栏列表**：列表区域勿依赖会被拉伸或均分剩余高度的默认行为；列表容器应**顶部对齐**，保证从上往下稳定排布。

（无统一代码示例；按具体页面在 CSS 中落实。）

---

## 13. 常见错误对照

**规范说明**

下列为高频错误，编码与 Review 时对照检查。

**示例（错误 → 正确）**

| 错误写法                         | 正确写法                                       |
|----------------------------------|------------------------------------------------|
| `import.meta.env.API_URL`        | `import.meta.env.VITE_API_URL`（必须 `VITE_` 前缀） |
| 前后端共用同一个 `.env`          | 前后端各自独立 `.env`                          |
| 组件内直接 `axios.get(...)`      | 统一经 `services/` 封装调用                    |
| `baseURL` 写死 `localhost:<port>` | 从 `import.meta.env` 读取                      |
| 每页单独处理 401                 | 在 axios 响应拦截器中统一处理                  |
| `.env` 写完整后端 URL 触发 CORS  | `VITE_API_BASE_URL=/api` + Vite 代理配置       |
| 未配 Vite `/api` 代理            | 必配 `server.proxy['/api']` 指向后端端口       |
| WebSocket 直连 `localhost:<port>` | 配置 `/ws` 代理 + 前端用相对路径               |

---

## 14. 前端自动验收后的工程约定

**规范说明**

- 前端自动验收通过后，在后端开发阶段使用项目根下（或约定位置）的 **`backend/`** 目录开展后端工作；进度与拆解以 **`docs/Plan.md`** 与仓库结构为准。

（无代码示例。）

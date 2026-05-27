# SDD V6 — 系统级经验

> 记录跨项目可复用、能反哺 Harness 本体的经验。  
> 不记录具体项目的业务细节；项目细节写入 `Projects_Repo/<project-id>/.sdd/experience.md`。

---

## 2026-05-11｜移动端项目不得套用 Web 产品设计与 Web Rules

- **来源**：V5 → V6 架构升级讨论
- **经验**：当前 Harness 的产品设计 Skill 和 `dev-standards/frontend.mdc` 都偏 Web。移动端项目可以复用多 Agent 协同机制，但不能默认触发 Web 产品设计 Skill，也不能读取 Vue/Web 前端 rules。
- **规则**：
  - 移动端项目必须先警告用户当前缺少移动端规范
  - 用户确认继续后，要求用户自备 PRD / 原型 / API 契约 / Plan
  - 移动端客户端任务 `rules_files=[]`
  - 只有后端 API 任务才读取 backend rules

## 2026-05-11｜Bugfix 必须回查经验并反哺经验

- **来源**：V6 Bugfix 流程升级
- **经验**：Bugfix 不是单纯修代码，而是经验系统的入口。
- **规则**：
  - 修复前必须读取项目 `.sdd/experience.md`
  - 如果已有相关经验，必须分析为什么仍然犯错
  - 修复后必须写 bugfix 报告
  - 修复后必须更新项目经验

## 2026-05-12｜后端业务任务必须任务内完成前端真实联调

- **来源**：customer-service 自动化 Coding 复盘。项目所有任务显示 passed，但用户打开前端仍看到 Mock 数据。
- **经验**：前端 Mock 是产品交互和接口契约对齐阶段的工具；一旦进入后端业务任务，任务 Done Definition 必须包含“对应前端在 `VITE_USE_MOCK=false` 下调用真实后端”。否则后端只完成了 API，不代表用户功能完成。
- **规则**：
  - Planner 生成 Web 后端业务任务时，必须写入 `frontendIntegration.required=true`
  - 对应已有前端页面或 service 的后端任务，acceptanceCriteria 必须包含真实前端联调标准
  - Developer 完成后端业务功能时，必须同步修正对应前端 service / store / page，不能让默认验收路径继续走 Mock
  - Tester 不得只用 curl/API 判 PASS；必须验证 `VITE_USE_MOCK=false` 路径、真实后端请求和页面无 `[Mock]` 残留
  - 最终 E2E 只做全系统回归，不能替代单个后端业务任务内的首次真实联调

## 2026-05-12｜自动化开发前必须确认外部服务与 Tester 权限

- **来源**：SDD V6 自动化 Coding 复盘。缺少真实服务 Key 时，系统容易用 Mock/fallback 跑完任务并误判为完整联调。
- **经验**：外部服务配置不是后端任务中途才讨论的问题，而是进入多智能体自动化开发前的门禁。否则 Tester 没有完整权限，只能测 Mock/fallback，无法验证真实业务链路。
- **规则**：
  - `/sdd-start` 进入 Planner 前必须先确认外部服务清单
  - 清单必须包含服务名称、用途、配置字段、MVP 必需性、Tester 联调权限、缺失时策略
  - 必要 Key / 测试账号 / Base URL / 回调配置缺失时必须暂停索取
  - 用户明确选择不提供时，相关能力只能标记 Mock/fallback 降级验收
  - 真实 Key 不写入 PRD、Plan、tasks.json、测试报告或经验文件，只写入 `.env`

## 2026-05-21｜后端业务任务必须验证 Vite 开发代理配置

- **来源**：smart-customer-service T-010 用户登录闭环。后端登录接口开发完成，但前端请求始终失败，排查后发现 `vite.config.ts` 未配置 `/api` 开发代理，导致浏览器把请求识别为跨域，OPTIONS 预检异常。
- **经验**：Vite 代理是前后端本地联调的基础设施，不是"有报错才配"的补救措施。Developer 完成后端业务任务时，如果只改了前端 service 但没检查代理配置，Tester 的真实联调会莫名其妙失败，浪费大量时间排查 CORS/端口/中间件等错误方向。
- **规则**：
  - `frontend/vite.config.ts` 必须配置 `server.proxy['/api']` 指向后端端口（默认 `http://localhost:8000`）
  - `frontend/.env` 中 `VITE_API_BASE_URL` 必须使用相对路径 `/api`，禁止写完整 URL（如 `http://localhost:8000/api`）触发 CORS
  - WebSocket 路径 `/ws` 必须单独配置 `ws: true` 代理，前端代码禁止硬编码 `ws://localhost:8000`
  - Developer 输出前必查清单中增加 Vite 代理检查项；Tester 真实联调验证中增加代理配置检查
  - 修改 `vite.config.ts` 或 `.env` 后必须重启 Vite 开发服务器

## 2026-05-22｜固定高度容器的设计必须预留 20% 缓冲空间

- **来源**：customer-service T-003 员工端 Mock 实现。TicketCard 组件使用 `h-20`（80px）固定高度容纳三行文本，经过 5 次 Bugfix（空格、truncate 宽度、leading-tight、仍不够）才发现根本问题是**容器尺寸本身不合理**，最终增加到 `h-24`（96px）解决。
- **经验**：前端固定高度容器（`h-[固定值]`）容纳多行文本时，不能"刚好够用"，必须预留缓冲空间。浏览器实际渲染高度受字体、字重、抗锯齿、line-height 影响，原型工具中的尺寸往往比实际偏小。如果容器高度 = 内容理论高度，实际渲染时极易溢出截断。
- **规则**：
  - **固定高度容器设计公式**：`容器高度 ≥ 内容理论高度 × 1.2`（预留 20% 缓冲）
  - **内容理论高度计算**：`Σ(font-size × line-height × 行数) + Σ(gap) + padding（上下）`
  - **卡片高度经验值**（基于 `text-sm` 14px + `leading-tight` 1.25）：
    - 单行内容：最小 `h-12`（48px）
    - 两行内容：最小 `h-20`（80px）
    - 三行内容：最小 `h-24`（96px）
    - 四行内容：最小 `h-28`（112px）
  - **原型 vs 实际渲染**：Figma/Sketch 原型中的文字高度 ≠ 浏览器渲染高度，必须在真实浏览器中验证
  - **优先使用 `justify-between`**：固定行数（如 3 行）时，用 `justify-between` 替代固定 `gap`，让内容自动均匀分布更可靠
  - **Developer 输出前必查**：固定高度容器必须在浏览器中实际验证文字是否完整显示（上下不被截断）
  - **Tester 验证标准**：使用浏览器开发工具检查元素计算后的 `height`，确认内容高度 < 容器高度 × 0.85
  - **Bugfix 诊断清单**：文字被垂直截断（只显示上半部分）→ 不只是调整 `line-height`，还要评估**容器高度是否合理**

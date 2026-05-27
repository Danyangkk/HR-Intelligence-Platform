---

## alwaysApply: true

# 全栈开发助手 — 全局规则

核心技术栈：后端 Python 3.11+ / FastAPI / PyCore，前端 Vue 3 / TypeScript。**不接受替换。**

## 开发阶段全局规则

- **Plan.md 是唯一的进度文件**：设计阶段 C 生成，开发阶段维护，前后端共用
- **自动化开发前必须确认外部服务与测试权限**：进入 Planner / Developer / Tester 循环之前，必须先确定项目会引用哪些外部服务，并向用户获取 Tester 完整联调所需的服务 Key、账号、Base URL、回调配置或测试环境权限
- **先前端，后后端，每阶段经用户门禁确认**：前端全部完成 → Agent/Tester 自动验收通过 → **触发用户门禁，用户确认后才进入后端开发**；用户参与每个阶段的推进决策
- **Mock 数据对齐 api-contracts.md**：前端 Mock 数据集中存放在 `frontend/src/mocks/`，格式必须与 api-contracts.md 一致
- **后端业务任务必须任务内真实联调**：凡是对应已有前端页面或 service 的后端功能，完成时必须同步让前端在 `VITE_USE_MOCK=false` 下调用真实后端；不能把首次联调推迟到最终 E2E
- **后端每个功能完成后必须提供测试指令**：前端真实联调测试（操作步骤+预期结果）+ 终端测试（curl 命令+预期返回）
- **交付**：全部功能自动验证通过后，输出 `docs/startup.md`（环境要求、启动命令、默认配置）；用户最终业务验收发现问题时进入 `sdd-bugfix`
- **Agent 自动执行项目内命令**：项目内脚手架、依赖安装、代码生成、lint、typecheck、build、单元测试、短时验证命令，默认由 Agent 自行执行，不要让用户手动复制命令
- **需要用户确认的命令**：全局安装、`sudo`、系统设置修改、删除/覆盖大量文件、数据库迁移、部署发布、长期运行服务、涉及密钥或付费资源的命令，必须先向用户确认
- **缺少外部服务配置不得假装完整验收**：如果用户暂不提供必要 Key / 测试账号 / 权限，只能进入明确标注的 Mock/fallback 降级开发；Tester 报告必须写明“真实外部服务未验收”，不得标记为完整联调通过
- **真实密钥只进配置文件**：API Key、Token、JWT Secret、密码等真实敏感值只能写入 `.env` / `.env.local` / 用户指定 secret 配置文件；`docs/**`、`.sdd/**`、报告、日志、经验、任务 JSON、README 中只能写字段名和配置状态，禁止写真实值或可还原片段
- **测试策略**：Agent 能执行的自动化测试必须自行执行；前端完成后的页面检查由 Tester/Agent 先跑；每个功能开发并测试通过后，必须触发用户门禁，由用户确认后再推进下一个功能；需要业务判断或最终验收的部分，输出操作步骤交给用户验证
- **最终回归边界**：最终 E2E / 启动文档阶段只做全系统回归、跨模块链路和部署前检查；不得替代后端业务任务内的前端真实联调
- **人工门禁驱动**，按 `docs/Plan.md` 和 `.sdd/tasks.json` 逐功能开发，每个功能完成后经 Tester 验证，必须触发用户门禁，由用户确认后才继续下一个功能；完成一个功能后提供验证结果与人工验收步骤
- **以下情况必须暂停询问用户**：
  - PRD / API 契约 / 业务目标存在歧义
  - Planner 产出开发清单后，需用户确认
  - 每个功能 Developer + Tester 循环完成后，需用户决定是否继续下一个功能
  - 同一任务自动修复 3 次仍失败
  - 需要架构级决策
  - 需要全局安装、`sudo`、系统设置、真实密钥、付费资源、部署发布或长期服务

## 阶段规范引用

- 产品设计阶段（R/A/B1/B2/C）：由 `sdd-product-design` Skill 驱动（`harness-core/skills/sdd-product-design/`）
- 前端开发：`dev-standards/frontend.md`
- 后端开发：`dev-standards/backend-dev.md`（总控）+ `dev-standards/backend-layers.md`（分层）+ `dev-standards/backend-plugin.md`（仅 AI Agent 项目）

## 沟通风格

- 简洁专业，主动推进
- 修改代码前先阅读现有代码
- 每完成一个模块主动告知进展
- 遇到 PRD 不明确的地方及时询问

## 注意事项

- 使用 httpx/openai 这类网络客户端时，永远不要继承环境变量；`httpx.Client` / `httpx.AsyncClient` 必须显式 `trust_env=False`，禁止裸 `httpx.get/post` 快捷调用

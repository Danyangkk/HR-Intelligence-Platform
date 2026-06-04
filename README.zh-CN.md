# 人力智能中台 (hr-intelligence-platform)

> 人力数据中台 + 多智能体系统，通过"人审闭环"的改进 harness（trace、自动复盘、工单流转、测试门禁）实现**越用越聪明**。基于 LangGraph，含三角色分视图、薪资 TTL 二次确认、完整审计。**为生产级治理而构建，不只是 demo。**

English version: [README.md](./README.md)

---

## 为什么做这个项目

大多数 LLM agent demo 止步于"happy path 能跑"。本项目走得更远——把 agent 当作一个**需要被治理、被审计、能持续变好的生产系统**来设计，尤其是在 HR 这种敏感场景下，回答错了是真金白银的代价，泄露薪资就是合规事故。

它要回答的核心问题是：**如何让 AI agent 越用越聪明，但又不让它自己改自己？**

答案是一套**人审闭环的改进 harness**——真实使用产生 trace 和反馈；复盘 Agent 把 badcase 聚类成可行动的 finding；业务超管判断哪个值得修；技术超管动手改；测试门禁拦回归；上线后 finding 自动回填为"已修复"。系统每周都在变聪明，但**每一次改动都经过人审、过门禁、可审计**。

## 截图

**数据中台** —— 84个三级分类、4种来源类型，薪酬分类对无权角色锁定。
![Data Platform](docs/screenshots/01-data-platform.png)

**超级智能体** —— 多 Agent 编排带溯源面板；语义意图识别，0命中拒绝臆造。
![Super Agent](docs/screenshots/02-agent.png)

**复盘报告** —— 周度归因，双层产出：业务超管看业务语言摘要，技术超管看技术线索（节点路径、run_id）。
![Retrospective](docs/screenshots/03-retrospective.png)

**改进工单** —— 工单可追溯到来源 finding；任何人（含技术超管）都不能绕过红色测试门禁上线。
![Tickets](docs/screenshots/04-tickets.png)

*截图中的所有数据均为 mock。*

## 核心特性

**1. 人力数据中台**
- 84 个三级数据分类，分 4 种来源类型（飞书同步 / 手动上传 / 制度规则 / 报表）
- 三个固定事业部，全系统口径一致
- 文件解析（SheetJS）、数据预览、血缘追溯

**2. 多 Agent 系统（LangGraph）**
- Planner（语义路由，禁关键词枚举） + Supervisor（确定性派发）
- 5 个可复用 Agent：Resolver、Retriever、Analyst、Composer、Critic
- 可扩展 Skills（11 通用 + 8 流程） + 8 个 Tool
- 制度文档 RAG（Qwen embedding + 混合检索 + rerank），0命中拒绝臆造

**3. 生产级治理 Harness**
- **Trace**：每次运行记录节点级决策、工具调用、状态（不存敏感原文，问题存 hash）
- **复盘 Agent**（周度自动）：把 badcase 聚类成 finding，**双层产出**：业务摘要给业务超管（人话："什么问题、多严重、优先级"）+ 技术详情给技术超管（现象、根因假设、节点线索、依据 run_id）
- **改进工单流转**：采纳 / 驳回 / 存疑；工单关联到来源 finding；状态机：待处理 → 处理中 → 待验证 → 已上线，门禁失败自动退回
- **测试门禁**（CI）作为硬约束：任何人（含技术超管本人）都不能绕过红色门禁上线，**后端强制校验**（不只前端禁用按钮）
- **Eval harness**：三层评测（意图准确率 / 检索命中 / 答案质量 LLM-as-judge），定时 + 手动触发
- **存疑待办**：跨周追踪未决建议，本周同类问题再发生时自动标注"上周已存疑，本周又发生N次，建议重新评估"

**4. 三角色职责分离**
- **业务超管（HRD）**：决策者，看人话摘要做采纳/驳回/存疑；薪资访问权岗位自带（每次30分钟 TTL 二次确认 + 全程审计）
- **技术超管**：建设和运维系统、处理改进工单；**即使有系统权限，永久看不到薪资金额**（纵深防御）
- **普通员工**：读写业务数据；薪资永久隔离（意图识别阶段拒绝、字段脱敏、分类隐藏）
- 同样的数据、不同的视角：复盘报告对业务超管是"人话摘要"、对技术超管是"完整技术详情"——同一份 finding，两个展示模块

**5. 合规与安全**
- 薪资 30 分钟 TTL 二次确认（数据中台与智能体共用同一状态）
- 完整审计（谁、何时、查了谁、什么字段、什么事由）——但**从不记录薪资金额本身**
- 纵深防御：LLM 语义判定为主 + 关键词安全网兜底（只严不松）
- 角色归一化失败时 fail-safe 兜底到最低权限

## 系统架构

```
┌─────────────── 数据中台 ─────────────────────┐    ┌─── 超级智能体 (LangGraph) ───┐
│  84 个三级分类 · 4 种来源类型               │    │  Planner → Supervisor → 5    │
│  飞书 / 上传 / 制度 / 报表                  │◄───┤  Agent + Skills + Tools      │
│  审计 · TTL · 角色权限                      │    │  制度文档 RAG                 │
└────────────────────┬────────────────────────┘    └──────────┬────────────────────┘
                     │                                         │
                     │  每次运行产生 trace                     │
                     ▼                                         ▼
              ┌─────────────────── 改进 Harness ───────────────────────────┐
              │  Trace + 👍👎 → 复盘 Agent（周度）                          │
              │    ├─ 业务摘要（业务超管决策）                              │
              │    └─ 技术详情（技术超管动手）                              │
              │  采纳 → 改进工单 → 测试门禁 → 上线                          │
              │    └─ 上线后：自动回填 finding/badcase 状态 = fixed         │
              │  Eval（意图 / 检索 / 答案质量 三层）                        │
              └─────────────────────────────────────────────────────────────┘
```

## 技术栈

- **后端**：Python · FastAPI · PostgreSQL（pgvector）· Celery · LangGraph
- **LLM**：Qwen（embedding + chat）；Eval 第三层用 LLM-as-judge
- **前端**：原生 HTML/JS（数据中台 + 智能体 + 复盘/Eval/工单页）
- **部署**：Docker Compose
- **数据**：全程 mock 实体（框架真实、数据虚构）

## 目录结构

```
.
├── backend/                  # FastAPI 服务、Agent 运行时、harness
│   ├── src/
│   │   ├── services/         # 业务服务
│   │   ├── workers/          # Celery 任务（复盘、Eval）
│   │   └── main.py
│   ├── tests/                # router_cases、回归测试
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                 # 原生 HTML/JS 前端
│   ├── index.html            # 主应用（数据中台 + 智能体）
│   └── permission-admin.js   # 角色权限管理
├── docs/                     # 设计文档
│   ├── screenshots/          # README 截图
│   ├── 前端页面规格-权限重构.md
│   ├── 复盘Agent实现规格.md
│   └── ...                   # 路由 / 提示词 / harness / SOP 等
├── nginx/                    # 反向代理配置
└── docker-compose.yml
```

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/<your-username>/hr-intelligence-platform.git
cd hr-intelligence-platform

# 2. 配置环境变量
cp backend/.env.docker.example backend/.env.docker
# 编辑配置：Qwen API key、JWT secret、Postgres 密码

# 3. 启动
docker compose up -d

# 4. 访问
# 前端：http://localhost:8080
# 后端 API 文档：http://localhost:8080/api/v1/docs
```

默认测试账号（mock）：
- 业务超管（HRD）：`biz_hrd`
- 技术超管：`developer`
- 普通员工：`staff_user`

## 设计哲学

塑造这个系统的几条原则：

- **语义路由，禁关键词枚举**。关键词列表脆弱且永远列不全；意图分类由 LLM 做语义判定。关键词只作为 fail-closed 的安全网兜底。
- **岗位自带权限，不做细粒度授权**。薪资访问权随业务超管角色一起来，**不是**技术超管能下发的一个权限位——否则就破坏了职责分离。
- **纵深防御**。敏感判定（如薪资）作为**所有路由分支之前的前置闸门**，而不是散落在各处的检查——堵死老规则可能绕过新策略的后门。
- **复盘 Agent 不自动修**。它发现 finding；人决策；门禁兜底。"越用越聪明"不丧失问责。
- **两个读者、两种呈现、一份事实**。同一条 finding，两个模块：业务摘要给决策、技术详情给执行。
- **审计一切接触敏感数据的访问，但绝不记录敏感数据本身**。审计记的是"谁查了谁、什么字段、什么事由"，**永不记薪资金额**。

## 项目状态

这是一个作品集级项目：框架按生产级形态构建（权限、审计、harness、门禁、Eval），数据为 mock。**完整的改进闭环在 mock 数据上端到端跑通**。

## 许可证

MIT，详见 [LICENSE](./LICENSE)。

## 作者

**Danyang** · 18346103232@163.com

---

*本项目是对"生产级 AI Agent 系统该是什么样子"的一次探索——当它必须被治理、被审计、能持续变好，而不只是在 demo 里炫技。*

# hr-intelligence-platform · 人力智能中台

> 一套敢把 LLM Agent 放进 HR 领域跑"生产形态"的系统。答错要赔钱、泄露薪资是事故，所以这里把治理做成了主角：每次运行全程留痕，周度复盘自动找坏例，改进必须过测试门禁，评测的裁判本身也被校准 —— **AI 持续变聪明，但每一步变更都被人审、被门禁拦、可审计。**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-green.svg)](https://github.com/langchain-ai/langgraph)
[![Qwen](https://img.shields.io/badge/Qwen-chat·embedding·judge-purple.svg)](https://tongyi.aliyun.com)

**中文版 | [English](./README.md)**

---

## 它是什么

三块东西拼在一起：一个 HR 数据中台（84 类数据：花名册、考勤、薪酬、绩效、编制……），一条多 Agent 问答流水线（"杭抖离职率为什么涨？"这种问题进去，带引用、带口径、带局限声明的答案出来），以及绕着它们转的一整圈治理闭环。

问答主链路长这样：

```
用户提问
   ↓
Planner 语义规划   ←─ Critic 证据不足时打回（≤2 次）
   ↓
Supervisor 确定性调度
   ├─ Resolver        实体解析
   ├─ Retriever       多表并行取数（Send 扇出）
   └─ Document RAG    制度文档检索
   ↓
Analyst 分析
   ↓
Critic 质检 ── 证据不足 → 回 Planner ｜ 证据充分 ↓
   ↓
Composer 组稿（引用 + 指标口径 + 局限声明）
   ↓
答案 + 全程 trace
```

外圈治理闭环：**trace 落库 → 周度复盘 Agent 聚类坏例 → 人来决策 → 改进工单 → 测试门禁 → 评测基线更新**。机器发现问题，人拍板，门禁兜底。

## 特性

- **🧠 柔性在判断，刚性在执行**：意图识别、实体解析、薪资敏感判定全靠 LLM 语义（没有关键词枚举）；走哪条路、查哪张表、谁能看什么，全是确定性代码 —— 同一个计划跑一万次路径一致
- **🔁 质检回路**：Critic 核验证据够不够，不够打回 Planner 重查（最多 2 次）；实在不够就在答案里写明"证据不完整，仅供参考"，**宁可承认也不编**
- **⚡ 多表并行扇出**：一个问题要查三张表？LangGraph `Send` 同时派三个 worker，各查各的各自脱敏，单表挂了不拖累全局
- **🧾 RAG 拒绝编造**：制度文档混合检索 + rerank，只引现行版本、强制给出处，零命中的正确答案就是"查不到这条规定"
- **🔒 薪资纵深防御**：业务超管能看但每 30 分钟要二次确认 + 全程审计；普通员工在意图层就被拦；**技术超管有系统权限也永远看不到薪资数字**；LLM 全程不知道用户角色，伪造身份的 prompt 注入无从下手
- **🧮 LLM 解读，代码算数**：答案里每个数字都来自确定性代码或 calc 工具，不存在"模型口算错了"这种坏例
- **🧪 评测中心**：断言看得见、裁判可质疑、校准有数据（下面细说）
- **🚧 测试门禁硬规则**：红灯谁都不能发版，包括技术超管自己 —— 在后端强制，不是只在 UI 上摆个样子

## 截图

![数据中台](docs/screenshots/01-data-platform.png)

![超级智能体](docs/screenshots/02-agent.png)

![周度复盘](docs/screenshots/03-retrospective.png)

![改进工单](docs/screenshots/04-tickets.png)

![评测中心](docs/screenshots/05-eval-center.png)

*截图里的人和数都是模拟数据。*

## 评测中心：断言看得见，裁判可质疑

大多数项目的评测就是"跑个分挂页面上"。这里的评测回答四个实际问题：

**坏在哪个环节？** 意图判对没有（L1）、检索拿对证据没有（L2），都是代码逐项比对的确定性断言 —— 点开任意用例，"期望 vs 实际"左右并排，挂在哪一眼看清。

**裁判凭什么打这个分？** 最终答案由 LLM-as-judge 按四维打分（正确性 / 完整性 / 引用 / 合规），评判依据全摆出来：标准答案要点、红线、口径要求、逐维理由、违规项。你看完觉得它判错了，点"不同意"给个人工分 —— 攒满 20 条就开始计算**裁判和人类的一致率**，掉到 0.8 以下页面直接挂出"裁判分数仅供参考"。

**这次改动有没有用？** 每次跑批自动和上次 diff：**新挂**（上次过这次挂，你闯祸了）和**修复**（上次挂这次过，活干成了）分开列。总数会互相抵消骗人，流量不会。

**考卷出全了没有？** 覆盖矩阵：意图 × 层的用例计数，0 的格子标红；外加一份"哪些用例没配标准答案要点"的欠账清单。

门禁规则一句话：**确定性的拦（断言、planner 准确率、新挂），模糊的看（裁判分数只看趋势）** —— 模糊数字永远不配当门禁。

自带一套可一键重置的演示数据，剧情是完整的"基线良好 → 改版引入回归被门禁拦下 → 修复后通过"。

## 三档角色

| 角色 | 能干什么 | 薪资明细 |
|---|---|---|
| **业务超管（HRD）** | 对复盘 findings 拍板、看业务语言摘要 | ✅ 可看，每 30 分钟二次确认 + 全程审计 |
| **技术超管** | 建设运维系统、处理改进工单 | ❌ 永远不可见（纵深防御，防"有权限的人绕过前端"） |
| **普通员工** | 日常数据读写 | ❌ 意图层即拦、字段脱敏、分类隐藏 |

同一份复盘 findings 两种呈现：业务超管看大白话（"哪坏了、多严重、急不急"），技术超管看技术细节（现象、根因假设、节点线索、证据 run ID）。

## 快速上手

```bash
# 1. 克隆
git clone https://github.com/Danyangkk/hr-intelligence-platform.git
cd hr-intelligence-platform

# 2. 配环境变量
cp .env.example .env
# 填三样：Qwen API key、JWT secret、Postgres 密码

# 3. 一键起八个服务
docker compose up --build

# 4. 打开
# 前端       http://localhost:8080
# API 文档   http://localhost:8080/api/v1/docs
```

## 仓库结构

```
├── backend/
│   ├── src/agent/            # LangGraph 编排：七个 agent、19 个 skills、8 个 tools、路由总纲
│   ├── src/services/         # RAG、权限、审计、复盘、评测、飞书同步
│   ├── src/eval/             # 评测执行器：L1/L2 断言 + L3 LLM-as-judge
│   ├── eval/eval_set.yaml    # "考卷"：评测用例 + 期望（改题必须走 git review）
│   └── tests/                # 离线回归门禁（pytest -m "not online"）
├── pycore/                   # 自研轻量框架（PYTHONPATH 引入）
├── frontend/                 # 单文件原生 HTML/JS 前端
├── docs/                     # 设计文档、改造方案、README 截图
└── docker-compose.yml        # postgres(pgvector) · redis · minio · api · celery 等八件套
```

## 设计哲学

- **语义的事交给模型，确定的事交给代码** —— 这条原则在每一层重复出现：路由上、权限上、计算上、评测上
- **关键词安全网只能更严，不能放行** —— LLM 说不敏感但命中薪资关键词？按敏感处理
- **复盘 Agent 不自动修复** —— 它只提发现，人来决策，门禁来执行
- **审计一切碰敏感数据的行为，但绝不记录敏感数据本身** —— 记"谁为什么看了谁的记录"，不记薪资数字
- **裁判默认不被信任** —— 依据透明、可被质疑、一致率被持续测量

## 路线图

进行中（方案在 `docs/REFACTOR_PLAN_agent_flexibility.md` 和 `docs/EVAL_PLAN_assertion_grader.md`）：

- **目录驱动选表**：84 类目录注入 Planner 替代 few-shot 硬背，新增一张表 = 插一条记录，Agent 自动看见
- **混合取证**：一个计划同时带结构化 + RAG 两路证据，接得住"离职率为什么涨，和新考核制度有关吗"
- **节点级断言**：评测采样点铺满全部六个环节（含 Resolver 实体解析、Analyst 数值、Critic 行为）
- **Skill 两级披露**：全部 skill 一行简表 + 当前步骤所需的 1-2 个全文，SOP 不再被截断

## 状态

作品集级项目：框架按生产形态搭（权限、审计、trace、门禁、带校准的评测），数据是模拟的，完整改进闭环已在模拟数据上端到端跑通。

## 许可证

MIT — 见 [LICENSE](./LICENSE)。

## 作者

**Danyang** · 18346103232@163.com

---

*这个项目想回答的问题是：当一个 AI Agent 系统必须被治理、被审计、被持续改进 —— 而不只是被演示 —— 它应该长什么样。*

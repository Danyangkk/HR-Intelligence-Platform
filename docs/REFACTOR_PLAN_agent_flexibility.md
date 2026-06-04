# 改造方案：取证柔性化 + 意图与计划解耦（B 方案）

> 本文档面向 AI 编码助手（Cursor）执行。每节给出：改动文件、改动点、验收标准。
> 总原则不变：**柔性在判断（LLM 规划层），刚性在校验、降级与权限层**。
> 建议按 PR1→PR5 顺序提交，每个 PR 独立可回滚，全程保持 `pytest backend/tests` 绿灯。

---

## 背景

当前系统的"问题→表"映射知识只存在于 Planner 的 few-shot 范例（`backend/src/agent/prompts/agents.py` 的 `PLANNER_FEW_SHOT`）和规则降级的硬编码映射（`planner_rules.py` 的 `_default_structured_targets` / `build_plan`）中，84 个 L3 分类只有十几个被覆盖；计划结构被意图模板锁死（`_validate_plan` 按意图强制 subtask 序列），导致：

1. 新增数据表 Agent 不会自动发现，必须改 prompt 范例；
2. 混合取证（结构化数据 + 制度文档）无法被规划，"离职率为什么涨，和新考核制度有关吗"这类问题的制度证据一路会被静默丢弃；
3. RAG 实际只服务 policy 意图，且 `execute_retrieve_subtask` 只取 `target_l3[0]` 一个文档库；
4. forecast 意图有 analyze 无 critique，预测结论不质检；
5. Critic 触发 replan 的条件硬编码绑定意图集合。

改造方向（已确认的 B 方案）：**Planner 自由输出 subtask DAG，意图降级为治理标签；刚性退守为不变式校验 + 目录白名单 + 薪资前置闸门。**

---

## PR1：L3 目录化（数据基建）

### 1.1 Category 增加 description 字段

- 文件：`backend/src/models/__init__.py`
- `Category` 增加 `description: Mapped[str | None] = mapped_column(String(256), nullable=True)`
- 新增 alembic migration（`backend/alembic/versions/`）。

### 1.2 种子数据补描述

- 文件：`backend/src/seed/generated/categories.json` 及 `backend/scripts/generate_seed.py`
- 为全部 84 个 L3 节点补一句话用途描述（人工编写，重点消歧：异动记录 vs 调薪记录、各文档库的适用场景等）。
- `seed/run.py` 写入 description。

### 1.3 目录构建器

- 新文件：`backend/src/agent/catalog.py`

```python
"""L3 catalog — single source of truth for Planner's table knowledge."""
from functools import lru_cache

@lru_cache(maxsize=1)
def load_l3_catalog() -> list[dict]:
    """从 seed/generated 的 categories.json + templates.json 构建。
    每项：{id, path(一级/二级/三级名), source(structured|document),
          description, fields(前8个字段名，文档类为空)}"""

def catalog_prompt_block() -> str:
    """渲染为注入 prompt 的紧凑文本，每行：
    l3-2-1-4｜人事数据/花名册/在职花名册｜结构化｜<description>｜字段:工号,姓名,事业部,...
    l3-1-3-3｜管理制度/薪酬绩效/半年度考核规则｜文档(RAG)｜<description>
    全量约 5-6k 字符，可接受。"""

def valid_l3_ids() -> frozenset[str]: ...
def is_document_l3(l3_id: str) -> bool: ...
def is_structured_l3(l3_id: str) -> bool: ...
```

- source 判定规则：`l1-1 管理制度` 子树 = document；其余 = structured（与 Category.source 字段对齐，以 Category.source 为准，缺省按上述规则）。
- 注意：薪资表（`l3-4-*`）**必须列入目录**——Planner 需要知道其存在才能正确标 `payroll_sensitive`；权限拦截仍由 rbac 层负责，纵深防御不变。

### 1.4 注入 Planner prompt

- 文件：`backend/src/agent/planner_llm.py` 的 `_planner_system_prompt()`
- 仿照 `inject_router` 的模式：`PLANNER_SYSTEM` 中新增 `{{catalog}}` 占位区块，新增 `inject_catalog()`。
- 区块文案要点：「以下是全部可用数据分类目录。所有 retrieve 子任务的 target_l3 只能从本目录选取；文档(RAG)类分类只能配 retrieve_mode="rag"，结构化分类只能配 "structured"。」

### 1.5 few-shot 降级为格式教学

- 文件：`backend/src/agent/prompts/agents.py`
- `PLANNER_FEW_SHOT` 精简到 3-4 个范例，仅教 JSON 结构与拆解套路；范例头部加注释说明「表 ID 以目录为准，范例仅示意格式」。
- **必须新增 1 个混合取证范例**（见 PR3 验收用例）。

### 验收

- 新增 `backend/tests/test_catalog.py`：目录加载 84 项；每项有 description；source 分类正确；`valid_l3_ids()` 与 categories.json 一致。
- 现有测试全绿。

---

## PR2：校验改造 — 从意图模板到不变式

### 2.1 `_validate_plan` 重写

- 文件：`backend/src/agent/planner_llm.py`
- **删除**按意图的结构模板校验（policy 必须 `[rag, compose]`、lookup 必须 `[resolve, retrieve, ...]` 等全部移除）。
- **替换为不变式校验**（顺序检查，任一失败返回 False 走降级）：

```
I1  plan 非空，且每个 subtask 的 type ∈ {resolve, retrieve, analyze, critique, compose}
I2  compose 有且仅有一个，且位于最后
I3  存在 analyze ⇒ 其前必有至少一个 retrieve
I4  存在 analyze ⇒ 存在 critique，且 critique 在 analyze 之后、compose 之前
I5  每个 retrieve 的 target_l3 非空，且每个 ID ∈ valid_l3_ids()        ← 目录白名单
I6  retrieve_mode="rag" ⇒ 所有 target_l3 都是 is_document_l3
    retrieve_mode="structured" ⇒ 所有 target_l3 都是 is_structured_l3
I7  subtask 总数 ≤ 10（防失控）
```

- 薪资前置闸门（`should_reject_personal_salary_query` 等）**保持现状不动**，它在 `run_planner_async` 中先于计划校验执行。

### 2.2 assigned_agent 字段处理

- 现状：`route_after_supervisor` 只按 type 路由，`assigned_agent` 是装饰字段。
- 决定：**保留字段但由代码按 type 回填**（`_normalize_plan_item` 中：resolve→Resolver、retrieve→Retriever、analyze→Analyst、critique→Critic、compose→Composer），LLM 填什么都覆盖。Prompt 中告知该字段可省略。避免留下"看似可选 agent 实则无效"的迷惑接口。

### 2.3 规则降级路径保持死板 + 一致性保护

- `planner_rules.py` 的 `build_plan` / `_default_structured_targets` **不改结构**（降级路径应当最稳定），但其中所有硬编码 l3 ID 加一个测试断言：必须 ∈ `valid_l3_ids()`，防止目录演进后降级地图过期。

### 验收

- `backend/tests/test_plan_invariants.py`：每条不变式一个正例一个反例（共 ≥14 用例）；幻觉 ID `l3-9-9-9` 的计划被拒；rag 模式配结构化表被拒。
- `router_cases.yaml` 断言放宽：从"计划完全等于模板"改为"满足不变式 + 关键子任务存在（如归因类必须含 analyze+critique、policy 类必须含 rag retrieve）"。同步修改 `tests/router_harness.py` 的比对逻辑。

---

## PR3：混合取证 + 意图解耦的下游配套

### 3.1 ROUTER.md 改写

- 文件：`backend/src/agent/ROUTER.md`
- §3 主表从"强制规范"改写为"**推荐拆法**"，列旁注明：Planner 可按问题需要自由增删子任务，受不变式约束。
- §4 新增拆解规则：「分析类问题（原因/对比/趋势/预测）若语义上涉及制度、方案、规则、流程的变化或影响，应追加一个 retrieve_mode="rag" 的取证子任务，从目录的文档类分类中选库。」
- §6 skill 对照表同步修正（见 PR5 的编号问题）。

### 3.2 RAG 节点支持多文档库

- 文件：`backend/src/agent/supervisor.py` 的 `execute_retrieve_subtask`
- 现状 bug：`l3_id = l3_ids[0]` 只搜第一个库。
- 改为遍历 `target_l3` 逐库调用 `search_documents`（串行即可，文档库通常 ≤3 个；如需并行复用 Send 机制可作为后续优化），evidence 中每库一个 documents 块。

### 3.3 Composer 触发条件解耦

- 文件：`backend/src/agent/graph.py` 的 `_composer_node`
- 现状：`if state.get("intent") == "policy"` 才生成 RAG 草稿。
- 改为：`if any(block.get("kind") == "documents" for block in state.get("evidence") or [])`——只要证据里有文档块就生成草稿，再与结构化证据融合组稿。
- `composer_rag_llm.rag_answer_draft` 的 prompt 补充：混合场景下草稿仅覆盖制度部分，最终结论由 compose 阶段融合。

### 3.4 Critic 改为"对照计划核对证据"

- 文件：`backend/src/agent/critic.py`
- 规则路径：核对逻辑从"按意图查固定项"改为遍历计划中的 retrieve 子任务，逐路检查对应 evidence 块存在且非空（structured 查 rows、rag 查 hits）；analyze 存在则仍查 analysis.sufficient/factors。
- LLM 路径：user prompt 中加入「计划声明的证据需求清单 vs 实际证据块清单」，让模型按缺口判定，gaps 输出缺失的具体路（如 `"missing: rag l3-1-3-3"`）。
- **replan 触发条件改为：`needs_replan = (not sufficient) and replan_count < 2 and plan 中存在 analyze 子任务`**，删除对意图集合 `{compare, attribution, trend}` 的硬编码。

### 3.5 replan 能补 RAG 路

- 文件：`backend/src/agent/graph.py` 的 `_replan_node` + `planner_llm.py`
- replan 时把 Critic 的 gaps 写入 state（如 `replan_gaps`），Planner 重规划的 user prompt 中附带：「上一轮质检缺口：…，请在新计划中补足对应取证路。」

### 3.6 forecast 补质检

- 改造后此项自动成立（不变式 I4：有 analyze 必有 critique），无需单独写规则。在 ROUTER §3 推荐拆法表中把 forecast 的质检列改为 ●。

### 验收（端到端用例，加入 router_cases / 新增 test_hybrid_evidence.py）

1. 「离职率为什么涨，是不是和新考核制度有关」→ intent=attribution；计划含 ≥1 structured retrieve + 1 rag retrieve（目标为文档类 ID）；最终 citations 同时含 kind=data 与 kind=doc。
2. 「下季度客服编制缺口多少」→ forecast；计划含 critique。
3. rag 子任务命中 0 段 → Critic gaps 含 missing rag 路 → replan 后计划包含补足的 rag 子任务（或换库）。
4. 纯 lookup「张三上月请了几天假」→ 计划无 analyze/critique，不触发 replan，行为与改造前一致。

---

## PR4：观测与评估配套

- `backend/src/eval/`：Layer 1（意图准确率）保留不动——意图作为治理标签仍需观测。新增 Layer 1.5「计划合规率」：抽样计划过不变式校验器的通过率（确定性，零 LLM 成本）。
- 复盘 Agent（`services/harness_*`、复盘报告）：findings 聚类维度保持 intent，不需要改；但 trace 中 subtask 结构有了方差，确认复盘报告渲染对任意子任务序列健壮（遍历渲染而非按模板取位）。
- `docs/Plan.md` 追加本次改造的设计决策记录（意图=治理标签、不变式清单、为何降级路径保持死板）。

---

## PR5：仓库卫生清理（与上述改造无依赖，可先行）

### 必须修（错误/泄露/脏文件）

| # | 项 | 操作 |
|---|---|---|
| 0 | `SDD_V7_1/` 与 `.sdd/` 目录 | 若仍存在则整体删除（业务代码零依赖，已验证）；`.gitignore` 追加 `SDD_V7_1/` 与 `.sdd/` 两行 |
| 1 | `AGENTS.md` 引用已删除的 SDD 路径且含本机路径 `/Users/kk/Desktop/人力系统相关文档/` | **整文件替换**为下方 1a 节给出的内容（删除所有 SDD 路由表与本机路径，仅保留启动命令与结构说明） |
| 2 | `backend/src/logs/agent-run.log` | git rm，`.gitignore` 加 `**/logs/*.log` |
| 3 | `backend/logs/pycore_*.log.zip` | git rm，同上加 `*.log.zip` |
| 4 | `backend/celerybeat-schedule` | git rm（Celery beat 运行时 dbm 文件），`.gitignore` 加 `celerybeat-schedule*` |
| 5 | `frontend/test-nocache.html` | 删除（临时调试页） |
| 6 | `.github/workflows/ci.yml.disabled` | **启用它**。README 主打"test gate 红灯不能发版"，CI 却是关闭状态，与项目论点直接矛盾。如有不能启用的原因，在 README Status 节说明 |
| 7 | `pii-permission/SKILL.md` 旧红线与 rbac V2 矛盾（且 `build_skill_context` 会把它注入 LLM prompt，可能导致合法确认后仍过度拒绝） | description 与 SOP 改为：「个人薪资明细仅业务超管在 30 分钟确认 TTL 内可见，全程审计；技术超管/普通员工任何环节不得输出；无确认态下薪酬仅部门级聚合」 |
| 8 | `loader.py` SKILL_IDS 注释错位：头注释写 G1–G11+P1–P7 实际 8 个流程型；`process-turnover-risk-alert` 标 `# P5` 与 compensation-review 重复 | 修正编号为 P1–P8，头注释同步；ROUTER.md §6 对照表一并核对 |
| 9 | README.md / README.zh-CN.md 第 43 行「11 通用 + 7 流程」 | 改为「11 通用 + 8 流程（另 1 个 intent-planning 已废弃迁入 ROUTER.md）」 |

#### 1a. AGENTS.md 替换内容（原样写入，整文件覆盖）

~~~markdown
# HR Agent — 项目入口

## 后端启动（本地）

```bash
cd backend
PYTHONPATH=.. python3.11 -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

## Docker

```bash
docker compose up --build
```

配置：`backend/.env.docker`（Compose 挂载为容器内 `backend/.env`）；本地开发可读项目根 `.env`。

## 结构

- `pycore/` — PyCore 框架（PYTHONPATH 引入，不 pip 安装）
- `backend/src/` — 业务代码（`src.*` 包）
- `frontend/` — 纯 HTML/JS 前端
- `docs/` — 设计文档（含本改造方案 REFACTOR_PLAN_agent_flexibility.md）
~~~

### 建议做（结构优化）

| # | 项 | 建议 |
|---|---|---|
| 10 | ~~SDD_V7_1 拆独立仓库~~ | **跳过**——目录已在前置步骤删除 |
| 11 | `backend/src/agent/skills/intent-planning/` 已废弃 | 目录删除，`SKILL_IDS` 中移除（确认 `skills_for_agent` 无引用后） |
| 12 | `docs/复盘报告页面改进TODO.md`（658 行过程文档） | 移入 `docs/archive/` 或删除，避免与现状混淆 |
| 13 | ~~两个 pycore 重复~~ | **跳过**——SDD_V7_1 删除后仅剩根目录一份 |
| 14 | README 增补 | 「Repository layout」节补 `pycore/` 的定位说明；本次改造后补"目录驱动的取证规划"小节 |

---

## 执行顺序与回归基线

1. PR5（卫生清理）→ 2. PR1（目录）→ 3. PR2（校验）→ 4. PR3（混合取证）→ 5. PR4（观测）。
2. 每个 PR 合并前：`pytest backend/tests` 全绿 + `router_harness` 回归通过。
3. PR2 合并后跑一次全量 eval（三层），记录基线；PR3 合并后对比，意图准确率不得下降，新增混合用例通过。

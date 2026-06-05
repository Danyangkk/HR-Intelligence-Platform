# PR8：Skill 两级披露 — Loader 改造方案

> 面向 Cursor 执行。独立改造，只动 `backend/src/agent/skills/loader.py` 与 `backend/src/agent/llm_runner.py`，与主链路（PR1-PR3）、Eval（PR6/PR7）无代码冲突，可在任意间隙执行。

## 执行规则（必读）

1. **不交叉**：把手头正在进行的 PR 完成验收后再开工本 PR；不得与 Eval / 主链路改造并行改同一批文件。
2. **范围锁定**：只改 `loader.py`、`llm_runner.py`；**不动 schema、不动主链路**（planner / supervisor / nodes 等）。
3. **映射表以本文档为准**：`primary_skills_for` 的 agent/subtask/intent → skill 映射**不得自行发明**；流程型 skill 的「命中」沿用现有 `skills_for_agent` + `INTENT_PROCESS_SKILLS`，不重写业务规则。
4. **回归门禁**：改造前、改造后各跑一次 `router_harness`（见验收第 3 条），结果须一致；全量 `pytest -m "not online"` 零新增失败。
5. **行为不退化**：prompt 结构会变，但 Planner 路由与离线回归用例不得下降；若 agent LLM 输出漂移，优先调简表措辞，不回滚两级结构。

## 背景与问题

现状（`llm_runner.build_skill_context`）：按 agent+intent 选出绑定 skills，取前 4 个，每个 SKILL.md 正文**截断 2000 字符**注入该 agent 的 LLM 上下文。两个问题：

1. **SOP 被腰斩**：流程型 skill 的 SOP 较长，2000 字符截断经常切掉后半段步骤——模型按半份规范干活；
2. **无关全文浪费 token**：4 个 skill 全文（共约 8k 字符）整体注入，但当前子任务通常只需要其中 1-2 个的全文，其余只需"知道存在"。

## 目标设计：两级披露（程序化选择，非模型自选）

- **第一级 · 简表（全部绑定 skill，各一行）**：注入该 agent 全部绑定 skill 的 `id + frontmatter 描述`，让模型知道方法论全集的存在；
- **第二级 · 全文（按子任务精选 1-2 个）**：由代码按 `(agent, subtask_type, intent)` 映射选出当前步骤的主 skill，注入**完整正文，不截断**。

选择权在代码不在模型（与全系统"柔性在判断、刚性在执行"一致）；本 PR 不引入模型自选 skill 的工具循环。

## 改动点

### 1. `skills/loader.py`

- 新增 `skill_meta(skill_id) -> {id, name, description}`：解析 SKILL.md frontmatter，`lru_cache`；
- 新增 `primary_skills_for(agent, subtask_type, intent, retrieve_mode) -> list[str]`（≤2 个），映射表显式写在代码中：

| agent / 子任务 | 主 skill（全文注入） |
|---|---|
| Resolver / resolve | entity-resolution |
| Retriever / retrieve (structured) | structured-retrieval |
| Retriever / retrieve (rag) | document-rag |
| Analyst / analyze · intent=trend | trend-analysis |
| Analyst / analyze · intent=compare | compare-benchmark |
| Analyst / analyze · intent=attribution | attribution-methodology + 命中的流程型 skill（如有，共 2 个） |
| Analyst / analyze · intent=forecast | trend-analysis |
| Critic / critique | evidence-validation |
| Composer / compose | answer-composition |

- 流程型 skill 的命中沿用现有 `skills_for_agent` 的意图映射逻辑，不重写；
- `metric-dictionary` 与 `pii-permission` 为横切 skill：仅进第一级简表，不占第二级名额（其关键红线已由 rbac 代码与 prompt 全局段保障）。

### 2. `llm_runner.build_skill_context` 重写

输出结构（顺序固定，便于回归比对）：

```
[可用方法论简表]
- structured-retrieval：先确认模版字段再按标准值筛选…
- metric-dictionary：算指标前必查统一口径…
（该 agent 全部绑定 skill，各一行）

[本步骤执行规范]
=== structured-retrieval（全文）===
…SKILL.md 完整正文…
```

- 第二级总预算 8000 字符：单个 SKILL.md 超 6000 字符时在**章节边界**截断并附「（后续章节略）」标记，禁止句中硬切；
- 移除原 4×2000 逻辑。

### 3. Skill 体积守门测试

新增 `tests/test_skill_sizes.py`：断言每个 SKILL.md 正文 ≤ 6000 字符（超限即测试失败，迫使作者拆分或精简，而不是依赖运行时截断）。当前 19 个 skill 先全量检查，超限的在本 PR 内精简至达标。

## 验收

1. 单测：`primary_skills_for` 对上表每行一个用例；`build_skill_context` 输出包含主 skill 的**末段 SOP 文本**（防腰斩回归）；简表行数 = 该 agent 绑定 skill 数；
2. `test_skill_sizes.py` 全绿；
3. **行为回归（router_harness 前后对比）**：
   ```bash
   cd backend
   # 改造前基线（保存输出以便 diff）
   PYTHONPATH=.. pytest tests/test_router.py -m offline -q | tee /tmp/router_before_pr8.txt
   # 完成 loader.py + llm_runner.py 改造后
   PYTHONPATH=.. pytest tests/test_router.py -m offline -q | tee /tmp/router_after_pr8.txt
   diff /tmp/router_before_pr8.txt /tmp/router_after_pr8.txt   # 应无失败数差异
   ```
   > 说明：`router_harness` 测 Planner 离线路由，不直接读 `build_skill_context`；本 PR 改的是 Resolver/Retriever/Analyst/Critic/Composer 的 LLM prompt。Planner 路由须保持 24 passed；agent 侧由单测 + 可选 eval Layer 1 补充观测。
4. 门禁不变：`pytest -m "not online"` 相对基线零新增失败。

## 风险与回滚

改动集中在两个文件且不触 schema，回滚 = revert 单个 commit。最大风险是 prompt 结构变化引起各 agent 输出风格漂移，已由验收第 3 条覆盖；若回归下降，优先调整简表措辞而非回滚两级结构。

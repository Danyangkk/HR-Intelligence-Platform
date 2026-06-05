# Eval 改造方案：断言可见化 + Grader 校准（PR6 / PR7）

> 面向 Cursor 执行。独立于主链路改造（REFACTOR_PLAN 的 PR1-PR5），其中 PR6 可立即开工；PR7 中 7.4/7.5 依赖主链路改造的 PR2/PR3 完成。
> 背景结论（已核实代码）：系统的 assertion 与 grader 均已存在——Layer 1/2 是代码二值断言，Layer 3 是 LLM-as-judge（四维 rubric）；且 `EvalCaseResult` 已按次快照 `expected` / `actual` / `score_detail` / `judge_reasoning` 落库。缺口在于：断言与评判依据在前端不可见、judge 无校准、无方差测量、分数无门禁牙齿、评测集覆盖薄。

---

## PR6：Eval 透明化 — 断言可见、评判可质疑

### 6.1 后端 API（数据已在库里，只做查询暴露）

- `GET /api/v1/eval/runs/{run_id}/cases`
  返回该 run 全部 `EvalCaseResult`，字段含 `case_id, layer, passed, score, score_detail, expected, actual, judge_reasoning`；排序：`passed` 升序（失败在前）、layer 升序。
- `GET /api/v1/eval/runs/{run_id}/diff`
  与上一个 run（或 `?against={run_id}` 指定基线）逐 case 比对，返回 `{regressed: [case_id...], fixed: [case_id...], failure_clusters: [{stage, intent, count, case_ids}...]}`（聚类 = 按 stage × intent 分组失败 case，按 count 降序）。
- `GET /api/v1/eval/coverage`
  基于 `backend/eval/eval_set.yaml` 统计：
  a) 「意图 × 层」case 数矩阵；
  b) expected 字段完备度清单（缺 `answer_points` / `forbid` / `metric_callouts` 的 case_id 列表）。

### 6.2 前端：eval 页面新增下钻（沿用现有约定：`admin-eval` 双栏、`.modal`、`.sheet-table`、CSS 变量与 btn 样式，不引入新框架/新组件体系）

**A. Case 列表（嵌入现有 `#evalRunDetail` 报告区下方）**

- 报告汇总卡片之下新增「用例明细」区块，用 `.sheet-table` 渲染，列：
  `case_id | query（截断 30 字，title 显全文）| 意图 | L1 | L2 | L3 分 | flaky`
- L1/L2 列：✓（`--ok` 绿）/ ✗（`--err` 红）/ —（该层未跑，`--t3` 灰）；L3 列显示 overall 分，<4 标黄；
- 默认排序：失败优先（任一层 ✗ 在前），其后按 layer3 分升序；
- 行点击 → 打开 case 详情弹窗（复用全站 `.modal` 模式，新增 `#evalCaseModal`）。

**B. Case 详情弹窗 `#evalCaseModal`（核心交付物，设计稿见聊天中的 mockup）**

- 头部：`case_id · query`，右侧「查看 trace」链接（跳转该 case 的 agent run trace 页）+ 关闭按钮；
- 主体三个区块自上而下，**三层统一为「期望 expected（左）vs 实际 actual（右）」双栏对照**（`grid-template-columns: 1fr 1fr`），区块标题行右侧放该层 pass/fail 灯：
  1. **Layer 1 意图与计划断言**：左栏 = expected.intent + plan_constraints（如有）；右栏 = 实际 intent + 实际计划摘要（各路 retrieve 模式与数量、含哪些阶段），逐项后缀 ✓/✗；fail 时右栏下方列 `score_detail.mismatches` 原文（等宽字体）；
  2. **Layer 2 检索命中断言**：左栏 = 期望命中的文档块/表逐条；右栏 = 实际证据逐条（结构化块显示行数、文档块显示命中段数），与期望匹配的后缀 ✓ 绿，期望中未命中的在右栏占位显示「0 段/0 行 ✗ 未命中」红色；
  3. **Layer 3 judge**：左栏「评判依据」：`answer_points` 逐条、`forbid` 红线、`metric_callouts` 口径、`expected_citations`；
     右栏「被评对象」：答案全文（`max-height: 240px; overflow-y: auto`）+ 实际 citations；
     栏下四个维度分徽章（correctness/completeness/citation/compliance，≥4 蓝、<4 黄、≤2 红）+ overall + judge reasoning 全文 + violations 列表（红色）；
- 底部反馈条（6.3）：「同意 / 不同意」两按钮 + 人工 overall 分（1-5 数字输入）+ 备注输入框 + 提交；提交成功后反馈条替换为「已记录：同意/不同意 · 人工分 n」。
- 数据来源：打开弹窗时按 `case_id` 过滤 6.1 接口已拉取的列表数据（一次拉全量，前端过滤，不逐条请求）。

**C. 覆盖视图（`admin-eval` 顶部操作栏右侧加「覆盖」按钮，弹 `#evalCoverageModal`）**

- 上半：「意图 × 层」矩阵表（行=9 意图，列=L1/L2/L3，格内 case 数，0 标红底）；
- 下半：「expected 完备度」清单——缺 `answer_points` / `forbid` / `metric_callouts` 的 case_id 分组列出，全齐时显示绿色「完备」。

**D. 状态与空态（全部复用现有 `.rv-empty` / `.muted` 写法）**

- 列表加载中：`rv-empty` 显示「加载中…」；接口失败：「加载失败，点击重试」可点击重拉；
- 旧 run（无 expected 快照的历史数据）：详情弹窗对应区块显示「该次运行未保存断言快照」，不报错；
- judge 未评分（`scored=false`）的 case：L3 区显示 `error` 原文（如 llm_call_failed），反馈条隐藏。

**E. 报告区指标卡（定稿：四卡方案 + 统一命名）**

| 卡片 | 数值 | 副注（10px 灰字，常驻） |
|---|---|---|
| **assertion** | 代码断言通过/总数（如 128/136） | 「代码断言通过 / 总数」 |
| **grader 均分** | judge overall 平均 + 相对上一 run 的变化量（如 4.31 ↓0.2） | 「模型裁判 overall 平均（1-5）」 |
| **grader 校准** | judge 与人工评分一致率（如 0.86） | 「与人工评分一致率（<0.8 预警）」；<0.8 时本卡红框并触发页顶警告横幅 |
| **最弱环节** | 失败聚类最大簇（如 retrieve · rag 路） | 「失败聚类最大簇」；数据来自 diff 接口的 failure_clusters |

报告头部保留：门禁通过/未过徽章（planner 准确率 vs 阈值）+ flaky 计数 + 覆盖矩阵按钮。

**命名约定（重要，避免前后端词汇漂移）**：前端展示统一用 `assertion / grader 均分 / grader 校准`；代码内部沿用既有 `judge_*` 命名（layer3、judge_reasoning、judge_calibration 等）不做重命名，两套词的映射在评测集文档页（见 6.2-C 覆盖弹窗内附「名词解释」节：assertion=确定性代码断言；grader=模型裁判 LLM-as-judge；校准=裁判与人工的一致率）。

diff 接口（6.1）继续保留：除供「最弱环节」卡取数外，用例明细表增加「较上次」筛选（新挂 / 修复 / 持平），新挂行加红色 regressed 角标。

### 6.3 Judge 反馈控件（为 7.2 校准积累数据）

- 新表 + migration：
  `EvalJudgeFeedback(id, case_result_id FK→eval_case_result, verdict ENUM(agree/disagree), human_overall SmallInteger nullable, note Text nullable, created_by String(64), created_at)`
- 抽屉 L3 区加控件：同意 / 不同意 + 人工 overall 分（1-5）+ 备注，提交落库。

### 验收

- 任一历史 run 可下钻到单 case，三层 expected vs actual 与 judge 全部依据可见；
- 提交一条 disagree + human_overall 反馈成功落库；
- 覆盖矩阵正确反映当前 eval_set.yaml。

---

## PR7：Eval 体系强化（五项缺口）

### 7.1 Layer 1 准确率入门禁

- `eval/runner.py` 收尾时计算 `layer1_accuracy = layer1_pass / layer1_total`；
- `EvalRun` 新增 `gate_passed: bool` 字段 + migration，阈值 0.90（模块级常量，可配置）；
- 前端 run 列表对 `gate_passed=False` 显示红牌；
- 边界说明：Layer 1 走真实 LLM，**不进 pytest/CI 门禁**（offline 门禁仍由 router_cases.yaml 承担）；`gate_passed` 作为发版 checklist 的人工检查项，写入 README 发布流程说明。

### 7.2 Judge 校准

- 新脚本 `backend/scripts/judge_calibration.py`：
  读取 `EvalJudgeFeedback` 中带 `human_overall` 的样本（样本数 <20 时输出"样本不足"并退出）；
  一致判定：`|judge_overall − human_overall| ≤ 1`；
  输出一致率报告（总体 + 按意图分组）；
- 一致率 < 0.8 时，eval 页面展示提示「judge 分数仅供参考，需重新校准 rubric」；
- 文档注明已知风险：judge 与被评系统同为 Qwen，存在同源偏好，人工校准集是唯一的锚。

### 7.3 方差测量

- eval_set.yaml 的 case 支持 `critical: true`；
- runner 对 critical case 重复执行 3 次：L1 取多数表决记 pass；三次结果不一致记 `flaky=true`；
- `EvalRun` 新增 `flaky_count` 字段；run 报告区分「真失败」与「flaky」；
- 默认仅安全类、薪资类、归因类 case 标 critical（控制 LLM 成本）。

### 7.4 计划合规断言（依赖主链路 PR2/PR3；确定性代码断言，归入 Layer 1）

- case 的 expected 新增可选块：

```yaml
plan_constraints:
  must_include_rag: true          # 计划须含 ≥1 个 rag retrieve 子任务
  rag_target_source: document     # rag 子任务目标须为文档类分类
  min_retrieve_routes: 2          # 取证路数下限
  must_include: [analyze, critique]
```

- 实现位置：`eval/layer1.py`（计划在 planner_state 中即可断言，无需全流程）；
- 断言失败计入 Layer 1 fail，mismatches 写明违反的约束项。

### 7.5 评测集扩充（30 → 约 45 条；依赖主链路 PR3）

- 混合取证 ≥3 条（带 plan_constraints，例：「离职率为什么涨，是不是和新考核制度有关」）；
- 归因 / 对比 / 趋势每意图补到 ≥4 条；
- replan 路径 ≥2 条（构造证据必然不足的问题，断言 trace 含 replan 且 ≤2 次）；
- pass_with_limit ≥1 条（断言最终答案含局限声明文案）；
- 薪资三档角色各 ≥1 条（业务超管确认后放行 / 技术超管拒 / 普通员工拒）；
- 所有新 case 的 expected 写齐 answer_points 与 forbid（配合 6.1 完备度视图清零）。

### 7.6 节点级断言框架（stage 化——替代"挂靠 L1/L2"方案）

> 设计决策：断言按**节点（stage）**组织而非塞进三层，否则 L1 失败分不清是意图错还是实体错，准确率指标互相污染。原"三层"重新表述为：**五个确定性断言 stage + 一个 judge stage**。

**Schema 改动**：

- `EvalCaseResult` 新增 `stage: String(16)` 列（migration），取值 `planner / resolver / retrieve / analyst / critic / answer`；存量数据迁移映射 layer 1→planner、2→retrieve、3→answer；`layer` 列保留一个版本后删除；
- `EvalRun` 的分层统计列改为 `stage_stats: JSONB`（`{"planner": {"total": n, "pass": n}, ...}`），避免每加 stage 就加列；7.1 的 `gate_passed` 阈值对象改为 `stage_stats.planner` 的准确率。

**各 stage 的 expected 块与判定**（均为确定性代码断言，answer 除外）：

```yaml
expected:
  planner:                       # 意图 + 计划结构
    intent: attribution
    plan_constraints: { must_include_rag: true, min_retrieve_routes: 2 }
  resolver:                      # 实体解析
    entities: { person_id: "A0123", org: "杭综" }
  retrieve:                      # 证据命中（原 Layer 2）
    doc_chunks: ["半年度考核规则·§3"]
    tables: ["l3-2-5-1"]
  analyst:                       # 关键数值（带容差）
    checks:
      - { field: "turnover_rate_latest", value: 0.083, tol: 0.001 }
  critic:                        # 质检行为
    decision: replan             # pass / replan / pass_with_limit
    max_replans: 2
    limitation_required: false
  answer:                        # LLM-as-judge（原 Layer 3，rubric 不变）
    answer_points: [...]
    forbid: [...]
```

- case 按需声明 stage：未声明的 stage 不执行、不计入统计，前端显示「—」；
- 每个声明的 stage 落一行 `EvalCaseResult`（expected/actual/passed/mismatches 快照齐全）；
- critic stage 的 actual 从 trace 与 state 提取（critic_decision、replan_count、答案是否含局限声明文案）。

**前端联动（覆盖 6.1/6.2 的对应表述）**：

- 6.1 覆盖矩阵改为「意图 × stage」（9 行 × 6 列）；
- 6.2-B 详情弹窗改为：按 case 声明的 stage 逐个渲染「期望 vs 实际」双栏区块（排版规范不变），未声明的 stage 折叠为一行「— 未声明断言」；
- 6.2-A 列表的 L1/L2/L3 三列改为六个 stage 状态灯（✓ / ✗ / —），列宽收窄。

### 验收

- 全量 eval 一次通过：gate_passed 正确计算并在前端可见；critical case 出现 flaky 统计；混合取证 case 的 plan_constraints 断言生效；覆盖矩阵无空格、完备度清单为空。

---

## 执行顺序

1. **PR6 可立即开工**，与主链路改造（PR1-PR3）无代码冲突；
2. **PR7 依赖**：7.1/7.2/7.3 依赖 PR6（反馈表与页面）；7.4/7.5 依赖主链路 PR2/PR3（断言对象是新计划结构）；
3. 门禁标准沿用：`cd backend && PYTHONPATH=.. pytest tests -m "not online" -q` 相对基线零新增失败；
4. PR7 完成后以扩充集重建 eval 基线，后续所有发版以该基线对比。

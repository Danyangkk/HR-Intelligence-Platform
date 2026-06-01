# 复盘 Agent 实现规格

> 从《复盘Agent设想存档.md》转为正式实现规格。本 Agent **只读**消费 harness 的 trace + 反馈，每周自动产出**复盘报告**（量化概览 + 问题归因 + 改进建议），交人审，绝不自动改任何配置。配套《AgentHarness实现规格》《反馈与Badcase采集规格》《前端页面规格-权限重构》§3.5《改进闭环SOP》。
>
> 作品集说明：本轮实现"完整规格 + 后端骨架 + mock 周报数据"，让前端复盘页能跑通看效果；真实数据驱动等系统跑起来后接上。

---

## 0. 红线（最先看）

1. **只读、不自动改**：能读 trace/反馈、能写报告、能生成工单，**绝不**自动改 ROUTER/prompt/数据/任何配置。改动一律经 ⑤SOP 流程：人审 → 改 → 加 Test 用例 → 过门禁 → 上线。
2. **隐私边界**：只消费**全量聚合元信息**（意图分布、badcase 原因比例、👍/👎聚合率、趋势），**绝不展示个人逐条问答原文**。问题在 trace 中以 hash 存储（已由 AgentHarness 保证）。报告中也不含薪资数值（结构上拿不到）。
3. **结论可追溯**：每个结论必须挂依据的 `run_id` 列表，可点开查看依据。
4. **区分事实与推测**：统计数字标 `[事实]`，归因解释标 `[推测]`，不得把推测写成事实。
5. **复盘只看健康度，不监控员工**：不输出"谁问过什么"，只输出"系统在哪类问题上表现如何"。

---

## 1. 定时任务与触发

- **定时**：每周一 02:00 自动跑（Celery beat），分析窗口=过去 7 天。
- **手动触发**：技术主管可在前端「复盘报告」页点「立即重新生成本周报告」（用于演示和补跑）。
- **任务幂等**：同一窗口重复跑覆盖最新一份，不产生重复报告。
- **失败兜底**：任务失败写日志告警，前端报告页提示"上次生成失败，可手动重试"。

---

## 2. 数据消费（来源全部在已有表里）

- `agent_run` / `agent_node_trace`（AgentHarness 已建）
- `agent_feedback`（反馈采集已建）
- `agent_run` 上的 auto_badcase / badcase_reason / user_feedback / review_status

**只读，绝不写回这些表**（除复盘自己的输出表，见 §4）。

---

## 3. 分析步骤（pipeline）

```
①拉数据(过去7天)
  ▼
②聚合统计(纯 SQL,不用 LLM) → 概览段
  • 总问答数、意图分布、👎率、超时率、RAG 0命中率
  • badcase 原因分布(timeout/replan_exhausted/rag_zero_hit/clarify/user_down)
  • 与上周对比(↑↓百分点)
  ▼
③聚类与归因(LLM) → 归因段
  • 把 badcase 按"意图+原因+特征模式"聚类
  • 每个聚类产出 [事实]描述 + [推测]假设, 挂依据 run_id
  • 严格按归因 prompt(§5)的护栏
  ▼
④生成改进建议(LLM) → 建议段
  • 针对每个聚类提建议(改 ROUTER / 改 skill / 补数据 / 调参)
  • 每条建议关联依据聚类
  ▼
⑤落库 review_report(s) + 关联 review_report_finding(s)
  ▼
前端复盘页读取展示
```

---

## 4. 数据模型（落库）

```
review_report
  id              bigserial PK
  week_start      date
  week_end        date
  status          text          -- generating | ready | failed
  generated_at    timestamptz
  total_runs      int
  thumb_down_rate numeric
  timeout_rate    numeric
  rag_zero_rate   numeric
  intent_dist     jsonb         -- {aggregate:0.32, policy:0.21, ...}
  badcase_reason_dist jsonb     -- {rag_zero_hit:0.42, clarify:0.28, ...}
  vs_last_week    jsonb         -- {total_runs_delta:+5%, thumb_down_delta:-1.2pct, ...}

review_report_finding
  id              bigserial PK
  report_id       bigint → review_report(id)
  finding_key     text          -- LLM输出的稳定id如"F1"(供工单关联)
  seq             int
  -- 业务摘要层(给业务超管)
  biz_problem     text          -- 业务语言的问题描述
  impact          text          -- 影响面(频次/占比)
  priority        text          -- high | medium | low
  -- 技术详情层(给技术超管)
  phenomenon      text          -- 现象(期望vs实际)
  root_cause_hypothesis text    -- [推测]根因假设
  node_clues      text          -- 节点元信息线索
  evidence_run_ids text[]       -- 依据的 run_id 列表(展开查看)
  category        text          -- routing | skill | data | metric | entity | perf

review_report_suggestion
  id              bigserial PK
  report_id       bigint → review_report(id)
  suggestion_key  text          -- LLM输出的稳定id如"S1"
  finding_id      bigint → review_report_finding(id)  -- 关联到哪个 finding
  seq             int
  content_biz     text          -- 业务语言建议(给业务超管决策,无技术词)
  draft_changes   jsonb         -- 技术实现草稿(给技术超管,target/action/add_test_case)
  risk            text          -- 风险提示
  status          text          -- pending | accepted | rejected | hold
  reject_reason   text NULL     -- 驳回时填(也是对复盘归因质量的反馈)
  decided_by      text NULL
  decided_at      timestamptz NULL
  ticket_id       bigint NULL   -- 采纳后关联到 improvement_ticket
```

> 改进工单表 `improvement_ticket` 用现有结构（§前端规格 §3.6/3.7），采纳时把 suggestion 的 finding_key/suggestion_key 写入工单 source_finding_id/source_suggestion_id，ticket_id 回写 suggestion。

---

## 5. 归因 prompt（LLM，含目的/有用性硬约束/两层产出/护栏/few-shot）

```
你是 HR 超级智能体系统的【复盘分析员】。

【你的目的】
技术超管不可能逐条看几千条运行记录。你的职责是：从过去一周的运行元数据里，
找出【真正值得修的问题】，并把每个问题描述到【看的人能据此行动】的程度。
你做两件事：① 发现值得修的问题（不是罗列统计数字）；② 让问题可被行动。

【输入】
- 总览统计 {{aggregates}}：总数/各意图占比/👎率/超时率/RAG 0命中率/各 badcase 原因占比/与上周对比。（已由SQL聚合，纯统计）
- badcase 样本 {{badcase_samples}}：每条含 run_id / intent / outcome / badcase_reason / 节点路径 / 加载的skill / 调用的tool / chunks_hit / rows_returned / 反馈原因。**无 query 原文、无个人姓名、无薪资数值。**

【什么是"有用的复盘"——每条 finding 必须能回答这4个问题，否则不要输出】
1. 什么问题（现象）：不是"👎率6%"这种数字，而是"用户问X类问题时系统Y表现不对"。
2. 有多严重（影响面）：发生几次、占该类提问的比例、是高频还是个例。这决定值不值得现在修。
3. 为什么（根因假设）：基于 trace 模式推断的可能原因，**必须标[推测]**。
4. 从哪下手（行动线索）：具体到改哪个文件/skill/哪类case，不是"优化体验"这种空话。

【聚焦原则】
- 只输出 top 3-5 个【最值得修】的问题，按影响面（频次×严重度）排序。
- 不要罗列所有小问题；个例、偶发、影响面极小的不输出。
- 没有数据支撑的不写，宁可少说。

【对比历史存疑（生成本周 finding 后做）】
- 输入会附带【历史存疑 finding 列表】{{open_hold_findings}}（之前被业务超管标为"存疑"、仍未解决的）。
- 对本周每条 finding，语义比对历史存疑列表：若主题高度相似（同一类问题再次发生），在该 finding 加标记 `recurring_from`（关联的历史存疑 finding_key）+ 一句提醒文案"此问题上周已存疑，本周又发生N次，建议重新评估"。
- 只比对【存疑】的，不比对已驳回的。判定靠语义相似，不靠关键词匹配。

【两层产出——同一条 finding 输出两个模块，前端按角色分别展示】
说明：每条 finding 同时产出"业务摘要模块"和"技术详情模块"两个模块。前端按角色挑：
**业务超管只看模块A（完全看不到模块B的技术内容）；技术超管看模块B（技术详情）。** 两个模块描述的是同一个问题，但用两种语言各表达一次。

A. 业务摘要模块（给业务超管判断"值不值得修"）：
   - biz_problem：业务语言的问题描述。**硬约束：必须是非技术人员能看懂的人话，绝不出现任何技术术语**（不得出现 RAG/over_reject/0命中/Planner/node/run_id/检索/意图 等词）。
     - ❌ 错误："RAG 0命中集中在年终奖核算" / "over_reject 误伤成本查询"
     - ✅ 正确："员工问'年终奖怎么算'，系统答不上来" / "查各部门成本时被系统错误拒绝"
   - impact：影响面，业务语言（"本周15次，员工拿不到答案"）。
   - priority：high | medium | low（按影响面定）。
   - 自检：写完 biz_problem 问自己"一个完全不懂技术的 HR 总监能看懂吗"，看不懂就重写。
B. 技术详情模块（给技术超管"动手修"，可含技术细节）：
   - phenomenon：现象（具体什么提问、期望什么、实际什么）。
   - root_cause_hypothesis：[推测]根因假设。
   - evidence_run_ids：依据的 run_id 列表（可追溯）。
   - node_clues：从节点元信息看到的线索（如"Planner判成policy而非aggregate"）。
   - category：routing | skill | data | metric | entity | perf。

【改进建议（每条 finding 配1条，也输出两个模块，前端按角色展示）】
和 finding 一样，建议分业务版/技术版两个模块：
- content_biz：**业务语言**的建议——说"要解决什么业务问题、做了有什么好处"。**硬约束：不含技术词**（不得出现 ROUTER/aggregate/Planner/few-shot/§/文件名/检索 等）。
  - ❌ "ROUTER 给 aggregate 补成本类部门查询边界"
  - ✅ "让系统能正确回答'各部门成本'类问题（解决成本查询被误拒）"
  - 业务超管看这个 + 采纳/驳回/存疑按钮，据此决策"要不要做"。
- draft_changes：技术实现草稿（给技术超管执行）：{ target: 改哪个文件的哪节, action: 大概怎么改, add_test_case: 建议加什么测试用例 }
- risk：风险提示（如"注意别同时把真正的个人薪资放开"）
- 备注：这是建议草稿，最终改法由技术超管结合代码判断，且必须过测试门禁才上线。
- 展示：业务超管看 content_biz（业务语言，无技术细节）；技术超管看 draft_changes（技术实现）。采纳生成工单时，业务超管在工单追踪看 content_biz，技术超管在工作台看 draft_changes。

【护栏（不可违反）】
- [事实]（统计/标记）与[推测]（根因假设）必须分清，不得把推测写成事实。
- 不臆造：trace信息不足以归因时，root_cause_hypothesis 写"信息不足，建议补充XX trace字段"。
- 不输出 query 原文、个人姓名、薪资数值。复盘是看【系统健康度】，不是监控员工。
- 建议必须落到具体文件/skill/参数；空泛建议（"提升效果""优化性能"）视为无效，不要输出。
- 你只发现和建议，绝不自动改任何东西。

【输出 JSON（每个 finding/suggestion 带稳定 id，供采纳生成工单时关联）】
{
  "summary": {"total_runs":N, "thumb_down_rate":x, "key_takeaway":"一句话本周总结"},
  "findings": [
    {
      "id": "F1",
      "biz_problem": "...", "impact": "...", "priority": "high",
      "phenomenon": "...", "root_cause_hypothesis": "[推测]...",
      "evidence_run_ids": ["...","..."], "node_clues": "...",
      "category": "routing"
    }
  ],
  "suggestions": [
    {
      "id": "S1", "finding_id": "F1",
      "content_biz": "...(业务语言,给业务超管决策,无技术词)",
      "draft_changes": {"target":"...","action":"...","add_test_case":"..."},
      "risk": "..."
    }
  ]
}

【few-shot 示例】
输入(节选): aggregates 显示 over_reject 集中; badcase_samples 中 8 条 intent被判salary_sensitive但用户问的是部门成本, node_clues 显示 Planner 在薪资前置闸门拦截。
输出:
{
  "summary": {"total_runs":1240,"thumb_down_rate":0.062,"key_takeaway":"成本类查询被薪资拦截误伤是本周最值得修的问题"},
  "findings": [
    {
      "id":"F1",
      "biz_problem":"用户查询'各部门成本'时，常被系统当作敏感薪资问题拒绝回答",
      "impact":"本周发生8次，占成本类提问的67%，高频且阻断正常业务查询",
      "priority":"high",
      "phenomenon":"用户问'各部门成本汇总'，期望返回部门级聚合金额(允许)，实际被薪资前置闸门拦截reject",
      "root_cause_hypothesis":"[推测]薪资敏感判定把'部门成本聚合'误判为'个人薪资明细'，未区分'聚合金额'与'个人明细'，待人确认",
      "evidence_run_ids":["r-0521-001","r-0522-014","r-0523-076"],
      "node_clues":"Planner节点 decision 显示 payroll_sensitive=true，但这些应是 aggregate 放行",
      "category":"routing"
    }
  ],
  "suggestions": [
    {
      "id":"S1","finding_id":"F1",
      "content_biz":"让系统能正确回答'各部门成本/人力成本汇总'这类问题(解决成本查询被误当薪资拒绝)",
      "draft_changes":{"target":"ROUTER §3 出口2 / Planner薪资语义判定","action":"让LLM输出的payroll_scope/payroll_sensitive能区分聚合vs个人明细，部门级成本聚合判为aggregate放行","add_test_case":"router_cases.yaml/eval_set: 加'各部门成本汇总'→intent=aggregate,reject=false 及变体3条"},
      "risk":"调整时注意不要把真正的'部门每个人的薪资明细'(仍敏感)也一起放开——区分'聚合数'与'个人记录集合'"
    }
  ]
}
```

> 关键：finding 的 `id`(F1) 和 suggestion 的 `id`(S1)/`finding_id` 是稳定标识，落库后供"采纳生成工单"时写入工单的 source_finding_id/source_suggestion_id（见工单来源关联）。

---

## 6. 前端展示（已在《前端页面规格-权限重构》§3.5 定义）

技术超管/业务超管可见。展示三段（概览/归因/建议），每条建议三按钮（采纳生成工单/驳回/存疑）。本规格补充几条交互细节：

- **报告版本切换**：右上角下拉选周次（本周/上周/上上周…）。
- **归因展开依据**：点 finding 行的"依据 N 个 run ▾"可展开 run_id 列表（只展示元信息：intent/outcome/badcase_reason/时间，**无原文**）。
- **建议状态条**：每条建议旁显示当前 status（pending/accepted/rejected/hold），accepted 后显示关联工单号链接。
- **手动重跑**：管理员可点「立即重新生成本周报告」（仅技术超管可见，业务超管看到的是只读）。

---

## 7. Mock 周报数据（作品集演示用）

> 落库为示例数据，让前端复盘页第一眼能展示完整内容。后续真实跑批后被覆盖。

```yaml
review_report:
  id: 1
  week_start: 2026-05-19
  week_end: 2026-05-25
  status: ready
  total_runs: 1240
  thumb_down_rate: 0.062
  timeout_rate: 0.011
  rag_zero_rate: 0.08
  intent_dist: {aggregate: 0.32, policy: 0.21, attribution: 0.18, lookup: 0.12, trend: 0.07, compare: 0.05, list: 0.03, chitchat: 0.02}
  badcase_reason_dist: {rag_zero_hit: 0.42, clarify: 0.28, user_down: 0.20, timeout: 0.10}
  vs_last_week: {total_runs_delta: "+8%", thumb_down_delta: "-1.5pct", rag_zero_delta: "+2pct"}

review_report_finding:
  - finding_key: "F1"
    seq: 1
    biz_problem: "用户查询'各部门成本'时，常被系统当作敏感薪资问题错误拒绝"
    impact: "本周8次，占成本类提问的67%，高频且阻断正常业务查询"
    priority: high
    phenomenon: "用户问'各部门成本汇总'，期望返回部门级聚合金额(允许)，实际被薪资前置闸门拦截reject"
    root_cause_hypothesis: "[推测]薪资敏感判定把'部门成本聚合'误判为'个人薪资明细'，未区分聚合金额与个人明细，待人确认"
    node_clues: "Planner节点 decision 显示 payroll_sensitive=true，但这些应判为 aggregate 放行"
    evidence_run_ids: [r-2026-0520-211, r-2026-0523-076, ...]  # 8 个
    category: routing
  - finding_key: "F2"
    seq: 2
    biz_problem: "员工问'怎么补卡/考勤补卡'类制度，系统答不上来"
    impact: "本周12次全部未命中，集中在考勤补卡主题"
    priority: medium
    phenomenon: "用户问考勤补卡流程，RAG检索0命中，返回'未找到相关制度'"
    root_cause_hypothesis: "[推测]知识库缺《考勤补卡管理办法》文档，待人确认"
    node_clues: "document节点 decision.chunks_hit=0，检索无命中"
    evidence_run_ids: [r-2026-0521-001, r-2026-0521-088, r-2026-0522-014, ...]  # 12 个
    category: data
  - finding_key: "F3"
    seq: 3
    biz_problem: "查'李XX'相关问题时系统频繁反问'你指的是哪位'"
    impact: "本周5次澄清，集中在同名员工，影响查询效率"
    priority: low
    phenomenon: "用户问'李XX'，系统因同名无法确定具体是谁，触发澄清反问"
    root_cause_hypothesis: "[推测]实体词典缺同名员工的部门/工号区分信息，待人确认"
    node_clues: "Resolver节点 decision 显示 clarify=true, resolved=false"
    evidence_run_ids: [r-2026-0524-033, ...]  # 5 个
    category: entity

review_report_suggestion:
  - suggestion_key: "S1"
    finding_id: "F1"
    content: "在薪资敏感判定中明确区分'部门/事业部级聚合金额'(放行)与'个人薪资明细'(管控)"
    draft_changes:
      target: "路由总纲 ROUTER §3 出口2 / Planner 薪资语义判定"
      action: "让LLM输出的payroll_scope/payroll_sensitive能区分聚合vs个人明细，部门级成本聚合判为aggregate放行"
      add_test_case: "router_cases.yaml: '各部门成本汇总'→intent=aggregate,reject=false 及变体3条"
    risk: "注意不要把'部门每个人的薪资明细'(仍敏感)也一起放开——区分聚合数与个人记录集合"
    status: pending
  - suggestion_key: "S2"
    finding_id: "F2"
    content_biz: "把《考勤补卡管理办法》补进知识库,让员工问补卡流程时系统能答上来"
    draft_changes:
      target: "数据中台 / 管理制度 / 考勤"
      action: "上传新制度文档并触发重新分块入库"
      add_test_case: "eval_set.yaml: 加'员工怎么补卡'断言命中该文档"
    risk: "无"
    status: pending
  - suggestion_key: "S3"
    finding_id: "F3"
    content_biz: "让系统遇到同名员工时能更好区分,减少反复追问"
    draft_changes:
      target: "实体别名表 / Resolver few-shot"
      action: "添加重名映射，Resolver 澄清时显示候选人的部门/工号"
      add_test_case: "router_cases.yaml: 加同名员工澄清正向用例"
    risk: "无"
    status: pending
```

---

## 8. 实现要点（给 Cursor）

1. **Celery 周定时任务**：`tasks/review_agent.py`，每周一 02:00 触发；可手动触发同任务。
2. **数据拉取层**：纯 SQL 聚合，**不传任何 query 原文/个人字段给 LLM**，只传聚合元信息和 badcase 样本元数据。
3. **LLM 调用**：用 §5 的 prompt，注入聚合数据；解析 JSON 输出落库。失败时整任务标 failed,不写半成品报告。
4. **数据库迁移**：新建 review_report / review_report_finding / review_report_suggestion 三张表。
5. **接口**：
   - `GET /api/v1/agent/review/reports?week=` 列报告
   - `GET /api/v1/agent/review/reports/{id}` 报告详情(findings+suggestions)
   - `POST /api/v1/agent/review/reports/{id}/regenerate` 手动重跑（仅技术超管）
   - `POST /api/v1/agent/review/suggestions/{id}/accept` 采纳→生成工单
   - `POST /api/v1/agent/review/suggestions/{id}/reject` 驳回(填理由)
   - `POST /api/v1/agent/review/suggestions/{id}/hold` 存疑
   全部 RBAC，仅技术超管/业务超管可访问。
6. **mock 数据 seed**：第一次部署写入 §7 mock 周报，前端立刻可演示。
7. **观察期**：上线后先空跑两周（生成报告但不强求人审），技术主管校准归因质量，再开放采纳工单流程；避免初期 LLM 归因不准导致工单泛滥。

---

## 9. 验收标准

1. 周定时任务能跑、能手动重跑、幂等。
2. 报告含三段：概览（含统计图）/ 归因（事实+推测+依据run_id 可展开）/ 建议（含工单草稿）。
3. 抽查报告内容：**无 query 原文、无个人姓名、无薪资金额**。
4. 故意制造一类 badcase（如批量 0命中）→ 下次报告中能看到对应 finding 与建议。
5. 点采纳 → 工单生成，关联 finding/suggestion 显示在改进工单页。
6. 驳回/存疑 status 正确切换并留痕。
7. 普通员工访问任意复盘接口 → 403。

---

## 10. 与其他模块的关系

- 上游：消费 AgentHarness 的 trace 表 + 反馈采集的 agent_feedback。
- 下游：建议被采纳后写入改进工单表，进入 ⑤SOP 闭环（技术主管按 SOP 处理 → 必须过 ③Test 门禁才上线）。
- 横向：Eval（④）提供"改完后系统变好了没"的量化验证。
- 不动业务主链路：复盘 Agent 是离线分析任务，不参与用户问答 LangGraph 主流程。

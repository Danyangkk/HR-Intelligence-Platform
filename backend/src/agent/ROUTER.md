# 路由总纲 ROUTER

> 意图→流程→skill 的**唯一事实源**。Planner 运行时全文注入；改路由只改本文件，不动 Planner 代码与 system_prompt。

---

## §1 Query 端到端生命周期

```
接收 → 规划(Planner) → 解析(Resolver) → 取证(Retriever) → 分析(Analyst) → 质检(Critic) → 汇总(Composer) → 输出
```

| 阶段 | Agent | 职责 |
|------|-------|------|
| 接收 | API | 接收用户 question、history |
| 规划 | Planner | 意图判定、subtask DAG、指派 agent；**不取数不回答** |
| 解析 | Resolver | 人名/组织/时间/模糊指标 → 系统口径 |
| 取证 | Retriever | 结构化取数 或 文档 RAG |
| 分析 | Analyst | 趋势/对比/归因/预测 |
| 质检 | Critic | 证据充分性；不足则触发 replan |
| 汇总 | Composer | 组织最终答案、配图、溯源、薪资过滤 |
| 输出 | API | SSE/JSON 返回用户 |

### 提前出口（不经完整编排）

| 出口 | 触发 | 行为 |
|------|------|------|
| **chitchat** | 无实质 HR 诉求的寒暄 | Planner 短路 `reply`，plan=[]，不派 agent、不 RAG |
| **reject** | 个人薪资明细等安全红线 | Planner 输出 reject=true + reason，plan=[] |
| **clarify** | Resolver 关键实体解析失败/重名 | 暂停编排，向用户澄清 |

### replan 回路

Critic 判定证据不足且 `replan_count < 2` → 回到 Planner，携带 `critic_feedback` 补充/修正 subtask，**保留已完成步骤**。

---

## §2 红线（与 global_preamble 一致，Planner 必须遵守）

1. **policy 白名单**：仅「纯制度/流程询问且不查数据」可判 policy。数据类与闲聊**绝不**兜底 policy。
2. **组织 + 数量/比率诉求**：强制 **aggregate**（结构化），禁止 policy / lookup / RAG。
3. **查数表绝不是 policy**：需结构化表行/统计的，走 structured，不走 RAG。
4. **闲聊最先判**：问候/感谢/告别/问能力/其他非 HR 闲聊 → chitchat 短路，固定话术，不走编排不 RAG。
5. **个人薪资明细双层拦截**：Planner 拆解时 reject；Composer 生成时过滤。部门/事业部级聚合金额**放行**。
6. **检索 0 命中**：明确说「未找到相关数据/规定」，**绝不编造、润色编造**。
7. **未匹配**：无法归入 chitchat 或任一业务 intent，或 confidence < 0.45 → `intent=""`, plan=[]，**禁止** policy/aggregate 兜底。

---

## §3 意图判定（语义，不靠关键词枚举）

判定三维：

| 维度 | 取值 |
|------|------|
| **主体** | 组织(事业部/部门/全公司) / 个人(人名) / 制度文档 / 不明确 |
| **诉求** | 统计数值·比率·汇总 / 具体记录 / 制度规定·流程 / 随时间变化 / 原因(为什么) / 未来估算 / 横向比较 / 列名单 |
| **数据来源** | 结构化表 vs 文档(RAG) |

**语义映射原则**（示例，非关键词表）：

- 组织 + 统计数值/比率/汇总 → **aggregate**
- 组织 + 随时间变化 → **trend**
- 组织或个人 + 原因/偏高/偏低/风险 → **attribution**
- 组织 + 未来估算/缺口 → **forecast**
- 多组织/维度横向比较 → **compare**
- 个人 + 具体记录 → **lookup**
- 按条件列人员名单 → **list**
- 制度/流程说明且无数据诉求 → **policy**（须满足白名单）
- 无实质 HR 诉求寒暄 → **chitchat**

**强制纠偏**：组织名 + 多少人/规模/比率/离职率等 → 必 aggregate；人名 + 查数据 → lookup（薪资明细除外 → reject）。

### chitchat 话术（短路 reply）

| 子类 | 场景 | reply |
|------|------|-------|
| 问候/感谢 | 你好/在吗/谢谢 | 你好呀～我是 HR 的超级助手，今天有什么事情可以帮你呢？ |
| 告别 | 再见/拜拜 | 如果之后有任何需要都可以再次询问小助手哦～ |
| 问能力 | 你是谁/你能干嘛 | 你好呀～我是 HR 的超级助手，今天有什么事情可以帮你呢？我可以帮你查数据（考勤/薪酬/编制等）、解读制度政策、做统计对比与趋势分析，也能做离职、绩效等原因诊断。 |
| 其他闲聊 | 天气/笑话等与 HR 无关 | 我是专注 HR 领域的小助手～人力数据、制度政策、统计分析我都能帮上忙，有相关问题随时问我哦。 |

边界：「公司有问候礼仪规定吗」→ policy；「杭综多少人」→ aggregate。

---

## §4 意图 → 激活阶段 → skill 主表

`retrieve_mode`：policy 用 **rag**；其余业务 intent 用 **structured**（aggregate 绝不 RAG）。

| intent | 判定要点 | 激活阶段 (subtask types) | 流程型 skill（Analyst/Retriever 加载） | 常用 target_l3 |
|--------|----------|---------------------------|----------------------------------------|----------------|
| **chitchat** | 寒暄短路 | （无，plan=[]） | — | — |
| **policy** | 纯制度/流程，无数据诉求 | retrieve(rag) → compose | process-leave-policy（制度解读） | l3-1-1-1 员工手册 |
| **lookup** | 个人具体记录 | resolve → retrieve(structured) → compose | — | 花名册 l3-2-1-4；请假 l3-2-2-1；加班 l3-2-2-4；绩效 l3-5-1-1 |
| **list** | 条件列名单 | resolve → retrieve(structured) → compose | — | l3-2-1-4 花名册 |
| **aggregate** | 组织级统计/比率/人数 | resolve → retrieve(structured) → compose | — | l3-2-5-1 人事报表；l3-2-1-4；l3-6-1-1 编制 |
| **trend** | 指标随时间变化 | resolve → retrieve → analyze → critique → compose | trend-analysis | l3-2-5-1 多期 |
| **forecast** | 编制/缺口预测 | resolve → retrieve → analyze → compose | process-headcount-planning | l3-6-1-1 |
| **compare** | 跨组织/维度比较 | resolve → retrieve → analyze → critique → compose | compare-benchmark, process-headcount-planning | l3-4-6-3, l3-6-1-1 |
| **attribution** | 为什么/偏高/风险 | resolve → retrieve(多表) → analyze → critique → compose | process-resignation-attribution, process-performance-diagnosis, process-turnover-risk-alert, attribution-methodology | l3-2-5-1, l3-5-1-1, l3-2-2-4, l3-2-2-1, l3-2-3-1 等 |

### 各阶段默认 skill（执行 Agent 加载）

| subtask type | Agent | 通用 skill |
|--------------|-------|------------|
| resolve | Resolver | entity-resolution, metric-dictionary |
| retrieve(structured) | Retriever | structured-retrieval, pii-permission, metric-dictionary |
| retrieve(rag) | Retriever | document-rag, pii-permission |
| analyze | Analyst | 上表流程型 skill + compare-benchmark / trend-analysis / attribution-methodology |
| critique | Critic | evidence-validation |
| compose | Composer | answer-composition, data-visualization |

### 拆解规则

- type → agent：resolve→Resolver, retrieve→Retriever, analyze→Analyst, critique→Critic, compose→Composer
- 含人名/模糊时间/模糊指标 → **首步 resolve**
- attribution / trend / compare → 须 retrieve 后 analyze + critique
- 多跳取数放在**同一 retrieve** subtask 内
- **末步必 compose**
- 「为什么类」须 resolve→retrieve→analyze→compose，不可单点草率回答

---

## §5 Planner 输出 JSON

```json
{
  "intent": "chitchat|policy|lookup|list|aggregate|trend|forecast|compare|attribution",
  "confidence": 0.0,
  "reasoning": "一句话语义判定",
  "reject": false,
  "reason": "",
  "reply": "",
  "plan": [
    {
      "id": "ST1",
      "type": "resolve|retrieve|analyze|critique|compose",
      "goal": "",
      "target_l3": ["l3-xxx"],
      "assigned_agent": "Resolver|Retriever|Analyst|Critic|Composer",
      "retrieve_mode": "rag|structured"
    }
  ]
}
```

- chitchat：`reply` 必填，`plan=[]`
- reject：`reject=true`，`reason` 必填，`plan=[]`
- 未匹配：`intent=""`, `confidence` 低, `plan=[]`

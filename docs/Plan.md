# HR Agent — 开发计划

## 一、产品设计

业务 SSOT：`/Users/kk/Desktop/人力系统相关文档/Cursor后端实现总文档.md`

## 二、后端开发

### 基础设施（pycore 脚手架）✅

- [x] 用户验收通过：`pycore/` + `backend/src/` + ConfigManager + APIServer
- [x] 自动验证通过：Docker `/health`、`/api/v1/categories`

### P1 数据读 API ✅

- [x] GET /data/{l3_id}、filters、export
- [x] 前端列表对接

### P2 导入闭环 ✅

- [x] validate / preview / commit、edit、delete

### P2 文档 RAG ✅

- [x] 上传、分块、BM25（tsvector）
- [x] Qwen embedding + hybrid RRF + rerank（T-002）

### P3 飞书 sync ✅

- [x] POST /feishu/{l3_id}/sync（T-003，l3-2-2-1 请假记录 MVP）
- [x] Celery worker + 演示数据 upsert；多维表格扩展暂缓

### P4 指标口径字典 ✅

- [x] 附录 D 落库 `backend/resources/metrics_dictionary.json`（T-004）
- [x] `GET /agent/metrics`、`GET /agent/metrics/{name}`、`POST /agent/calc`
- [x] Skill 资源 `backend/src/agent/skills/metric-dictionary/SKILL.md`

### P5 LangGraph 智能体骨架 ✅

- [x] LangGraph：planner → resolver → retrieve/document → composer（T-005）
- [x] `POST /agent/ask`（JSON 响应，SSE 留 T-007）
- [x] `POST /agent/query/structured`
- [x] policy / lookup 单跳跑通；薪资敏感拒答

### P6 智能体全量 ✅

- [x] compare / attribution 意图 + Analyst + Critic + replan（T-006）
- [x] 并行多表取数、guardrail 脱敏、chart_spec 输出
- [x] 多轮 history 实体继承（planner）

### P7 SSE + 前端对接 ✅

- [x] `POST /agent/ask` SSE 流式（`stream: true`）+ JSON 兼容
- [x] 前端超级智能体对接真实 API，替换脚本化 demo

### P8 RBAC / 审计 / 可观测 ✅

- [x] RBAC 角色权限 + `pii_check` 列级脱敏（T-008）
- [x] 写操作 / 登录 / 智能体问答记 `audit_log`
- [x] `agent_run_log` 记录 plan/trace/tools/耗时/replan
- [x] `GET /agent/runs`、`GET /agent/audit/logs`（hr_admin）
- [x] 前端 JWT 登录条（管理员/只读）

### P9 架构补全（设计文档对齐）✅

- [x] **Skill 运行时**：`skills/runner.py` — **全部 Agent**（Planner/Resolver/Retriever/Analyst/Critic/Composer）读 SKILL.md 按 SOP 执行，trace 含 `skill`/`sop`/`tools`（T-009）
- [x] **Tool 层**：8 tools registry；Analyst `calc`、Composer `chart_render` 经 `call_tool`/`invoke_tool`，不直连 service（T-010）
- [x] **Supervisor Send 扇出**：多表 retrieve → `Send(retrieve_worker)` → `retrieve_collect` → supervisor（T-011）
- [x] **飞书 11 表**：`table_configs` + `GET /feishu/config/status` + `POST /feishu/sync-all`；`FEISHU_BITABLE_*_TABLE_ID` 占位 + demo_fallback（T-012）
- [x] **验收**：pytest 全绿 + SDD T-009~T-013 标记完成（T-013）

### P10 规范级 Agent 智能化 ✅

- [x] **T-014 Resolver 重名 clarify**：`EmployeeLookupResult` + 重名 options，不再取首条模糊匹配
- [x] **T-015 query_structured 聚合**：`aggregation.py`（sum/avg/count/max/min + group_by）
- [x] **T-016 离职风险预警**：`process-turnover-risk-alert` SKILL + `analyst_rules` 加权识别
- [x] **T-017 飞书 beat + webhook**：`beat_schedule.py` 定时 sync + `POST /feishu/webhook`
- [x] **T-018 Agent LLM 框架**：`llm_runner.py`（`agent_llm_enabled` / `llm_json` / JSON 解析）
- [x] **T-019 Resolver LLM**：lookup 员工解析 + DB 重名校验；compare/attribution 走规则避免误 clarify
- [x] **T-020 Retriever prefetch**：structured retrieve 前 `get_template` + `feishu_status`
- [x] **T-021 Analyst LLM**：JSON 分析 + rules 兜底；compare 合并 bar chart_spec
- [x] **T-022 Critic LLM**：pass/replan/pass_with_limit + rules 兜底
- [x] **T-023 Composer rag_answer**：policy 分支 `rag_answer_draft` → compose → polish（Retriever 仅检索）
- [x] **验收**：`pytest tests/ -q` **58 passed**（2026-05-26）

### P11 多轮澄清闭环 ✅

- [x] **T-024 structured clarify**：`clarify_helpers.py`（重名 employee + 泛化 lookup scope）
- [x] **T-024 API**：`entities` 入参；`answer`/`clarify` SSE 回传 `entities` + structured `options`
- [x] **T-024 前端**：clarify 可点选；`history` 携带 `clarify` + `entities` 闭环
- [x] **T-024 种子**：花名册增加重名「王伟」用于演示

### P12 Hybrid Resolver + Analyst 指标口径 ✅

- [x] **T-025 Hybrid Resolver**：LLM 草稿 + `finalize_resolver_entities`（DB/字典校验；clarify 仅代码生成）
- [x] **T-025 metric_resolver**：模糊短语 → `metrics_dictionary.json`（`benchmark`/`threshold`/`citation`）
- [x] **T-025 resolver_lookup**：员工查重/clarify payload 独立模块，打破循环 import
- [x] **T-025 Analyst**：compare/attribution 读取 `entities.metric`，口径 citation 与 Resolver 一致
- [x] **验收**：`pytest tests/ -q` **70+ passed**（含 `test_analyst_metric` / `test_resolver_hybrid`）

### P13 8 意图 plan 补全 ✅ (T-026)

- [x] **list**：花名册清单（组织范围 + P级筛选）→ resolve → retrieve(l3-2-1-4) → compose
- [x] **aggregate**：group_by + sum 聚合（如各事业部请假总天数）
- [x] **trend**：多期 l3-2-5-1 → Analyst 趋势线 → Critic → Composer
- [x] **forecast**：l3-6-1-1 编制缺口估算 → Analyst → Composer
- [x] **Planner LLM**：8 意图 validate + rules 兜底
- [x] **Send worker**：携带 plan/plan_index/entities 避免取数丢上下文

### P14 规范级收尾 (T-027～T-030)

- [x] **T-027 Mock upsert**：`patch_mock_records` 补全缺失字段（如 l3-2-5-1 事业部）；seed 自动 patch
- [x] **T-028 附录 D 验收**：30 项指标字典全覆盖 + benchmark/threshold/citation 字段支持
- [x] **T-029 Retriever LLM 层**：`retriever_llm.py` 空结果放宽 filters（规则 + LLM）；supervisor 自动重试
- [ ] **T-030 飞书生产配置**：`.env.example` 11 表模板 + config/status 验收（**真实 table_id 待填入**）

## 三、前端开发

- [x] 单页 index.html 对接 P0–P2 API

## 四、质量门禁

```bash
python3.11 -m ruff check backend/src
python3.11 -m pytest backend/tests   # 待补充
```

## 五、功能详情

### T-002 文档 RAG

**测试指令**

```bash
curl http://localhost:8080/health
# 上传制度后
curl -X POST "http://localhost:8080/api/v1/docs/l3-1-1-1/search?q=请假"
```

**验收**：命中现行制度片段；无结果时 hits=[]。

## 六、Agent 取证柔性化改造（2026-06）

设计决策记录（详见 `docs/REFACTOR_PLAN_agent_flexibility.md`）：

- **意图降级为治理标签**：intent 仍用于观测聚类与 Eval Layer1，但不再锁死 subtask 模板；Planner 自由输出 DAG，由不变式校验兜底。
- **不变式清单（I1–I7）**：合法 subtask 类型、compose 唯一收尾、analyze⇒retrieve+critique、target_l3 目录白名单、RAG/结构化互斥、≤10 步。
- **L3 目录驱动**：84 项 `categories.json` description + `catalog.py` 注入 Planner，新增表无需改 few-shot。
- **混合取证**：分析类问题可追加 RAG 路；Retriever 遍历多文档库；Composer 按 evidence 含 documents 触发制度草稿。
- **降级路径保持死板**：`planner_rules.build_plan` 结构稳定，硬编码 l3 ID 纳入目录白名单测试。
- **回归基线**：宿主机 `cd backend && PYTHONPATH=.. pytest tests -m "not online" -q`；对比 `backend/tests/.baseline-failures.txt` 不得新增失败。

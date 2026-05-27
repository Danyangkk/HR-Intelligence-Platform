---
name: structured-retrieval
display_name: 结构化取数
description: 从飞书表/导入表取明细或聚合；先确认模版字段再按标准值筛选；支持内部多跳与 Send 并行扇出；最小权限。
type: general
when_to_use: 需要从结构化数据表取明细或统计值时。
tools: [get_template, query_structured, feishu_status]
uses_skills: []
guardrails: [结构化禁用RAG, 最小权限, 个人薪资明细不取]
---

# 结构化取数 (G2)

Retriever 从数据中台精确查询业务表。

## SOP

1. get_template 确认字段/唯一键
2. 读 plan 中 target_l3，用 entities 标准值构造 filters
3. 多表时 LangGraph Send 扇出并行取数
4. 飞书表可先 feishu_status 看时效
5. 结果附 l3_id + 唯一键，经 pii-permission 脱敏后供下游引用

## Few-shot

输入: "杭抖部门11月加班总时长"
→ query_structured(l3-2-2-4, {事业部:杭抖部门, 加班日期:2025-11}, agg) → structured evidence + agg

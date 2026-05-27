---
name: process-onboarding
display_name: 入职办理
description: 新员工入职流程指引：制度要求、所需材料、系统操作步骤与时间节点。
type: process
when_to_use: "新员工入职怎么办/入职需要哪些材料/入职流程"。
tools: [search_documents, query_structured]
uses_skills: [document-rag, entity-resolution]
guardrails: [只引现行制度, 查不到不臆造, 不涉及个人薪资明细]
---

# 入职办理 (P3 扩展)

## 模块

员工手册(`l3-1-1-1` RAG)、花名册(`l3-2-1-4`)

## SOP

1. 文档检索：入职相关制度条文（only_current）
2. 若有具体员工：实体解析确认工号与部门
3. 组织分步骤指引（材料、审批、系统录入），附制度出处

## Few-shot

输入: "新员工张三入职需要办什么"
→ 解析张三工号 + RAG 检索入职章节 → 分步骤清单 + 出处

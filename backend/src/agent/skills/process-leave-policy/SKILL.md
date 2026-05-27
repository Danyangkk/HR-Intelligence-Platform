---
name: process-leave-policy
display_name: 制度合规解读
description: 制度问答，仅引现行版本，给条文出处，查不到说查不到。
type: process
when_to_use: "年假/补偿/试用期/报销/请假流程等怎么规定"。
tools: [search_documents]
uses_skills: [document-rag, metric-dictionary]
guardrails: [只引现行版本, 给条文出处, 查不到不臆造]
---

# 制度合规解读 (P4 流程)

## SOP

1. 文档检索与解读（仅现行制度，only_current=true）
2. 涉及计算（如年假折算）时查指标口径字典
3. 每个结论附《文档名》+段落出处

## Few-shot

输入: "年假怎么规定"
→ 引《员工手册2025现行版》4.2 节作答 + 出处

输入: "宠物陪护假"
→ "未在现行制度中找到相关规定"

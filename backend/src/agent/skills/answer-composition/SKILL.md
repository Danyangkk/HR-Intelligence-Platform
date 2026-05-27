---
name: answer-composition
display_name: 答案组织与引用
description: 结论先行的图文组织+溯源标注(数据:模块+定位键;文档:文档+段落)+口径+局限声明。
type: general
when_to_use: Composer 产出最终答案时。
tools: []
uses_skills: [data-visualization, pii-permission]
guardrails: [不臆造, 个人薪资明细字段跳过]
---

# 答案组织与引用 (G10)

## SOP

1. 先一句话结论，再分点论证
2. 数据结论标模块+记录定位键；文档结论标文档名+段落(seq/title_path)
3. 指标标口径（取自 Analyst.metrics_used）
4. 数据缺失或 Critic 超限放行时声明局限

## Few-shot

输入: Analyst 绩效归因输出
输出: 结论先行 + 分点论证 + 口径说明 + citations 含 data/doc 定位

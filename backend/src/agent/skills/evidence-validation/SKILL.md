---
name: evidence-validation
display_name: 证据校验
description: 质检证据覆盖性/一致性/归因质量/口径/安全，决定 pass/replan/pass_with_limit。
type: general
when_to_use: Critic 质检时（aggregator 之后、composer 之前）。
tools: []
uses_skills: []
guardrails: [replan 限 2 次, 个人薪资明细要求剔除而非补数]
---

# 证据校验 (G11)

Critic 判断 evidence 是否足以作答。

## SOP

1. 检查覆盖性（计划全部方面、关键模块是否取到）
2. 检查一致性（证据矛盾、数字与结论一致）
3. 检查归因质量（是否有基准、是否相关当因果）
4. 检查口径（指标是否标准口径）
5. 检查安全（个人薪资明细→要求剔除）；决策 pass / replan / pass_with_limit

## Few-shot

输入: intent=attribution, 缺同岗对比基准, replan_count=0
输出: decision=replan, gaps=["缺少同部门同岗位绩效均值作为对比基准"]

输入: 已补齐基准, replan_count=1
输出: decision=pass

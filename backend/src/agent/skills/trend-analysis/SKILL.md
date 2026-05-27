---
name: trend-analysis
display_name: 趋势分析
description: 构造时间序列(≥3点)，算环比/同比/方向并指出拐点。
type: general
when_to_use: 趋势类问题或归因需要时间走势时。
tools: [calc]
uses_skills: [metric-dictionary]
guardrails: [≥3点才有趋势意义]
---

# 趋势分析 (G6)

## SOP

1. 构造时间序列（≥3 个时间点）
2. calc 算环比/同比/方向
3. 描述趋势与拐点

## Few-shot

输入: 离职率 6-11 月 [9,11,13,15,16,18]
输出: series=[{label:离职率%, points:[…]}], 结论="半年持续上升，累计+9pct，无明显拐点"

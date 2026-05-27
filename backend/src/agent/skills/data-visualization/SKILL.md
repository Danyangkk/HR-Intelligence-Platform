---
name: data-visualization
display_name: 数据可视化
description: 判断是否该出图并生成图表规格——趋势≥3点折线/构成占比饼·堆叠/对比≥2组分组柱状/排名条形；单值不画；数据来自证据。
type: general
when_to_use: Composer 组织答案、数据复杂到文字说不清时。
tools: [chart_render]
uses_skills: []
guardrails: [仅四类触发, 数据来自证据不自造]
---

# 数据可视化 (G8)

## SOP

1. 按规则判断图型（趋势≥3点/构成占比/对比≥2组/排名）
2. 用 Analyst 的 series/factors 作为数据源
3. 调 chart_render 生成 chart_spec

## Few-shot

输入: series=绩效得分 3 点 → chart_render(line)
输入: factors=5 项贡献度 → chart_render(factor_bar)
输入: 单值"2天" → 不出图

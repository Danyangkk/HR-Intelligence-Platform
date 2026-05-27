---
name: compare-benchmark
display_name: 对比与基准
description: 个体 vs 群体或本期 vs 上期的对比，统一口径计算偏离度/分位/差值；事业部用枚举精确区分。
type: general
when_to_use: 对比类问题或归因需要基准时。
tools: [query_structured, calc]
uses_skills: [metric-dictionary]
guardrails: [两侧口径一致, 事业部枚举精确区分]
---

# 对比与基准 (G5)

## SOP

1. 定对比对象与基准（同岗均值/公司均值/上期）
2. 取两侧数据按统一口径计算
3. 输出偏离度/分位/差值

## Few-shot

输入: 杭抖 vs 杭综人均成本
输出: series=[{label:人均成本, points:[{x:杭抖部门,y:2.31},{x:杭综部门,y:1.98}]}], 结论="杭抖高于杭综0.33万/人/月"

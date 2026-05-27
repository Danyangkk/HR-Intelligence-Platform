---
name: attribution-methodology
display_name: 归因分析方法论
description: "为什么X"类分析的通法：明确指标与基准→列因子→各因子取证→算贡献度排序→区分相关/因果。被各业务归因 skill 复用。
type: general
when_to_use: 任何 attribution 分析，由流程型 skill 间接调用。
tools: [calc]
uses_skills: [compare-benchmark, structured-retrieval]
guardrails: [必须有基准, 不把相关当因果, 不以偏概全]
---

# 归因分析方法论 (G4)

## SOP

1. 明确被解释指标与对比基准
2. 列候选因子（由业务 skill 给清单）
3. 各因子分别取证
4. calc 估贡献度并排序
5. 标证据强度与局限，区分相关/因果

## Few-shot

输入: 指标=离职率18%(基准:公司均值11%), 因子证据=[加班高,薪酬偏低,绩效平稳]
输出: factors=[{name:加班强度,contribution:0.41},{name:薪酬竞争力,contribution:0.28},…], caveat="加班与离职相关性强"

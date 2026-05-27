---
name: process-resignation-attribution
display_name: 离职归因
description: 诊断某部门/事业部离职率高或上升的原因，输出因子贡献度与改进建议。
type: process
when_to_use: "为什么X离职率高/上升"类问题。
tools: [query_structured, calc]
uses_skills: [trend-analysis, compare-benchmark, attribution-methodology, metric-dictionary]
guardrails: [薪酬仅部门聚合, 区分相关/因果]
---

# 离职归因 (P1)

## 因子

加班强度、薪酬竞争力(部门带宽)、绩效趋势、近期异动、面谈情绪

## 模块

异动记录、加班/请假、事业部人力成本拆分(部门级)、绩效结果、面谈记录、复盘报告(RAG)

## SOP

1. 趋势分析：离职率走势（口径=期间离职/期间平均在职）
2. 对比与基准：本部门 vs 公司均值；本期 vs 上期
3. 归因分析方法论：列因子→取证→贡献度排序

## Few-shot

输入: 杭抖近 6 月离职率上升
输出: factors=[加班0.41,薪酬0.28,绩效0.16,…] + 离职率趋势 series + "主因加班强度偏高与薪酬竞争力偏低"

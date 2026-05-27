---
name: process-performance-diagnosis
display_name: 个人绩效诊断
description: 诊断某员工绩效差/下滑的原因，对比同岗均值并给因子贡献与建议。
type: process
when_to_use: "某人为什么绩效差/下滑"或"某人最近表现怎么样"。
tools: [query_structured, calc]
uses_skills: [compare-benchmark, trend-analysis, attribution-methodology, metric-dictionary]
guardrails: ["绩效差"判定取口径字典, 不引入个人薪资明细]
---

# 个人绩效诊断 (P2)

## 因子

业绩达成、出勤投入、培训参与、近期异动、面谈反映问题

## 模块

考核结果/绩效数据分析(`l3-5-1-1`)、对应业绩数据、加班/请假、培训台账、异动、述职/面谈

## SOP

1. 对比与基准：个人 vs 同部门同岗位均值
2. 趋势分析：近 2 考核周期得分走势
3. 归因分析方法论：因子贡献度排序

## Few-shot

输入: 张三近 2 期绩效 82→65，业绩达成率低于均值，11 月事假 2 天
输出: findings=[绩效下滑,业绩为主因,出勤异常] + factors=[业绩0.44,出勤0.22,…] + series(绩效趋势)

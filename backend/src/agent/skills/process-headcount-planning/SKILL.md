---
name: process-headcount-planning
display_name: 编制健康度盘点
description: 盘点编制 vs 实有、超缺编、达成率并按阈值预警。
type: process
when_to_use: "编制是否健康/哪些部门超缺编/达成率"或 compare 类编制对比。
tools: [query_structured, calc]
uses_skills: [metric-dictionary, compare-benchmark]
guardrails: [缺编/超编实时算不入库]
---

# 编制健康度盘点 (P4/P6)

## 指标

编制 vs 实有、缺编/超编、编制达成率(=实有/编制)

## 模块

杭抖/杭综/中后台编制数据(`l3-6-1-1`)

## SOP

1. 指标口径字典：编制达成率
2. 对比与基准：部门间对比
3. 阈值预警（<90% 缺编，>110% 超编）

## Few-shot

输入: 全部门编制盘点
输出: 达成率排名 + "运营组缺编12%需补招，财务超编5%"

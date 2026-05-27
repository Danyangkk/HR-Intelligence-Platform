---
name: process-compensation-review
display_name: 人力成本拆解
description: 拆解人力成本变动/结构原因，全程部门级聚合，不涉个人明细。
type: process
when_to_use: "为什么成本涨了/成本结构如何"。
tools: [query_structured, calc]
uses_skills: [trend-analysis, attribution-methodology, metric-dictionary]
guardrails: [全程部门/事业部聚合, 严禁个人薪资明细]
---

# 人力成本拆解 (P5)

## 因子

人数变动、薪资结构、奖金、社保福利

## 模块

集团人力成本汇总、事业部人力成本拆分(`l3-4-6-3`)、人力成本变动分析

## SOP

1. 趋势分析：成本环比/同比
2. 归因分析方法论：拆各成本项贡献

## Few-shot

输入: 杭抖 Q3 环比 +8%
输出: factors=[人数+0.5,奖金+0.3,社保+0.2] + "主因季度奖金发放与扩招"

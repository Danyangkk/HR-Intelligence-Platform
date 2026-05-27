---
name: process-turnover-risk-alert
display_name: 离职风险预警
description: 基于画像加权打分识别高离职风险员工并给主因，结论标注为风险提示非确定。
type: process
when_to_use: "哪些员工有离职风险/谁可能要走"。
tools: [query_structured, calc]
uses_skills: [attribution-methodology, trend-analysis]
guardrails: [结论标"风险提示非确定", 不涉个人薪资明细]
---

# 离职风险预警 (P5)

## 风险因子(加权)

出勤异常↑、绩效下滑、长期无晋升、加班畸高/畸低、近期负向面谈

## 模块

考勤、绩效(`l3-5-1-1`)、异动(`l3-2-3-1`)、加班(`l3-2-2-4`)

## SOP

1. 结构化取数：绩效、加班、异动
2. 归因方法论反向作风险加权 + 异常识别
3. 输出风险名单 + 各自主因，声明「风险提示非确定」

## Few-shot

输入: 杭抖运营组谁有离职风险
输出: [{工号,风险高,主因:绩效连降+加班畸高},…] + "建议优先面谈前3名（风险提示非确定）"

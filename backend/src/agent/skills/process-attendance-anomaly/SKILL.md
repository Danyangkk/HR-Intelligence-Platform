---
name: process-attendance-anomaly
display_name: 考勤异常核查
description: 交叉核对打卡/请假/加班识别缺卡、超时加班、请假与打卡冲突、出勤率异常。
type: process
when_to_use: "考勤是否有异常/谁缺卡/谁超时加班"。
tools: [query_structured, calc]
uses_skills: [structured-retrieval, compare-benchmark]
guardrails: [飞书表只读]
---

# 考勤异常核查 (P7)

## 检查项

缺卡、超时加班、请假与打卡冲突、出勤率异常

## 模块

门禁打卡、飞书打卡、请假(`l3-2-2-1`)、加班(`l3-2-2-4`)（均飞书同步表）

## SOP

1. 结构化取数：交叉核对打卡/请假/加班
2. 对比与基准：个体 vs 部门均值/阈值
3. 输出异常清单

## Few-shot

输入: 杭抖 11 月
输出: [{工号,异常:连续3日缺卡},{工号,异常:月加班超80h}] + 汇总异常人次

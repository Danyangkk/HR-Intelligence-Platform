---
name: entity-resolution
display_name: 实体解析
description: 把人名/组织/时间/模糊指标解析为系统口径（工号、事业部三枚举、标准时间、可量化指标+基准）；重名或失败则澄清。
type: general
when_to_use: 问题含人名、部门/事业部、模糊时间或模糊指标，需要落到系统口径时。
tools: [query_structured]
uses_skills: [metric-dictionary]
guardrails: [关键实体失败/重名→澄清不猜, 事业部只能落三枚举]
---

# 实体解析 (G1)

Resolver 专用：从自然语言问题中解析员工/组织/时间范围。

## SOP

1. 抽取实体候选（员工、组织、时间、模糊指标）
2. 人名 → query_structured 查花名册/任职取唯一工号+维度，多人则澄清
3. 组织 → 事业部三枚举（杭综部门/杭抖部门/职能部门）+ 部门
4. 时间 → 标准范围或周期串（YYYY-MM / YYYYQn / YYYY年度）
5. 模糊指标 → 查指标口径字典取定义/基准/阈值

## Few-shot

输入: "张三这个月请了几天假"（花名册命中唯一 A0123）
输出: entities={employee:{工号:A0123,姓名:张三,事业部:杭抖部门}, time_range:{from:2025-11-01,to:2025-11-30}}

输入: "看看王伟的绩效"（花名册命中 2 个王伟）
输出: clarify={question:"有两位『王伟』，您指哪位？", options:["王伟 A0210 · 杭综部门","王伟 A0455 · 职能部门"]}

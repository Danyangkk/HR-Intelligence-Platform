---
name: metric-dictionary
display_name: 指标口径字典
description: 系统统一的"指标→标准口径(分子/分母)"知识，保证全系统口径一致；算指标前必查，口径随结论输出。
type: general
when_to_use: 任何涉及指标计算或模糊指标解析的环节。
tools: [calc]
uses_skills: []
guardrails: [字典没有的指标先确认定义再算, 本字典是唯一口径来源]
---

# 指标口径字典 (G7)

Analyst / Resolver 计算 HR 指标前，必须先查本 Skill 对应的标准口径。

## 资源

- 机器可读字典：`backend/resources/metrics_dictionary.json`
- API：`GET /agent/metrics`、`GET /agent/metrics/{name}`、`POST /agent/calc`

## SOP

1. 按指标名取标准口径（分子/分母）
2. 从中台取数得到输入值后，用 calc 按口径计算
3. 口径随结论输出，禁止自行编造

## 口径摘选

- 离职率 = 期间离职人数 / 期间平均在职人数
- 出勤率 = 实际出勤 / 应出勤
- 人均人力成本 = 部门成本合计 / 在职人数
- 编制达成率 = 实有 / 编制
- 绩效"差" = 显著低于同岗均值（默认 < 均值×0.85 或 < 1 个标准差）

## Few-shot

输入: "算杭抖离职率"
→ 口径=期间离职/期间平均在职 → 结论附"(口径:期间离职/期间平均在职)"

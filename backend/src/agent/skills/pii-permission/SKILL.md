---
name: pii-permission
display_name: 脱敏与权限
description: 按角色与字段敏感度对取数结果脱敏/拦截；个人薪资明细任何环节不得输出；薪酬仅部门级聚合。
type: general
when_to_use: 任何取数与生成环节(横切)。
tools: [pii_check]
uses_skills: []
guardrails: [个人薪资明细红线, 越权拒绝并记审计]
---

# 脱敏与权限 (G9)

## SOP

1. pii_check 判定每字段允许/脱敏/拒绝
2. 薪资金额/身份证/银行账号脱敏
3. 个人薪资明细剔除
4. 薪酬只以部门/事业部聚合出现

## Few-shot

输入: role=hr_specialist 取薪资表个人字段
→ pii_check → {实发合计:deny} → 剔除该字段，仅返回部门聚合

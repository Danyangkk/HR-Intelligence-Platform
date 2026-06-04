---
name: pii-permission
display_name: 脱敏与权限
description: 个人薪资明细仅业务超管在 30 分钟确认 TTL 内可见，全程审计；技术超管/普通员工任何环节不得输出；无确认态下薪酬仅部门级聚合。
type: general
when_to_use: 任何取数与生成环节(横切)。
tools: [pii_check]
uses_skills: []
guardrails: [薪资 TTL 确认态校验, 越权拒绝并记审计]
---

# 脱敏与权限 (G9)

## SOP

1. pii_check 判定角色+确认态：业务超管且 payroll_confirmed_until > now → 允许个人薪资字段
2. 技术超管/普通员工 → 薪资金额/身份证/银行账号 一律 deny
3. 无确认态（超时或未确认）→ 薪酬仅部门/事业部聚合
4. 所有薪资访问写入审计表（访问人/对象/字段/时间/事由）

## Few-shot

输入: role=biz_super_admin, payroll_confirmed=true, 取薪资表个人字段
→ pii_check → {实发合计:allow} → 返回明细（审计记录已写入）

输入: role=tech_super_admin, 取薪资表个人字段
→ pii_check → {实发合计:deny} → 剔除，仅返回部门聚合

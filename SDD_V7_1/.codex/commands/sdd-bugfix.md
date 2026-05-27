# sdd-bugfix — Codex Adapter

用途：在 Codex 中执行 SDD Bugfix 流程。

执行时读取并严格遵守：

```text
harness-core/router.md
harness-core/skills/sdd-bugfix/SKILL.md
```

输出写入当前活动项目：

```text
Projects_Repo/<active_project_id>/.sdd/bug_fix/
Projects_Repo/<active_project_id>/.sdd/experience.md
```

约束：

- 如果 Bug 涉及产品口径，先执行 `sdd-align`
- 修复报告不得泄露真实 Key / Token / Secret
- 不得随意修改 `.sdd/tasks.json` 状态，除非用户明确要求


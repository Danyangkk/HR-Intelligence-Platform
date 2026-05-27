# sdd-start — Codex Adapter

用途：在 Codex 中启动 Planner → Developer → Tester 多智能体开发循环。

执行时读取并严格遵守：

```text
harness-core/router.md
harness-core/protocols/development-rules.md
harness-core/protocols/codex-subagents.md
harness-core/commands/sdd-start.md
```

Codex 可用自定义 subagent 时：

- 调度 `.codex/agents/planner.toml`
- 调度 `.codex/agents/developer.toml`
- 调度 `.codex/agents/tester.toml`

Codex 不支持自定义 subagent 时：

- 在主会话按 `harness-core/protocols/codex-subagents.md` 严格模拟角色边界
- Orchestrator 不直接读代码、不直接写代码、不跳过 Tester

门禁：

- Planner 产出 `.sdd/tasks.json` 后必须交给用户确认
- 每个功能闭环 Developer + Tester 后必须触发用户门禁
- 全局安装、`sudo`、系统设置、真实密钥、付费资源、长期服务必须先问用户


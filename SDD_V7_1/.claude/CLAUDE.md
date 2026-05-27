# SDD Harness V7_2 — Claude Code Entry

你是 SDD Harness V7_2 在 Claude Code 环境下的入口。

核心规则只允许维护在 `harness-core/`。`.claude/` 目录只做 Claude Code 适配。

## 启动顺序

处理任何项目管理、产品设计、功能升级、Bugfix、开发任务前，先读取：

1. `harness-core/router.md`
2. `harness-core/protocols/development-rules.md`

## Agents

Claude Code agent 适配器位于：

```text
.claude/agents/planner.md
.claude/agents/developer.md
.claude/agents/tester.md
```

这些文件只引用：

```text
harness-core/agents/*.md
```

不要在 `.claude/agents/` 里维护核心规则。

## Commands

Claude Code command 适配器位于：

```text
.claude/commands/sdd-start.md
.claude/commands/sdd-bugfix.md
.claude/commands/sdd-align.md
.claude/commands/sdd-new-project.md
```

这些文件只引用 `harness-core/commands/*.md`。

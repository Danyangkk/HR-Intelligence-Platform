# SDD Harness V7 — Codex Entry

你是 SDD Harness V7 在 Codex 环境下的入口。

本项目支持 Codex / Claude Code / Cursor 三端使用。核心规则只允许维护在 `harness-core/`，平台目录只做适配。

## 启动顺序

处理任何项目管理、产品设计、功能升级、Bugfix、开发任务前，先读取：

1. `harness-core/router.md`
2. `harness-core/protocols/development-rules.md`
3. 如需多智能体开发，读取 `harness-core/protocols/codex-subagents.md`

## Codex Commands

Codex 命令适配位于：

```text
.codex/commands/sdd-new-project.md
.codex/commands/sdd-align.md
.codex/commands/sdd-start.md
.codex/commands/sdd-bugfix.md
```

它们只负责把 Codex 路由到 `harness-core/commands/`、`harness-core/skills/` 和 `harness-core/protocols/`，不得维护核心流程。

## Codex Subagents

Codex subagent 配置位于：

```text
.codex/agents/planner.toml
.codex/agents/developer.toml
.codex/agents/tester.toml
```

当用户说“开始开发 / 进入开发阶段 / 执行 sdd-start / 继续多智能体开发”时，视为明确授权 Codex 使用 subagents：

- `planner`
- `developer`
- `tester`

按 `harness-core/commands/sdd-start.md` 和 `harness-core/protocols/codex-subagents.md` 推进。若当前 Codex 环境不支持自定义 subagent TOML，在主会话中模拟 Planner / Developer / Tester，但必须保持角色边界。

## 路径原则

业务文件只能写入当前活动项目：

```text
Projects_Repo/<active_project_id>/
```

不得把业务 `docs/`、`.sdd/`、`frontend/`、`backend/` 写到 Harness 根目录。

## 核心规则位置

- Router：`harness-core/router.md`
- 开发全局规则：`harness-core/protocols/development-rules.md`
- Codex 子智能体协议：`harness-core/protocols/codex-subagents.md`
- 开发循环：`harness-core/commands/sdd-start.md`
- Planner：`harness-core/agents/planner.md`
- Developer：`harness-core/agents/developer.md`
- Tester：`harness-core/agents/tester.md`
- 产品设计：`harness-core/skills/sdd-product-design/SKILL.md`
- Bugfix：`harness-core/skills/sdd-bugfix/SKILL.md`
- 场景对齐：`harness-core/skills/alignment/SKILL.md`

## 禁止

- 不要维护 `.codex/agents/*.toml` 里的核心流程，只能写入口适配。
- 不要维护 `.codex/commands/*.md` 里的核心流程，只能写命令适配。
- 不要复制 `.cursor/` 或 `.claude/` 的规则当作核心规则。
- 不要把项目内依赖安装交给用户手动执行。


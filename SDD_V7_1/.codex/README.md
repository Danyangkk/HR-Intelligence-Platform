# SDD V7 Codex Adapter

本目录是 Codex 适配层，只做入口和 subagent 配置，不维护核心规则。

## 入口

- 根入口：`AGENTS.md`
- Codex 配置：`.codex/config.toml`
- 子智能体：`.codex/agents/*.toml`
- Codex 命令提示：`.codex/commands/*.md`

## 使用方式

在 Codex 中打开 Harness 根目录后：

1. 先读取 `AGENTS.md`
2. 再按需读取 `.codex/commands/<command>.md`
3. 命令文件只会指向 `harness-core/` 的真正规则

## 子智能体

当前提供三个薄适配器：

- `planner` → `harness-core/agents/planner.md`
- `developer` → `harness-core/agents/developer.md`
- `tester` → `harness-core/agents/tester.md`

如果当前 Codex 环境不支持自定义 subagent TOML，按 `harness-core/protocols/codex-subagents.md` 在主会话中模拟三角色边界。


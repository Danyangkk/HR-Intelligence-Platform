# Codex Subagents Protocol

本协议定义 SDD V7 在 Codex 中使用 Planner / Developer / Tester 的方式。

## 目标

Codex 适配必须保持三件事：

1. 核心规则只在 `harness-core/` 维护
2. Codex 目录只做薄适配
3. 即使当前 Codex 环境不支持自定义 subagent，也必须维持角色边界

## 子智能体配置

Codex 子智能体配置位于：

```text
.codex/agents/planner.toml
.codex/agents/developer.toml
.codex/agents/tester.toml
```

这些文件只允许声明：

- `name`
- `description`
- `sandbox_mode`
- 指向 `harness-core/agents/*.md` 的 `developer_instructions`

不得在 TOML 中复制 Planner / Developer / Tester 核心规则。

## 编排器职责

Orchestrator 负责：

- 读取 `project-registry.json`
- 确定 `active_project_path`
- 读取 `.sdd/tasks.json` 的任务状态
- 调度 Planner / Developer / Tester
- 汇总 PASS / FAIL / BLOCKED
- 维护用户门禁

Orchestrator 禁止：

- 直接读业务代码细节
- 直接写功能代码
- 跳过 Tester
- 把业务文件写入 Harness 根目录

## 降级模式

如果 Codex 当前环境不能直接调用 `.codex/agents/*.toml`：

1. 主会话先声明当前模拟角色
2. 每个角色开始前读取对应 `harness-core/agents/*.md`
3. 每个角色只做自身职责
4. 角色切换时清楚说明输入和输出文件

降级模式仍必须遵守：

- Developer 一次只做一个任务
- Developer 不修改 `.sdd/tasks.json` 状态
- Tester 独立验证，不信任 Developer 声明
- Tester 只更新 status / notes，并写测试报告与 BUG 日志
- 真实 Key / Token / Secret 只能进入 `.env` 等配置文件

## Codex 命令适配

Codex 命令提示位于：

```text
.codex/commands/
```

命令文件只做路由提示，必须指向：

```text
harness-core/commands/
harness-core/skills/
harness-core/protocols/
```

不得在 `.codex/commands/` 复制核心流程。


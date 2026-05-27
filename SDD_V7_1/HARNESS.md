# SDD V7_2 Harness 使用规范

## 核心概念

SDD V7_2 分成两个层级：

```text
Harness 本体：开发规范、Agent、Skill、Command、Rules、模板、系统经验
项目实例：具体业务代码、设计文档、项目状态、项目经验
```

Harness 本体不直接承载业务代码。业务代码必须写入：

```text
Projects_Repo/<project-id>/
```

---

## 项目加载方式

SDD V7_2 只管理 `Projects_Repo/` 下的项目。

项目来源有两种：

1. 新建项目：在 `Projects_Repo/<project-id>/` 创建
2. 克隆项目：在 `Projects_Repo/` 下执行 `git clone`

不直接管理任意外部路径。外部已有项目需要先迁入或 clone 到 `Projects_Repo/`。

---

## Harness 与项目的关系

每个项目只获得轻量项目入口和运行状态，不复制平台适配层。核心 Harness 位于 SDD V7_2 根目录：

```text
harness-core/
.codex/
.cursor/
.claude/
```

项目内不得出现 `.codex/`、`.cursor/`、`.claude/` 规则副本，避免规则漂移。

---

## 经验系统

### 系统经验

路径：

```text
memory/harness-experience.md
```

作用：记录跨项目可复用、能反哺 Harness 的经验。

### 项目经验

路径：

```text
Projects_Repo/<project-id>/.sdd/experience.md
```

作用：记录当前项目内长期有效的经验。

### 任务经验

来源：

- Developer 完成任务后的记录
- Tester 报告
- Bugfix 报告

任务经验可以提升为项目经验；项目经验可以提升为系统经验，但必须经过门禁和用户确认。

---

## 不允许的做法

- 不要直接在 SDD V7_2 根目录开发业务代码
- 不要把项目代码写进 Harness master
- 不要把项目级经验无脑写入系统经验
- 不要让移动端项目读取 Web 前端 rules
- 不要跳过项目选择直接进入开发

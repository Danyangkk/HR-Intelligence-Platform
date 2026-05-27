# SDD V7_2 — 项目管理型 AI Coding Harness

> Spec-Driven Development V7_2：从“项目内开发规范包”升级为“多项目管理 Harness”，并支持 Codex / Claude Code / Cursor 三端入口。

---

## V7_2 的定位

SDD V7_2 不再默认“当前文件夹就是项目”。它是一个 **项目管理系统**：

1. 先管理项目仓库 `Projects_Repo/`
2. 再选择新建项目 / 克隆项目 / 继续已有项目 / 功能升级 / Bugfix
3. 然后进入单个项目工作区
4. 最后执行产品设计、多 Agent 开发、测试、修复和经验沉淀

一句话：

> V5 是开发规范包，V7_2 是项目管理型、多平台 Agent Harness。

核心原则：

- `harness-core/` 是唯一真相源
- `.codex/`、`.claude/`、`.cursor/` 只做平台适配
- `Projects_Repo/<project-id>/` 只放业务项目状态和代码，不再复制整套平台规则

---

## 目录结构

```text
SDD_V7_2/
├── AGENTS.md                        # Codex 自动入口
├── START.md                         # 非 Cursor 兜底 / 教学说明
├── HARNESS.md                       # Harness 使用规范
├── project-registry.json            # 项目注册表
│
├── harness-core/                    # 唯一真相源：agents / commands / skills / dev-standards / protocols
│   ├── router.md
│   ├── agents/
│   ├── commands/
│   ├── skills/
│   ├── dev-standards/
│   └── protocols/
│
├── .codex/                          # Codex 适配层：subagents TOML + commands + config
│   ├── config.toml
│   └── agents/
│
├── .claude/                         # Claude Code 适配层
│   ├── CLAUDE.md
│   ├── agents/
│   └── commands/
│
├── Projects_Repo/                   # 默认项目仓库，所有项目放这里
│   └── <project-id>/
│
├── .cursor/                         # Cursor 适配层，所有文件只引用 harness-core
│   ├── agents/
│   ├── commands/
│   ├── skills/
│   ├── dev-standards/
│   └── rules/
│
├── templates/
│   ├── project/                     # 新项目初始化模板
│   ├── tasks.json
│   ├── experience.md
│   └── work-log.md
│
├── memory/
│   └── harness-experience.md        # 系统级经验
│
└── pycore/                          # Python 后端框架底座
```

---

## 项目工作区结构

每个项目都在 `Projects_Repo/<project-id>/` 下：

```text
Projects_Repo/<project-id>/
├── AGENTS.md                        # 项目级轻入口，提示返回 Harness 根目录
├── .sdd/                            # 项目状态脑子
│   ├── project.json                 # 项目元信息
│   ├── status.json                  # 当前阶段状态
│   ├── tasks.json                   # 任务状态机
│   ├── experience.md                # 项目级经验
│   ├── work-log.md                  # 工作日志
│   ├── bug_fix/                     # Bugfix 报告
│   └── test-reports/                # Tester 报告
│
├── docs/
│   ├── PRD.md
│   ├── api-contracts.md
│   ├── Plan.md
│   └── prototypes/
│
├── frontend/ / mobile/
├── backend/
└── ...
```

---

## 工作流总览

```text
Cursor 自动注入 Harness Router
  │
  ├─ 读取 project-registry.json
  │
  ├─ 选择操作
  │   ├─ 新建项目
  │   ├─ 从 GitHub 克隆项目
  │   ├─ 继续已有项目
  │   ├─ 已有项目功能升级
  │   └─ Bugfix
  │
  ├─ 进入 Projects_Repo/<project-id>/
  │
  ├─ 判断项目形态
  │   ├─ Web：可走 alignment + sdd-product-design 全流程
  │   └─ 移动端：警告缺少移动端规范，用户确认后继续，可选业务场景对齐
  │
  ├─ 判断项目状态
  │   ├─ 缺 PRD / API / Plan → 产品设计或要求用户补齐
  │   └─ 文件齐全 → 多 Agent 开发
  │
  └─ Planner → Developer → Tester → Bugfix / Experience
```


## Codex 使用方式

在 Codex 中打开 Harness 根目录后，先读取：

```text
AGENTS.md
.codex/README.md
```

常用 Codex 命令适配：

```text
.codex/commands/sdd-new-project.md
.codex/commands/sdd-align.md
.codex/commands/sdd-start.md
.codex/commands/sdd-bugfix.md
```

Codex 子智能体配置：

```text
.codex/agents/planner.toml
.codex/agents/developer.toml
.codex/agents/tester.toml
```

如果当前 Codex 环境不支持自定义 subagent TOML，按 `harness-core/protocols/codex-subagents.md` 在主会话中模拟 Planner / Developer / Tester 的角色边界。

---

## 核心变化

### 1. 所有项目统一放进 `Projects_Repo/`

无论是新建项目，还是从 GitHub 拉下来的项目，都放在：

```text
Projects_Repo/<project-id>/
```

V7_2 不管理任意外部路径，降低教学和使用复杂度。

### 2. `.sdd/` 替代 `.output/` 成为长期项目状态目录

V5 的 `.output/` 更像临时产物目录。V7_2 里：

- `docs/` 存设计文档
- `.sdd/` 存任务、状态、经验、日志、报告

### 3. 三级经验系统

```text
任务经验 → 项目经验 → 系统经验
```

- 任务经验：具体任务/bug 的局部经验
- 项目经验：当前项目长期有效的经验，写入 `.sdd/experience.md`
- 系统经验：跨项目可复用的 Harness 规则，写入 `memory/harness-experience.md`

经验可以上升，但必须带证据和用户确认。

### 4. 场景对齐层

`alignment` 是 V7_2 的业务口径对齐层，位于 PRD、技术合同、Planner 和 Bugfix 之前。

它负责把用户的大段想法、功能升级描述或产品口径型 Bug 整理成：

```text
docs/澄清文档/<feature-name>/01-alignment.md
```

它只写业务目标、范围、场景、验收口径和关键问题，不写技术方案、接口字段、组件拆分或开发任务。

### 5. Web / 移动端分流

- Web 项目：可以走产品设计 Skill，自动产出 PRD / 原型 / API 契约 / Plan
- 移动端项目：当前缺少移动端产品设计和开发 rules，必须警告并等待用户确认；用户需自行提供 PRD / 原型 / API 契约 / Plan

---

## 一句话架构

```text
SDD V7_2 Harness
  → Project Registry
    → Projects_Repo/<project-id>
      → Alignment
        → docs + .sdd
          → Product Design / Multi-Agent Development / Bugfix
            → Experience Promotion
              → Harness Evolution
```

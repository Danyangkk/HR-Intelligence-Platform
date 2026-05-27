
description: SDD V7_2 Harness Router。任一支持平台打开规范包后进入项目管理模式；任何产品设计、功能改动、Bugfix、开发任务前都必须先确定 active_project_path。

# SDD V7_2 Harness Router

你现在处在 SDD V7_2 Harness 工作区。Codex / Claude / Cursor 打开的目录可以是 Harness 根目录，但业务项目文件不得直接写在 Harness 根目录。

## 运行身份

默认身份是 Harness Router。

Harness Router 负责：

1. 读取 `project-registry.json`
2. 确定当前活动项目 `active_project_id`
3. 解析 `active_project_path = Projects_Repo/<active_project_id>/`
4. 判断用户要新建项目、克隆项目、继续项目、产品设计、功能升级、Bugfix 或进入开发
5. 自动调用 `scripts/sdd_project.py` 和对应 Command / Skill
6. 保证所有业务文件写入当前活动项目目录
**7. 执行指令之前，与用户对齐全局系统可使用的python指令（不默认用户系统使用python 或者python3 激活正确版本的python系统）**
只有当 `docs/PRD.md`、`docs/api-contracts.md`、`***.pen`、`docs/Plan.md` 齐全，与用户对齐了python指令与虚拟环境名称、用户明确开始开发时，才进入智能体开发模式，由 Harness Router调度 Planner / Developer / Tester。

## Active Project Path 强制规则

任何产品设计、场景对齐、功能改动、Bugfix、代码开发、测试报告写入之前，必须先确定：

```text
active_project_path = Projects_Repo/<active_project_id>/
```

如果 `project-registry.json` 没有 `active_project_id`，必须先让用户选择、创建或克隆项目，不得继续写业务文件。

如果当前项目目录不存在：

```text
<active_project_path>/.sdd/project.json
```

说明项目未初始化，不得继续产品设计、开发或 Bugfix。

## 路径解析规则

所有项目相对路径都必须基于 `active_project_path` 解析：

```text
docs/PRD.md                  => <active_project_path>/docs/PRD.md
docs/api-contracts.md        => <active_project_path>/docs/api-contracts.md
docs/Plan.md                 => <active_project_path>/docs/Plan.md
docs/prototypes/             => <active_project_path>/docs/prototypes/
docs/澄清文档/               => <active_project_path>/docs/澄清文档/
.sdd/tasks.json              => <active_project_path>/.sdd/tasks.json
.sdd/tmp/ui-design-spec.md   => <active_project_path>/.sdd/tmp/ui-design-spec.md
.sdd/experience.md           => <active_project_path>/.sdd/experience.md
.sdd/test-reports/           => <active_project_path>/.sdd/test-reports/
.sdd/bug_fix/                => <active_project_path>/.sdd/bug_fix/
frontend/                    => <active_project_path>/frontend/
backend/                     => <active_project_path>/backend/
mobile/                      => <active_project_path>/mobile/
```

禁止把业务文件写入当前 Harness 系统根目录，只能写在对应仓库项目（Projects_Repo）路径下。

如果发现这些目录已在 Harness 根目录出现，先提示这是误写入产物，并建议迁移到当前活动项目路径；不得继续在根目录推进业务流程。

## 项目选择规则

`scripts/sdd_project.py` 是 Harness Router 的内部工具，默认由 Agent 调用，不要求用户自己运行。

- 用户要新建项目：Agent 代为运行 `python scripts/sdd_project.py new <id> --name "<name>" --type web|mobile|unknown`
- 用户要切换项目：Agent 代为运行 `python scripts/sdd_project.py use <id>`
- 用户问当前项目：Agent 代为运行 `python scripts/sdd_project.py current`
- 用户要列项目：Agent 代为运行 `python scripts/sdd_project.py list`

为用户执行完创建项目的指令后，反问用户对需求的清晰程度，决定是否进入`alignment` skills。
参考反问模版：请问您是否对自己将要开发的项目有比较清晰的全流程把握？如果是，请你提供已有的流程解析，如果不是，我们将一起进入对齐阶段。

新建项目或切换项目后，必须向用户明确当前活动项目：

```text
active_project_id = <id>
active_project_path = Projects_Repo/<id>/
```

## Web / Mobile 门禁

Web 项目可以进入`sdd-product-design`。

移动端项目不得触发 Web 端 `sdd-product-design`，必须先警告：当前系统缺少移动端产品设计规范和移动端开发 rules。用户明确确认继续后，才可在用户自备 PRD / 原型 / API 契约 / Plan 的前提下进入多智能体开发。

## 文件写入前检查

每次准备写入文件前，先自检：

1. 是否已确定 `active_project_id`
2. 写入路径是否位于 `Projects_Repo/<active_project_id>/`
3. 是否误把 `docs/` 或 `.sdd/` 写到 Harness 根目录

任何一项不满足，先停止并修正路径。

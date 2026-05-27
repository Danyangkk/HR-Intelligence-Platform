# sdd-align — Codex Adapter

用途：在 Codex 中执行业务场景对齐。

执行时读取并严格遵守：

```text
harness-core/router.md
harness-core/skills/alignment/SKILL.md
```

输出默认写入当前活动项目：

```text
Projects_Repo/<active_project_id>/docs/澄清文档/<feature-name>/01-alignment.md
```

约束：

- 只对齐业务目标、范围、场景、验收口径和关键问题
- 不写技术方案、接口字段、组件拆分、数据库设计或开发任务
- 未确定 `active_project_path` 前不得写业务文件


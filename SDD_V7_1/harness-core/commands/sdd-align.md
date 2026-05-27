# /sdd-align

用途：调用 SDD V7_2 的业务场景对齐 Skill，在 PRD、技术合同、Planner 或 Bugfix 之前先统一产品口径。

适用：

- 新项目只有大段想法，尚未进入产品设计
- 已有项目功能升级前，需要明确业务边界
- Bugfix 涉及按钮、权限、可见性、历史数据、保存/下载/生成规则等产品语义
- 移动端项目需要先整理业务场景，但仍需用户自行提供移动端 PRD / 原型 / API 契约 / Plan

执行步骤：

1. 读取 `harness-core/skills/alignment/SKILL.md`
2. 确认当前已存在 `active_project_path` 和 `.sdd/project.json`；如不存在，返回 Router 先创建或选择项目，不得在 alignment 中自动初始化项目
3. 进入当前项目目录，按 Skill 要求读取 `.sdd/`、`docs/` 和相关代码事实
4. 输出业务 PRD 对齐稿
5. 如用户要求保存，写入：

```text
docs/澄清文档/<feature-name>/01-alignment.md
```

禁止：

- 不要直接写技术方案
- 不要拆开发任务
- 不要改代码
- 不要替代 `sdd-product-design`、Planner 或 `sdd-bugfix`

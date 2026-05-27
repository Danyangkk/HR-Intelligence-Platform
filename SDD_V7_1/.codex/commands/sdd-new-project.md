# sdd-new-project — Codex Adapter

用途：在 Codex 中创建新的 SDD 项目。

执行时读取并严格遵守：

```text
harness-core/router.md
harness-core/commands/sdd-new-project.md
```

推荐优先使用脚本：

```bash
python3 scripts/sdd_project.py new <project-id> --name "<项目名称>" --type web
```

约束：

- 项目只能创建在 `Projects_Repo/<project-id>/`
- 平台适配层 `.codex/`、`.cursor/`、`.claude/` 不复制进项目
- 真实 Key / Token / Secret 只能写入 `.env` 等配置文件


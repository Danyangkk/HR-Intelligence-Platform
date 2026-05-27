# /sdd-new-project - 新建 SDD V7_2 项目

## 使用方式

```text
/sdd-new-project <project-id> <项目名称> <web|mobile|unknown>
```

## 执行流程

1. 在 `Projects_Repo/<project-id>/` 创建项目目录
2. 初始化项目目录并写入项目级入口，不复制平台适配层
3. 初始化 `.sdd/`：
   - `.sdd/project.json`
   - `.sdd/status.json`
   - `.sdd/experience.md`
   - `.sdd/work-log.md`
   - `.sdd/test-reports/`
   - `.sdd/bug_fix/`
4. 创建 `docs/`
5. **初始化 Git 仓库**（读取 `harness-core/skills/git-workflow/SKILL.md`）：
   - `git init -b main`
   - 生成 `.gitignore`（基于项目类型：Node / Python / 通用）
   - 配置 Git 用户名/邮箱（如缺失则提示用户）
   - 初始提交：`git add .gitignore` + `git commit -m "chore: init repository"`
6. 更新 `project-registry.json`
7. 提醒用户推荐打开 Harness 根目录，而不是直接打开项目目录：

```text
Projects_Repo/<project-id>/
```

## 可选脚本

可使用标准库脚本初始化：

```bash
python scripts/sdd_project.py new <project-id> --name "<项目名称>" --type web
```

# 回滚指南 · 权限重构前快照

**重要：** 若需回到权限重构前的干净版本，使用以下任一方式。

## Git 标签（推荐）

```bash
git checkout pre-permission-refactor
```

或只查看/对比：

```bash
git diff pre-permission-refactor..HEAD
git log pre-permission-refactor..HEAD --oneline
```

## 快照信息

| 项 | 值 |
|---|---|
| 标签 | `pre-permission-refactor` |
| Commit | `7ede303` |
| 说明 | 权限模型重构 + 改进闭环 UI 实施前的 baseline |
| 日期 | 2026-05-27 |

## 回滚后

回滚后需重启 Docker 服务：

```bash
docker compose restart api nginx
docker compose exec api alembic upgrade head   # 若 DB 已跑新 migration，需自行 downgrade
```

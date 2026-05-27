# HR Agent 工作日志

## 2026-05-26 — 脚手架对齐 SDD V7_1

- 复制 `SDD_V7_1/pycore/` → 项目根 `pycore/`
- `backend/app/` → `backend/src/`，导入统一为 `src.*`
- 接入 `ConfigManager` + `DotEnvConfigLoader`（`backend/.env` / 根 `.env`）
- 接入 `APIServer`（`src/main.py`）
- Docker：`PYTHONPATH=/app`，挂载 `pycore/` + `backend/.env.docker`
- Harness：`.sdd/tasks.json`、`docs/Plan.md`

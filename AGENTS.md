# HR Agent — SDD 项目入口

本项目使用 **SDD V7_1 Harness** 驱动开发。核心规则位于 `SDD_V7_1/harness-core/`，业务 SSOT 位于 `docs/` 与 `/Users/kk/Desktop/人力系统相关文档/`。

## 快速路由

| 场景 | 读取 |
|------|------|
| 开发循环 | `SDD_V7_1/harness-core/commands/sdd-start.md` |
| 后端规范 | `SDD_V7_1/harness-core/dev-standards/backend-dev.md` |
| 任务清单 | `.sdd/tasks.json` |
| 进度 | `.sdd/status.json` |
| 计划 | `docs/Plan.md` |

## 后端启动（本地）

```bash
cd backend
PYTHONPATH=.. python3.11 -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

## Docker

```bash
docker compose up --build
```

配置：`backend/.env.docker`（Compose 挂载为容器内 `backend/.env`）；本地开发可读项目根 `.env`。

## 框架

- `pycore/` — PyCore 框架（PYTHONPATH 引入，不 pip 安装）
- `backend/src/` — 业务代码（`src.*` 包）

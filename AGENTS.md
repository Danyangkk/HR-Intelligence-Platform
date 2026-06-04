# HR Agent — 项目入口

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

## 结构

- `pycore/` — PyCore 框架（PYTHONPATH 引入，不 pip 安装）
- `backend/src/` — 业务代码（`src.*` 包）
- `frontend/` — 纯 HTML/JS 前端
- `docs/` — 设计文档（含本改造方案 REFACTOR_PLAN_agent_flexibility.md）

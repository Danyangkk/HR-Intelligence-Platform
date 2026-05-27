# HR Agent — 人力数据中台 + 超级智能体

## P0 快速启动

```bash
# 1. 环境变量
cp .env.example .env
# 编辑 .env 填入密钥（P0 可不填 DashScope / 飞书）

# 2. 一键启动
docker compose up --build
```

访问：

| 服务 | 地址 |
|------|------|
| 前端 + API 网关 | http://localhost:8080 |
| API 直连 | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| MinIO 控制台 | http://localhost:9001 (minioadmin/minioadmin) |

## 验收（P0）

```bash
curl http://localhost:8080/health
curl http://localhost:8080/api/v1/categories | head
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"hr_admin","password":"admin123"}'
```

## 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| hr_admin | admin123 | hr_admin |
| viewer | viewer123 | viewer |
| agent | agent123 | agent |

## 目录结构

```
HR-Agent/
  pycore/            # PyCore 框架（PYTHONPATH 引入）
  backend/src/       # FastAPI 业务代码
  frontend/          # 单页前端
  SDD_V7_1/          # Harness 规则与工具（harness-core/）
  .sdd/              # 项目状态与 tasks.json
  docs/Plan.md       # 开发计划
  docker-compose.yml
```

## 本地后端（非 Docker）

```bash
cd backend
PYTHONPATH=.. python3.11 -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

配置：项目根 `.env` 或 `backend/.env`（ConfigManager 读取，不用进程环境变量）。

Docker 使用 `backend/.env.docker`（Compose 挂载为容器内 `backend/.env`）。

## 实现路线

- **P0** ✅ 脚手架 + seed（84 个 l3 分类 + 61 套模版 + 11 条 feishu_sync）
- **P1** 数据中台读 API + mock 业务数据
- **P2** 导入闭环 + 文档 RAG
- **P3** 飞书真实 sync + webhook
- **P4+** LangGraph 智能体 + SSE

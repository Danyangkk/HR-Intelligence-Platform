人力超级智能体 · 运行日志查阅说明
================================

所有问答的运行记录（意图、节点耗时、重试、结果）都会自动写入：

  backend/logs/agent-run.log

（Docker 部署时路径相同，因 backend 目录已挂载到本机。）

怎么查看？
---------

1) 用文本编辑器直接打开 agent-run.log（推荐小白）

2) 实时跟踪最新日志（终端）：

   tail -f backend/logs/agent-run.log

   Docker 环境：

   docker compose logs -f api
   # 或
   tail -f backend/logs/agent-run.log

3) 只看最近 50 行：

   tail -n 50 backend/logs/agent-run.log

日志里有什么？
-------------

- ▶ 新问答开始：run_id、session、角色、问题指纹（hash，不是原文）
- ✓ / ↻ / ✗ / ⏱ 每个节点：planner、retriever、analyst 等，耗时、重试次数
- ■ 问答结束：成功/拒答/超时/澄清，总耗时、replan 次数

不会写入什么？
-------------

- 用户问题的原文
- 薪资金额、身份证、文档正文、数据行内容

数据库 trace（可选高级查询）
---------------------------

同一次运行也会写入 PostgreSQL 表 agent_run / agent_node_trace，
供 SQL 或 API 查询；日常排查看本文件即可。

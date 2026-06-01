from __future__ import annotations

NODE_TIMEOUT_S = 30.0
MAX_RETRY = 2
RETRY_BACKOFF_S = (1.0, 2.0)
# 整个 agent flow 的总超时。归因/对比类查询涉及多次 LLM 调用 + 并行 retrieve_worker
# + replan 兜底，90s 经常不够。调到 180s 给复杂查询足够时间。
FLOW_TIMEOUT_S = 180.0
FLOW_TIMEOUT_MESSAGE = "处理超时，请稍后重试或缩小问题范围"

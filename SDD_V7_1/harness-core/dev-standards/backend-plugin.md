

# PyCore Plugin 层规范

> **仅用于 AI Agent 应用。** 普通业务系统不需要 Plugin 层。

## 架构选择

| 应用类型 | 调用链 |
|---------|--------|
| 普通业务系统 | Router → Service → Repository |
| AI Agent 应用 | Router → PluginRegistry → Plugin → Service |

## BasePlugin 速查

```python
from pycore.plugins import BasePlugin, PluginResult
from pycore.core import get_logger

logger = get_logger()  # 模块级！BasePlugin 没有内置 logger

class SearchPlugin(BasePlugin):
    name: str = "search_knowledge"
    description: str = "Search the knowledge base"
    parameters: dict = { ... }  # OpenAI function calling JSON Schema

    async def execute(self, query: str, limit: int = 5, **kwargs) -> PluginResult:
        # **kwargs 是必须的！
        try:
            results = await self._do_search(query, limit)
            return self.success({"query": query, "results": results})
        except Exception as e:
            return self.fail(f"Search error: {e}")
```

## PluginResult 速查

```python
result = PluginResult.ok(data)      # 成功
result = PluginResult.fail("msg")   # 失败

if not result:          # 用 __bool__ 判断
    msg = result.error  # 失败用 .error
else:
    data = result.data  # 成功用 .data
```

## PluginRegistry 速查

```python
registry = PluginRegistry()
registry.register(SearchPlugin())
result = await registry.execute("search_knowledge", query="Python")
specs = registry.to_specs()  # OpenAI function calling 格式
```

## 易错点

| 错误写法 | 正确写法 |
|---------|---------|
| `if not result.success:` | `if not result:` |
| `result.output`（取错误时）| `result.error` |
| `self.failure("msg")` | `self.fail("msg")` |
| `async def execute(self, x):` | `async def execute(self, x, **kwargs):` |
| `len(registry._plugins)` | `len(registry)` |

## 外部服务调用规则（强制）

### 百炼平台禁止直接使用官方 SDK

调用阿里云百炼（LLM/Embedding/Reranker）时，**禁止使用 `dashscope` 等官方 SDK**。必须使用 `httpx` / `aiohttp` 直接发送 HTTP 请求，手动构造请求体、解析响应 JSON。

**原因：**
- SDK 封装层隐藏真实响应结构，易导致假设错误（如 T-008 中 `response.output.usage` vs 实际 `response.usage`）
- 直接 HTTP 调用结构透明、可控、Mock 简单
- 测试无需依赖 SDK 安装和版本兼容性

**正确做法示例：**
```python
import httpx

async def call_llm(prompt: str) -> str:
    async with httpx.AsyncClient(trust_env=False, timeout=30.0) as client:
        response = await client.post(
            f"{base_url}/compatible-mode/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]}
        )
        data = response.json()
        # 直接操作 dict，结构透明
        return data["choices"][0]["message"]["content"]
```

**错误做法：**
```python
# 禁止使用 SDK
import dashscope
response = dashscope.Generation.call(...)
```

### 写解析逻辑前必须先真实调用

封装第三方 API 时，必须先写探索代码真实调用并打印响应，确认结构后再写解析逻辑：
```python
# 探索阶段
response = await client.post(url, json=payload, headers=headers)
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
# 确认结构后，再写正式解析代码
```

### 禁止继承环境变量

外部服务 HTTP 客户端永远不得继承本机环境变量。所有 `httpx.Client` / `httpx.AsyncClient` 必须显式设置 `trust_env=False`，避免本机代理、证书、系统环境变量污染百炼/OpenAI/第三方 API 调用。禁止使用裸 `httpx.get()` / `httpx.post()` 快捷调用。

## 深入阅读

- 完整 Plugin 规范（参数 Schema、生命周期、组合模式）：`pycore/docs/specs/plugins.md`

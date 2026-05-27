

# 后端开发总规则

本文件由 `description` 触发选用（非路径 globs）。根据当前开发阶段，执行对应章节的规则。

- **依赖安装**：项目虚拟环境内的 `pip install` / `uv sync` / `pip install -r requirements.txt` 可由 Agent 自动执行；全局安装、`sudo`、系统 Python 修改、涉及密钥或付费资源的命令必须先向用户确认。
- **测试**：后端单元测试、lint、typecheck、短时启动检查、curl 验证可由 Agent 自动执行；需要人工业务验收的部分才交给用户操作。

**后端专项约束（硬性禁止，不得例外）**

- **Python 指令自动探测优先**：首次进入后端开发时，优先自动探测 `python3.11` / `python3` / `python` 的版本；若能确认 Python 3.11+，直接使用该指令。无法确认时才询问用户。
- **虚拟环境创建规则**：项目内虚拟环境可由 Agent 自动创建，默认名称 `.venv`；如果用户或项目已有指定名称，遵守已有约定。不得修改系统 Python 或全局环境。
- **pycore 通过 PYTHONPATH 引入，不通过 pip 安装**：`pycore/` 与 `backend/` 并列存放在项目根目录下，后端启动时**必须在命令中加上 `PYTHONPATH=..`**（从 `backend/` 目录启动时）。所有 `from pycore.xxx import ...` 的代码依赖此设置才能正常运行。完整说明与示例见本文件「PyCore 核心配置」章节。
- **严禁读取、依赖或继承进程环境变量**：后端代码**禁止**通过 `os.environ`、`os.getenv`、`environ` 等方式直接读取业务配置；所有配置（API Key、数据库 URL、端口、LLM 地址等）**必须通过后端配置文件**（如 `backend/.env` + PyCore `ConfigManager` / `BaseSettings`）获取。`ConfigManager.load()` 不得使用进程环境覆盖文件配置，即使显式传入 `use_env=True` 也必须失败。测试开关只能控制“是否运行测试”，不能作为业务配置来源。HTTP 客户端（`httpx`、`openai` 等）初始化时必须显式禁用环境继承，`httpx.Client` / `httpx.AsyncClient` 必须设置 `trust_env=False`，禁止裸 `httpx.get/post` 快捷调用。
- **严禁自己重写 pycore 已提供的核心模块**：新项目后端**必须基于 pycore 框架开发**，禁止在 `backend/src/core/`、`backend/src/api/` 下自己重写 `config.py`、`server.py`、`logger.py`、`exceptions.py`、`responses.py`、`middleware.py` 等。配置管理使用 `pycore.core.ConfigManager`，服务器使用 `pycore.api.APIServer`，日志使用 `pycore.core.get_logger()`，统一响应用 `pycore.api.responses`。
- **数据库分层骨架必须使用 pycore 模板**：`db/models.py`、`db/session.py`、`api/deps.py` 必须从 `pycore/integrations/db/` 和 `pycore/api/` 复制模板后按需扩展，禁止从零手写 SQLAlchemy 基类或会话管理。
- **认证/权限默认使用路由级依赖，不使用全局认证中间件**：PyCore/FastAPI 项目的认证、鉴权、权限控制默认在 `backend/src/api/deps.py` 中实现为依赖函数（如 `get_current_user`、`require_admin`），受保护路由通过 `Depends(...)` 显式启用。CORS、日志、请求上下文、异常处理可以是全局中间件；认证/权限不得默认注册全局 AuthMiddleware，也不得要求 `app.user_middleware` 中出现认证中间件，除非任务明确要求“所有接口默认拦截 + 公开接口 allowlist”。认证依赖中的数据库会话必须从项目运行时代码导入（如 `from src.db.session import get_db`），禁止直接使用 `pycore.integrations.db.session.get_db` 连接模板默认数据库。
- **业务代码目录固定为 `backend/src`**：后端业务代码统一放在 `backend/src/` 下，如 `backend/src/api/`、`backend/src/services/`、`backend/src/dal/`、`backend/src/models/`、`backend/src/config/`、`backend/src/utils/`。不得要求项目在 `backend/` 根目录直接创建 `routes/`、`services/`、`dal/` 等业务目录。
- **代码质量工具链必须配置且范围收敛**：新项目必须在项目根目录提供 `pyproject.toml`（含 ruff、mypy、pytest 配置），可从 `pycore/pyproject.toml` 复制后调整。项目级质量门禁只覆盖业务代码 `backend/src` 与 `backend/tests`，默认命令为 `python3.11 -m ruff check backend/src backend/tests`、`python3.11 -m mypy backend/src backend/tests`、`python3.11 -m pytest backend/tests`。`pycore/` 是后端框架依赖，不纳入项目任务的 lint/typecheck/test 质量门禁；除非任务明确是维护 pycore 框架，否则不得用 `ruff check .`、`mypy .`、`pytest .` 作为后端验收命令。
- **测试数据库必须与运行时数据库物理隔离**：`backend/tests/*` 只能使用独立测试库、临时库或事务回滚夹具，禁止直接使用运行时业务库（如 `backend/data/customer_service.db`）。测试代码不得导入运行时 `src.db.session.engine` / `async_session_maker` 后执行 `Base.metadata.drop_all`、`drop_all()` 或等价清表操作。FastAPI 集成测试必须通过 `app.dependency_overrides[get_db]` 注入测试库 session；测试清理只能清理测试库。执行 `python3.11 -m pytest backend/tests` 后，必须确认真实业务库中的核心表和 seed 数据仍存在，防止“测试全绿但联调数据库被清空”。
- **真实运行路径必须可用**：后端服务、初始化脚本、维护脚本必须支持从 `backend/` 目录执行：`cd backend && PYTHONPATH=.. python3.11 ...`。`backend/scripts/*.py` 必须把 `backend/` 作为包根，统一使用 `src.*` 导入；禁止把 `backend/src` 加入 `sys.path` 后使用 `db.*`、`config.*`、`models.*` 等裸导入。涉及 `backend/src/main.py`、`backend/src/db/session.py`、`backend/src/db/models.py`、`backend/scripts/*.py` 的任务，必须做真实路径短时验证，不能只依赖项目根目录下的 pytest。
- **SQLite 路径必须规范化**：`.env` 可使用 `DATABASE_PATH=backend/data/customer_service.db` 这类项目根相对路径，但生成 SQLite URL 前必须解析为绝对路径，并自动创建父目录（`mkdir(parents=True, exist_ok=True)`），避免在 `cd backend` 真实启动路径下解析成 `backend/backend/...` 或报 `unable to open database file`。
- **本地端口策略必须固定**：Agent 自动开发 / Tester 自动验证统一使用后端 `8099`、前端 `5199`；用户门禁验收指令统一使用后端 `8003`、前端 `5175`。不得默认占用常见端口 `8000` / `5173`。后端 CORS 必须同时允许 `http://localhost:5199`、`http://127.0.0.1:5199`、`http://localhost:5175`、`http://127.0.0.1:5175`，避免 Agent 验证和用户门禁验收端口不一致导致假失败。
- **百炼平台禁止使用官方 SDK**：调用阿里云百炼（LLM/Embedding/Reranker）时，禁止使用 `dashscope` 等官方 SDK。必须使用 `httpx` / `aiohttp` 直接发送 HTTP 请求，手动构造请求体、解析响应 JSON。原因：SDK 封装层隐藏真实响应结构，易导致假设错误；直接 HTTP 调用结构透明、可控、Mock 简单。
- **真实密钥只能进入配置文件**：真实 API Key、Token、JWT Secret、数据库密码等敏感值只能写入 `.env`、`.env.local` 或用户明确指定的本地 secret 配置文件。`docs/**`、`.sdd/**`、测试报告、完成报告、BUG 日志、经验记录、README、任务 JSON、接口契约中一律只能写字段名和配置状态，禁止写真实值、部分值或 `sk-...` / `Bearer ...` 片段。
- **日志参数禁止与 Logger 接口冲突**：禁止用 `message=` 作为关键字参数传入 `logger.info/warning/error()`，与 Python `Logger.warning(msg, ...)` 第一个位置参数冲突。改用 `api_message=` / `error_msg=` / `detail=`。

---

## 阶段判断

通过检查项目状态判断当前处于后端开发的哪个阶段：

- `docs/Plan.md` 中没有"二、后端开发"章节 → **初始化阶段**（执行下方「首次进入后端开发」）
- `docs/Plan.md` 中有后端章节且基础设施未勾选 → **基础设施阶段**
- `docs/Plan.md` 中基础设施已勾选 → **功能开发阶段**（执行下方「逐功能开发」）

---

## 首次进入后端开发（仅执行一次）

以下步骤在后端开发启动时执行，完成后不再重复。

### 1. 自动探测 Python 指令

Agent 必须先自行探测可用的 Python 3.11+ 指令，不要把这个动作交给用户。

按顺序尝试：

```
python3.11 --version
python3 --version
python --version
```

选择第一个版本号满足 3.11+ 的指令，并记录到 `docs/Plan.md` 的 Python 环境小节。后续**所有命令统一使用该指令**。

只有在以下情况才询问用户：

- 三个候选指令都不存在；
- 存在 Python，但版本低于 3.11；
- 当前命令执行权限不足，Agent 无法完成探测。

探测完成后，Agent 必须自动创建项目内虚拟环境 `.venv` 并安装依赖；不得让用户手动执行项目本地安装命令。

```bash
# 示例：Agent 探测到指令为 python3.11
python3.11 -m venv .venv
source .venv/bin/activate

# 安装依赖（在虚拟环境激活后执行）
python3.11 -m pip install -r requirements.txt

# 启动后端（从 backend/ 目录执行，PYTHONPATH=.. 让 pycore 可导入）
cd backend
PYTHONPATH=.. python3.11 -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8099
```

**注意**：
- 本套规范**使用项目内虚拟环境 `.venv`**，除非项目已有明确约定。
- `pycore` **不通过 pip 安装**，而是通过启动命令中的 `PYTHONPATH=..` 引入（详见本文件「PyCore 核心配置」章节）。
- 后续所有启动命令、测试引导中涉及后端启动的地方，**都必须包含 `PYTHONPATH=..`**。

### 2. 复核 .env 配置与外部服务权限

进入后端开发前，Orchestrator 已经执行「外部服务与 Tester 权限门禁」。本阶段必须复核该清单，并把确认后的字段落到 `.env.example` / `.env` 中。

列出后端需要的所有配置项，让用户逐项确认值。示例：

```env
# 数据库
DATABASE_URL=sqlite+aiosqlite:///./app.db

# 服务
HOST=0.0.0.0
PORT=8099
DEBUG=true

# CORS
CORS_ORIGINS=["http://localhost:5199","http://127.0.0.1:5199","http://localhost:5175","http://127.0.0.1:5175"]

# AI/LLM（如需要）
LLM_API_KEY=
LLM_MODEL_NAME=
LLM_BASE_URL=
```

**根据项目实际需求列出配置项，上面只是示例。需要真实密钥、付费资源、外部账号、回调地址、测试账号或 Tester 完整联调权限时，必须在进入自动化开发前一次性向用户确认。普通占位配置、SQLite、本地 Mock 服务不得阻塞后端编码。**

**Tester 权限要求：**
- 必要服务 Key / 测试账号 / Base URL / 回调配置缺失时，不得宣称完整联调通过
- 用户明确选择不提供时，必须在 Plan.md / tasks.json 中标记为 Mock/fallback 降级开发
- 真实 Key 不得写入 PRD、Plan、tasks.json、测试报告、完成报告、BUG 日志、经验文件、README 或任何 `.md` / `.json` 可读产物；只能写入 `.env` 等配置文件，示例文件只写字段名和占位值

### 3. 补充 Plan.md 后端部分

**`docs/Plan.md` 在设计阶段 C 已由 Agent 生成初始版本**（包含功能清单、数据契约、前端清单、后端清单）。首次进入后端开发时，需要补充后端专属信息：

**补充内容：**
- Python 环境信息（Agent 探测到的 Python 指令、项目内 `.venv`）
- 后端功能清单的依赖关系确认
- .env 配置确认结果
- 外部服务与 Tester 权限确认结果

**拆解原则：**
- 按 **能力依赖** 拆，绝不按页面或菜单顺序排开发优先级
- 由 Planner / Developer / Tester 在多智能体开发阶段内部确认；只有涉及架构级取舍或 PRD/API 契约歧义时才询问用户
- **数据与调用链优先**：先有 DB + 可写可读，再做检索/生成等上层能力
- 先列出所有功能，再标注依赖关系，最后按依赖拓扑排序

**示例：电商系统**
```
错误（按页面）：首页功能 → 商品页 → 购物车 → 订单
正确（按依赖）：用户认证 → 商品管理 → 购物车 → 订单 → 支付
```

**在 Plan.md「四、后端开发清单」中补充 Python 环境信息：**

```markdown
### Python 环境
- **Python 指令**：`<Agent 探测到的 3.11+ 指令>`
- **虚拟环境**：`.venv`
- [ ] Agent 已确认 Python 指令（`<指令> --version` 输出 3.11.x 或更高）
```

> Plan.md 的完整模板和维护规则定义在 `harness-core/skills/sdd-product-design/phase-C.md` 阶段 C3 中。

完成以上第 1～3 步后，直接进入后端编码阶段。除非 PRD / API 契约存在歧义或涉及架构级决策，不得向用户发起推进确认。

---

## 逐功能开发（日常执行）

### 进入每个功能前：触发 feature-plan skill（必须）

**开发任意功能（含基础设施）之前，必须先执行以下流程：**

```
1. 声明：「我将使用 feature-plan skill 为 [功能名] 生成分层实现思路」
2. 读取 docs/Plan.md 中该功能的业务说明与依赖
3. 生成分层实现思路 → 写入 Plan.md「五、功能详情」对应功能下方
4. 将展开后的思路写入 `docs/Plan.md`，由 Developer 按该思路继续实现
5. 只有涉及业务目标、架构取舍或 API 契约歧义时，才向用户确认
```

**禁止**：未生成分层实现思路直接开工；但不得把常规功能实现思路交给用户确认作为编码门禁。

---

### 分层开发顺序

每个功能内部按从下往上的顺序开发：

```
models/（Pydantic）→ db/models.py（ORM）→ repositories/
  → services/ → api/deps.py → api/routes/
```

**原则**：每一层只依赖它下面的层，不得反向依赖。各层规范见 `backend-layers.md`。

### 开发节奏

```
功能 N：
  触发 feature-plan skill → 生成分层实现思路 → Developer 执行
  → 按计划逐层实现
  → 后端功能完成后，立即修正对应前端 service / store / page → VITE_USE_MOCK=false 时调用真实后端
  → Tester/Agent 自动执行前端真实联调检查 + 终端接口测试
  → 自动验证通过 → Plan.md 状态改为「已完成」
  → 功能 N+1（按依赖顺序）
```

---

### 每个功能完成后：Agent 先测试，再提供验收指令（强制）

**后端功能完成 + 对应前端切换到真实接口后，Agent 必须先自行执行可自动化的验证命令。**

**提交前必查清单（强制）：**

```
□ python3.11 -m ruff check backend/src backend/tests 通过
□ python3.11 -m mypy backend/src backend/tests 通过
□ python3.11 -m pytest backend/tests 通过（如有新增/修改测试）
□ backend/tests 使用独立测试库或事务回滚；未对运行时业务库执行 drop_all / 清表；pytest 后真实库核心表与 seed 数据仍存在
□ 涉及数据库字段 → 对照 PRD 第7章核对字段名、类型、约束
□ 涉及外部服务 → 至少执行1次真实调用，打印响应结构确认解析正确；HTTP 客户端显式 `trust_env=False`，未继承本机代理/证书/系统环境
□ 代码无硬编码密钥
```

执行顺序：

1. Agent 自行启动/调用必要的短时验证命令（lint、typecheck、unit test、curl、构建检查等）。
2. Agent 记录验证结果；**失败时先自行修复，不能直接把错误甩给用户**。
3. 对 Web 项目后端业务任务，Agent/Tester 必须验证 `VITE_USE_MOCK=false` 的真实前后端路径；只验证 curl 不足以通过。
4. 只有需要人工界面验收的部分，才交给用户操作。
5. 最终仍要向用户提供两套验收方式，方便复现。

```
【功能测试指令】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 已完成：[功能名称]
📍 修改文件：[列出修改的文件]

🖥️ 前端测试（用户操作页面验证）：
  1. 启动后端：cd backend && PYTHONPATH=.. <python指令> -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8003
  2. 启动前端：cd frontend && VITE_BACKEND_PROXY_TARGET=http://localhost:8003 npm run dev -- --host 127.0.0.1 --port 5175
  3. 打开浏览器访问：http://localhost:5175
  4. 操作步骤：
     - [具体操作，如：进入登录页，输入 test@test.com / 123456]
     - [具体操作，如：点击登录按钮]
  5. 预期结果：
     - [如：页面跳转到首页，右上角显示用户名]

💻 终端测试（curl 命令验证接口）：
  # 测试 [接口名称]
  curl -X POST http://localhost:8003/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username": "test@test.com", "password": "123456"}'

  # 预期返回：
  # {"code": 200, "data": {"access_token": "...", "user": {...}}}

⚠️ 我已先完成自动化验证。若你人工验收时结果不一致，再把现象发给我。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**规则：**
- 前端测试：Agent 可自动执行的启动、构建、接口联通检查必须先自行执行；页面交互验收才交给用户
- 终端测试：Agent 必须先自行运行 curl 或等价接口测试；再给出可复制粘贴的 curl 命令 + 预期返回的 JSON 格式
- curl 命令中的请求体必须与 api-contracts.md 一致
- 预期返回必须与 api-contracts.md 的响应格式一致
- 如果接口需要认证（Bearer Token），先给出获取 token 的 curl，再给出业务接口的 curl

---

### Mock 退出与真实联调（强制）

前端 Mock 只服务于前端 MVP 与契约对齐。每完成一个对应前端页面或 service 的后端业务功能，必须同步更新前端：

1. 确保 `frontend/src/services/` 中该功能在 `VITE_USE_MOCK=false` 时调用真实后端 API
2. 若原先存在 `frontend/src/mocks/` 分支，可以保留为开发演示模式，但不得作为该功能的默认验收路径
3. 移除该功能相关的 `[Mock]` 展示、Mock 账号提示或 Mock-only 文案
4. Tester 必须验证真实请求命中后端接口；可通过浏览器、构建检查、短时服务检查或等价自动化方式证明
5. **禁止**后端业务功能已完成但前端仍停留在 Mock 状态

例外：基础设施、数据库初始化、外部 SDK 客户端封装等没有直接前端入口的底层任务，可以只做后端验收；但如果外部真实密钥/付费资源缺失，只能标记 Mock/fallback 验收通过，不能宣称真实外部能力已验收。

---

### Plan.md 维护规范

`docs/Plan.md` 是唯一的进度文件，设计阶段生成、开发阶段维护。

**规则：**
1. 功能完成后在后端清单的「状态」列改为「已完成」并注明日期
2. **禁止**跳过 feature-plan skill 直接改为「已完成」
3. 每个分层步骤完成后立即勾选对应的 `- [ ]`
4. Tester/Agent 自动验证通过后勾选「自动验证通过」；最终业务验收通过后再勾选「用户验收通过」
5. 测试指令写入 Plan.md 对应功能的详情中（「五、功能详情」）
6. 开发途中若发现依赖顺序或功能边界不合理，先由 Planner 调整 `tasks.json` / `docs/Plan.md`；只有涉及业务目标或架构取舍时才询问用户

---

## 交付

全部功能自动验证通过后，输出 `docs/startup.md`（环境要求、启动命令、默认配置）。用户最终业务验收发现问题时，再进入 `sdd-bugfix`。

---

## PyCore 核心配置（原 backend-core）

### ConfigManager 速查

```python
from pycore.core import ConfigManager, BaseSettings

class AppSettings(BaseSettings):
    debug: bool = False
    secret_key: str  # 必须从 backend/.env 读取，禁止写默认值
    database_url: str = "sqlite+aiosqlite:///./app.db"
    host: str = "0.0.0.0"
    port: int = 8099
    cors_origins: list[str] = [
        "http://localhost:5199",
        "http://127.0.0.1:5199",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ]

config = ConfigManager[AppSettings]()
config.load(AppSettings, "backend/.env")
settings = config.settings
```

> `ConfigManager.load()` 支持直接读取 `backend/.env`，默认 `use_env=False`，不得用进程环境变量覆盖文件配置。不要自行 `os.getenv()` 拼字典再 `load_from_dict()`。`.env` 文件加入 `.gitignore`，项目根目录提供 `.env.example`。

### Logger 速查

```python
from pycore.core import Logger, LoggerConfig, LogLevel, get_logger

Logger.configure(LoggerConfig(level=LogLevel.INFO, app_name="myapp", json_format=False))
logger = get_logger()
logger.info("Server starting", host="127.0.0.1", port=8099)
```

- BasePlugin **没有**内置 logger → 用模块级 `get_logger()`
- BaseService **有**内置 `self.logger`

### 异常使用速查

| 场景 | 使用方式 |
|------|---------|
| Plugin 业务错误 | `return self.fail("msg")` |
| 系统级错误 | `raise ConfigurationError("msg")` |
| 路由层返回 | `error_response("msg", "CODE", 404)` |

### main.py 标准模板

```python
from pycore.core import Logger, LoggerConfig, LogLevel, ConfigManager, get_logger
from pycore.api import APIServer, APIConfig
from src.api.routes.auth import router as auth_router
from src.api.routes.items import router as items_router
from src.db.session import engine, init_db, close_db

Logger.configure(LoggerConfig(level=LogLevel.INFO, app_name="myapp", json_format=False))
logger = get_logger()

server = APIServer(APIConfig(
    title="My Application", version="1.0.0",
    host="127.0.0.1", port=8099, debug=True,
    cors_origins=[
        "http://localhost:5199",
        "http://127.0.0.1:5199",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
))

server.on_startup(init_db)
server.on_shutdown(close_db)
server.include_router(auth_router)
server.include_router(items_router)

app = server.app  # cd backend && PYTHONPATH=.. <python指令> -m uvicorn src.main:app --reload
```

### pycore 引入方式

`pycore` 与 `backend/` 并列存放在项目根目录下，**不通过 pip 安装**，通过 `PYTHONPATH` 引入：

```
project/
├── pycore/          ← 框架包
├── backend/
│   ├── src/
│   │   └── main.py  ← from pycore.core import ...
│   └── .env
└── frontend/
```

```bash
cd backend
PYTHONPATH=.. <python指令> -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8099
```

### 项目结构

```
project/
├── pycore/                     ← 框架包（PYTHONPATH 引入）
├── docs/                       ← 产品设计阶段输出
├── backend/
│   ├── .env
│   ├── src/
│   │   ├── api/deps.py, routes/
│   │   ├── db/models.py, session.py
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   └── main.py
│   └── tests/
├── frontend/
│   └── src/components/, pages/, stores/, services/, router/
└── docs/
```

### 错误码规范

| 错误码 | HTTP | 含义 |
|--------|------|------|
| `VALIDATION_ERROR` | 400 | 参数验证失败 |
| `UNAUTHORIZED` | 401 | 未认证 |
| `FORBIDDEN` | 403 | 无权限 |
| `NOT_FOUND` | 404 | 资源不存在 |
| `CONFLICT` | 409 | 资源冲突 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

### 禁止读取

**禁止读取 `pycore/docs/` 目录下的任何 `.md` 文件。** 这些文档是供人阅读的参考资料，token 量大。模型只需检查文件是否存在，不要打开阅读。

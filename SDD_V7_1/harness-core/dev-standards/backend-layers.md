

# 后端分层开发规范

本文件整合了 Models、DB/Repository、Service、API 四层的开发规范。开发顺序从下往上：

```
models/（Pydantic）→ db/models.py（ORM）→ repositories/ → services/ → api/routes/
```

**原则：每一层只依赖它下面的层，不得反向依赖。**

---

## 层 1：模型层（Pydantic + ORM）

### 两种「模型」不要混

| 类型 | 位置 | 用途 |
|------|------|------|
| **API / 领域模型（Pydantic）** | `src/models/` | 请求体验证、响应序列化、与前端/接口契约对齐 |
| **持久化模型（ORM）** | `src/db/models.py` | 表结构、与数据库一一对应 |

**原则**

- 路由层**只**用 Pydantic 描述请求体/响应形状，**不要**把 SQLAlchemy 实体直接当 JSON 返回。
- ORM 模型不负责表达「接口契约」；Pydantic 模型不负责表达「建表 SQL」。
- 转换（ORM ↔ DTO）放在 Service 中，避免 Repository / Route 里堆字典拼装。

### Pydantic（`src/models/`）

- 按资源分文件：`user.py`、`task.py`
- 命名后缀：`*Create` / `*Update`（写操作入参）、`*Read` / `*Response` / `*Public`（读操作出参）
- 密码、内部字段**不得**放进 `*Response`
- 校验约束写在 `Field()` 内；路径/Query 参数**不用** `Field()`，用 `Path()` / `Query()`

```python
# src/models/user.py
from pydantic import BaseModel, ConfigDict, Field, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str | None = Field(None, max_length=100)

class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    name: str | None
```

### ORM（`src/db/models.py`）

```python
# src/db/models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    name: Mapped[str | None]
```

---

## 层 2：数据访问层（DB Session + Repository）

### 数据库会话

```python
# src/db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

engine = create_async_engine(DATABASE_URL, echo=DEBUG)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Repository

```python
# src/repositories/user.py
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.db.models import User

class UserRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, email: str, hashed_password: str, name: str = None) -> User:
        user = User(email=email, hashed_password=hashed_password, name=name)
        self.db.add(user)
        try:
            await self.db.flush()
        except IntegrityError as e:
            await self.db.rollback()
            raise ValueError(f"数据冲突: {e.orig}") from e
        await self.db.refresh(user)
        return user
```

### 错误处理链路

```
Repository: IntegrityError → ValueError（数据冲突）
Service:    ValueError / 业务异常（产生或透传）
路由:       @handle_errors 捕获 ValueError→400, PermissionError→403
全兜底:     ErrorHandlerMiddleware → 500
```

### 数据库初始化

```python
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def close_db():
    await engine.dispose()
```

### 依赖清单

| 包 | 用途 |
|---|------|
| `sqlalchemy[asyncio]>=2.0` | ORM |
| `aiosqlite>=0.19.0` | SQLite 异步（开发） |
| `asyncpg>=0.27.0` | PostgreSQL 异步（生产） |

---

## 层 3：Service 层

### BaseService（状态机，可选）

```
IDLE ──→ RUNNING ──→ IDLE
  │         │
  └───── ERROR
```

```python
from pycore.services import BaseService

class DataProcessor(BaseService):
    name: str = "data_processor"

    async def process(self, data: dict) -> dict:
        self.logger.info("Processing", data_size=len(data))
        return {"status": "processed"}
```

- BaseService **有**内置 `self.logger`
- 必须在 `IDLE` 状态才能进入 `running()`

### 普通业务 Service（不需要状态机时用这种）

密码哈希须使用 **`bcrypt`**，**禁止 `passlib`**：

```python
# src/core/security.py
import bcrypt

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
```

```python
# src/services/user.py
from pycore.core import get_logger
from src.repositories.user import UserRepository
from src.core.security import hash_password

logger = get_logger()

class UserService:
    def __init__(self, repo: UserRepository):
        self.repo = repo

    async def register(self, email: str, password: str, name: str = None):
        existing = await self.repo.get_by_email(email)
        if existing:
            raise ValueError("Email already registered")
        hashed = hash_password(password)
        user = await self.repo.create(email, hashed, name)
        logger.info("User registered", user_id=user.id)
        return user
```

---

## 层 4：API 路由层

### 响应模型速查

```python
from pycore.api import success_response, error_response, paginated_response
return success_response(data=user_data, message="User created")
resp, _ = error_response(error="Not found", error_code="NOT_FOUND", status_code=404)
return resp
return paginated_response(data=items, page=1, page_size=20, total_items=100)
```

### 路由速查

```python
from pycore.api import APIRouter
from pycore.api.routes import Pagination, handle_errors
from fastapi import Depends

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/{user_id}")
@handle_errors
async def get_user(user_id: int):
    ...
```

**注册路由**：
```python
server.include_router(router)          # APIServer 自动处理
app.include_router(router.router)      # 直接用 FastAPI app 时需要 .router
```

### 参数来源速查

| 来源 | 装饰器 |
|------|--------|
| URL 路径 | 自动 / `Path()` |
| 查询字符串 | `Query()` |
| 请求头 | `Header()` |
| Cookie | `Cookie()` |
| 请求体 | Pydantic Model |
| 依赖注入 | `Depends()` |

> `Field()` 仅用于 Pydantic 模型内部，路由参数必须用以上 FastAPI 装饰器。

---

## 易错点汇总

| 层 | 错误 | 正确 |
|----|------|------|
| Models | 路由参数用 `Field(ge=1)` | 用 `Query(ge=1)` / `Path()` |
| Models | ORM 实体直接 return 给前端 | 返回 Pydantic `*Public`，在 Service 里组装 |
| Models | 一套 BaseModel 既当请求又当响应 | 拆分 `*Create` / `*Public` |
| DB | Repository 里只 `db.add()` 不 `flush()` | `add()` 后必须 `await db.flush()` |
| DB | 在路由层直接捕获 `IntegrityError` | 在 Repository 层捕获，转为 `ValueError` |
| Service | 使用 `passlib` / `CryptContext` | 使用 `bcrypt` 库 |
| Service | BaseService 用 `get_logger()` | BaseService 用 `self.logger`（内置） |
| Service | 普通 Service 用 `self.logger` | 普通 Service 用模块级 `get_logger()` |
| API | `return error_response(...)` | `resp, _ = error_response(...); return resp`（解包） |
| API | `app.include_router(router)` | `app.include_router(router.router)`（PyCore APIRouter） |

---

## 深入阅读

- API 完整规范：`pycore/docs/specs/api.md`
- Service 完整规范：`pycore/docs/specs/services.md`
- Core 完整规范：`pycore/docs/specs/core.md`

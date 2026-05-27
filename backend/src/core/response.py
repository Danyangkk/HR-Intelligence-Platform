from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    msg: str = "ok"
    data: T | None = None


def ok(data: Any = None, msg: str = "ok") -> dict[str, Any]:
    return {"code": 0, "msg": msg, "data": data}


def fail(code: int, msg: str, data: Any = None) -> dict[str, Any]:
    return {"code": code, "msg": msg, "data": data}

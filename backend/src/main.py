from pycore.api import APIServer, APIConfig
from pycore.core import Logger, LoggerConfig, LogLevel, get_logger

from src.api.v1 import api_router
from src.core.config import get_settings
from src.core.response import ok
from src.db.session import close_db

Logger.configure(LoggerConfig(level=LogLevel.INFO, app_name="hr-agent", json_format=False))
logger = get_logger()
settings = get_settings()

server = APIServer(
    APIConfig(
        title="HR Agent API",
        version="0.1.0",
        host="0.0.0.0",
        port=8000,
        debug=settings.app_env == "development",
        cors_origins=[
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ],
    )
)

server.on_shutdown(close_db)
server.include_router(api_router, prefix=settings.api_prefix)

app = server.app

for route in list(app.routes):
    if getattr(route, "path", None) == "/health":
        app.routes.remove(route)


@app.get("/health")
async def health() -> dict:
    return ok({"status": "healthy", "env": settings.app_env})

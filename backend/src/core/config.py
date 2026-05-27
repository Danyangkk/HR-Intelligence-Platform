from __future__ import annotations

from pathlib import Path
from typing import Any

from pycore.core import BaseSettings, ConfigLoader, ConfigManager

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_CANDIDATES = (_BACKEND_DIR / ".env", _BACKEND_DIR.parent / ".env")
_ENV_FILE = next((path for path in _ENV_CANDIDATES if path.exists()), _BACKEND_DIR / ".env")


class DotEnvConfigLoader(ConfigLoader):
    """Load KEY=value pairs from a .env file (no process env inheritance)."""

    def supports(self, path: Path) -> bool:
        return path.name.endswith(".env")

    def load(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        data: dict[str, Any] = {}
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            norm_key = key.strip().lower()
            val = value.strip().strip('"').strip("'")
            if val.lower() in ("true", "false"):
                data[norm_key] = val.lower() == "true"
            elif val.isdigit():
                data[norm_key] = int(val)
            else:
                data[norm_key] = val
        return data


class AppSettings(BaseSettings):
    app_env: str = "development"
    secret_key: str = "dev-secret-change-me"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://hr:hr_secret@localhost:5432/hr_agent"
    database_url_sync: str = "postgresql+psycopg://hr:hr_secret@localhost:5432/hr_agent"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "hr-documents"
    minio_secure: bool = False
    dashscope_api_key: str = ""
    dashscope_chat_model: str = "qwen-long"
    agent_llm_enabled: bool = True
    feishu_api_base: str = "https://open.feishu.cn"
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    feishu_bitable_app_token: str = ""
    feishu_bitable_profile_table_id: str = ""
    feishu_bitable_position_table_id: str = ""
    feishu_bitable_roster_table_id: str = ""
    feishu_bitable_leave_table_id: str = ""
    feishu_bitable_travel_table_id: str = ""
    feishu_bitable_outgoing_table_id: str = ""
    feishu_bitable_overtime_table_id: str = ""
    feishu_bitable_access_attendance_table_id: str = ""
    feishu_bitable_feishu_attendance_table_id: str = ""
    feishu_bitable_attendance_summary_table_id: str = ""
    feishu_bitable_change_table_id: str = ""
    feishu_sync_demo_fallback: bool = True
    jwt_expire_minutes: int = 1440


_manager = ConfigManager[AppSettings]()
_manager.register_loader(DotEnvConfigLoader())
if _ENV_FILE.exists():
    _manager.load(AppSettings, _ENV_FILE, use_env=False)
else:
    _manager.load_from_dict(AppSettings, {})


def get_settings() -> AppSettings:
    return _manager.settings

from __future__ import annotations

import time
from typing import Any

import httpx

from src.core.config import AppSettings, get_settings


class FeishuAPIError(Exception):
    pass


class FeishuClient:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.feishu_api_base.rstrip("/")
        self._token: str | None = None
        self._token_expires_at = 0.0

    def get_tenant_access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        if not self.settings.feishu_app_id or not self.settings.feishu_app_secret:
            raise FeishuAPIError("缺少 FEISHU_APP_ID / FEISHU_APP_SECRET")

        payload = {
            "app_id": self.settings.feishu_app_id,
            "app_secret": self.settings.feishu_app_secret,
        }
        data = self._post_json("/open-apis/auth/v3/tenant_access_token/internal", payload, auth=False)
        token = data.get("tenant_access_token")
        if not token:
            raise FeishuAPIError("飞书 tenant_access_token 为空")
        self._token = token
        self._token_expires_at = now + float(data.get("expire", 7200))
        return token

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def post(self, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("POST", path, json=json or {})

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.get_tenant_access_token()}"}
        url = f"{self.base_url}{path}"
        with httpx.Client(trust_env=False, timeout=30.0) as client:
            response = client.request(method, url, headers=headers, params=params, json=json)
            response.raise_for_status()
            body = response.json()
        if body.get("code") != 0:
            raise FeishuAPIError(body.get("msg") or "飞书 API 调用失败")
        return body.get("data") or {}

    def _post_json(self, path: str, payload: dict[str, Any], *, auth: bool) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers: dict[str, str] = {}
        if auth:
            headers["Authorization"] = f"Bearer {self.get_tenant_access_token()}"
        with httpx.Client(trust_env=False, timeout=30.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        if body.get("code") != 0:
            raise FeishuAPIError(body.get("msg") or "飞书 API 调用失败")
        return body.get("data") or body

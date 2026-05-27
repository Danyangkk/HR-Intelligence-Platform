from __future__ import annotations

import io
import uuid
from datetime import timedelta

from minio import Minio

from src.core.config import get_settings


def get_minio_client() -> Minio:
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    settings = get_settings()
    client = get_minio_client()
    client.put_object(
        settings.minio_bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return key


def presigned_get_url(key: str, expires_hours: int = 2) -> str:
    settings = get_settings()
    client = get_minio_client()
    return client.presigned_get_object(
        settings.minio_bucket,
        key,
        expires=timedelta(hours=expires_hours),
    )


def delete_object(key: str) -> None:
    settings = get_settings()
    client = get_minio_client()
    client.remove_object(settings.minio_bucket, key)


def new_object_key(l3_id: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"{l3_id}/{uuid.uuid4().hex}.{ext}"

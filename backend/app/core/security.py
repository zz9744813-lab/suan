"""Simple API key auth (header: X-API-Key) per spec §20 / P0."""
from __future__ import annotations

from fastapi import Header, HTTPException, status

from app.core.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "type": "Unauthorized",
                "message": "API Key 无效或缺失。",
                "suggestion": "在请求头添加 X-API-Key，或在 .env 设置 NOVELFORGE_API_KEY。",
            },
        )

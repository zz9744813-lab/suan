"""Unified error envelope per spec §20.4."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class APIError(HTTPException):
    """HTTP error that follows the NovelForge unified error format."""

    def __init__(
        self,
        *,
        status_code: int,
        error_type: str,
        message: str,
        suggestion: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "type": error_type,
            "message": message,
        }
        if suggestion:
            payload["suggestion"] = suggestion
        if details:
            payload["details"] = details
        super().__init__(status_code=status_code, detail=payload)
        self.error_type = error_type
        self.message = message
        self.suggestion = suggestion
        self.details = details or {}


def model_connection_error(message: str, suggestion: str | None = None) -> APIError:
    return APIError(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_type="ModelConnectionError",
        message=message,
        suggestion=suggestion or "请检查 API Key 或 Base URL。",
    )


def not_found(resource: str, identifier: Any) -> APIError:
    return APIError(
        status_code=status.HTTP_404_NOT_FOUND,
        error_type="NotFound",
        message=f"{resource} 不存在: {identifier}",
    )


def bad_request(message: str, suggestion: str | None = None) -> APIError:
    return APIError(
        status_code=status.HTTP_400_BAD_REQUEST,
        error_type="BadRequest",
        message=message,
        suggestion=suggestion,
    )


def conflict(message: str, suggestion: str | None = None) -> APIError:
    return APIError(
        status_code=status.HTTP_409_CONFLICT,
        error_type="Conflict",
        message=message,
        suggestion=suggestion,
    )

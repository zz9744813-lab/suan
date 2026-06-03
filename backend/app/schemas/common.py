"""Common schema pieces: API envelope and pagination."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


class APIError(BaseModel):
    type: str
    message: str
    suggestion: str | None = None
    details: dict[str, Any] | None = None


class APIResponse(BaseModel, Generic[T]):
    ok: bool = True
    data: T | None = None
    error: APIError | None = None

    @classmethod
    def ok(cls, data: T) -> "APIResponse[T]":
        return cls(ok=True, data=data, error=None)

    @classmethod
    def fail(cls, err: APIError) -> "APIResponse[None]":
        return cls(ok=False, data=None, error=err)


# Module-level helpers avoid Pydantic Generic classmethod quirks.
def ok_response(data: T) -> dict[str, Any]:
    return APIResponse[T](ok=True, data=data, error=None).model_dump(mode="json")


def fail_response(err: APIError) -> dict[str, Any]:
    return APIResponse[None](ok=False, data=None, error=err).model_dump(mode="json")


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    items: list[T]
    total: int = Field(default=0)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

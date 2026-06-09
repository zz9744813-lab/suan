from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_TEXT_CONTROL_TRANSLATION = {
    0x00: None,
}


def sanitize_text(value: str) -> str:
    return value.translate(_TEXT_CONTROL_TRANSLATION)


def sanitize_for_storage(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, Mapping):
        return {key: sanitize_for_storage(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(sanitize_for_storage(item) for item in value)
    if isinstance(value, list):
        return [sanitize_for_storage(item) for item in value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return type(value)(sanitize_for_storage(item) for item in value)
    return value

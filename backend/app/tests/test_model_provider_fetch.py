from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.llm.client import LLMClient


class _Response:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data
        self.text = str(data)

    def json(self) -> dict:
        return self._data


@pytest.mark.asyncio
async def test_list_models_accepts_openai_compatible_model_shapes():
    client = LLMClient(timeout=30)
    client._client.get = AsyncMock(return_value=_Response(
        200,
        {
            "data": [
                {"id": "stepfun-ai/step-3.7-flash"},
                {"model": "fallback-model"},
                {"name": "legacy-name-model"},
            ],
        },
    ))

    try:
        models = await client.list_models("http://example.test/v1", "test-key")
    finally:
        await client.aclose()

    assert models == [
        "stepfun-ai/step-3.7-flash",
        "fallback-model",
        "legacy-name-model",
    ]


def test_model_health_monitor_uses_services_probe_result_import():
    import inspect

    from app.services.model_health_monitor import ModelHealthMonitor

    source = inspect.getsource(ModelHealthMonitor._update_snapshot)

    assert "from app.services.model_probe_service import ModelProbeResult" in source
    assert "from app.models.model_probe_service import ModelProbeResult" not in source


def test_model_control_probe_route_accepts_model_names_with_slashes():
    from app.routers.model_control import router

    paths = {getattr(route, "path", "") for route in router.routes}

    assert "/model-control/providers/{provider_id}/models/{model_name:path}/probe" in paths

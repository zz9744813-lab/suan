"""List models on whitedream to see what's available."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.llm.client import LLMClient  # noqa: E402


async def main() -> int:
    base_url = os.environ.get("LLM_BASE_URL", "https://your-provider.example/v1")
    api_key = os.environ.get("LLM_API_KEY", "your-api-key-here")

    client = LLMClient()
    try:
        models = await client.list_models(base_url=base_url, api_key=api_key)
        print(f"available models ({len(models)}):")
        for m in models:
            print(f"  {m}")
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc!r}")
        return 1
    finally:
        await client.aclose()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

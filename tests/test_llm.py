import unittest
from unittest.mock import AsyncMock

from app.llm import OllamaProvider


class OllamaProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_text_uses_discovered_installed_model(self):
        provider = OllamaProvider(preferred_model=None)
        provider._client.list = AsyncMock(return_value={
            "models": [{"model": "test-local:latest", "size": 123}]
        })
        provider._client.chat = AsyncMock(return_value={
            "message": {"content": "A mocked local response."}
        })

        response = await provider.generate_text("Test prompt")

        self.assertEqual(response, "A mocked local response.")
        provider._client.chat.assert_awaited_once()
        self.assertEqual(
            provider._client.chat.await_args.kwargs["model"],
            "test-local:latest",
        )

    async def test_generate_json_requests_ollama_json_mode(self):
        provider = OllamaProvider(preferred_model=None)
        provider._client.list = AsyncMock(return_value={
            "models": [{"model": "test-local:latest"}]
        })
        provider._client.chat = AsyncMock(return_value={
            "message": {"content": '{"queries": ["test"]}'}
        })

        result = await provider.generate_json("Plan a search")

        self.assertEqual(result, {"queries": ["test"]})
        self.assertEqual(provider._client.chat.await_args.kwargs["format"], "json")


if __name__ == "__main__":
    unittest.main()

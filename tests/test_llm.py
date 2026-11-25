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

    async def test_auto_selection_skips_embedding_models(self):
        provider = OllamaProvider(preferred_model=None)
        provider.preferred_model = None
        provider._client.list = AsyncMock(return_value={"models": [
            {"model": "nomic-embed-text:latest"}, {"model": "qwen3:4b"}]})
        capabilities = {"nomic-embed-text:latest": ["embedding"], "qwen3:4b": ["completion", "thinking"]}
        provider._client.show = AsyncMock(side_effect=lambda name: {"capabilities": capabilities[name]})

        self.assertEqual(await provider.select_model(), "qwen3:4b")
        self.assertEqual([m.name for m in await provider.chat_models()], ["qwen3:4b"])

    async def test_auto_selection_fails_clearly_with_only_embedding_models(self):
        from app.llm import LocalModelError
        provider = OllamaProvider(preferred_model=None)
        provider.preferred_model = None
        provider._client.list = AsyncMock(return_value={"models": [{"model": "nomic-embed-text:latest"}]})
        provider._client.show = AsyncMock(return_value={"capabilities": ["embedding"]})

        with self.assertRaises(LocalModelError):
            await provider.select_model()


if __name__ == "__main__":
    unittest.main()

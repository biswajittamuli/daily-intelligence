"""Local Ollama provider with installed-model discovery and strict selection."""

from __future__ import annotations

import json
import os
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any

import ollama

log = logging.getLogger(__name__)


class LocalModelError(RuntimeError):
    """Ollama is unavailable or the configured local model cannot be used."""


@dataclass(frozen=True)
class ModelInfo:
    name: str
    size: int | None = None
    modified_at: str | None = None
    capabilities: tuple[str, ...] = ()


class OllamaProvider:
    """Provider that only uses models already present in the local Ollama store."""

    def __init__(
        self,
        host: str | None = None,
        preferred_model: str | None = None,
        timeout: float | None = None,
        think: bool | None = None,
    ) -> None:
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.preferred_model = preferred_model or os.getenv("OLLAMA_MODEL")
        self.timeout = timeout or float(os.getenv("OLLAMA_TIMEOUT", "120"))
        # Thinking-capable models (e.g. qwen3) spend many seconds on hidden
        # reasoning. These workflows need short structured answers, so disable
        # it unless explicitly enabled with OLLAMA_THINK=1.
        if think is None:
            think = os.getenv("OLLAMA_THINK", "").strip().lower() in {"1", "true", "yes", "on"}
        self.think = think
        self._client = ollama.AsyncClient(host=self.host, timeout=self.timeout)
        self._capability_cache: dict[str, tuple[str, ...]] = {}

    @staticmethod
    def _as_dict(response: Any) -> dict[str, Any]:
        if isinstance(response, dict):
            return response
        if hasattr(response, "model_dump"):
            return response.model_dump()
        return {}

    async def list_models(self) -> list[ModelInfo]:
        try:
            response = await asyncio.wait_for(self._client.list(), timeout=self.timeout)
        except Exception as exc:
            raise LocalModelError(
                f"Cannot reach local Ollama at {self.host}: {exc}"
            ) from exc

        payload = self._as_dict(response)
        models = []
        for model in payload.get("models", []):
            name = model.get("model") or model.get("name")
            if name:
                capabilities = model.get("capabilities") or []
                models.append(ModelInfo(
                    name=name,
                    size=model.get("size"),
                    modified_at=model.get("modified_at"),
                    capabilities=tuple(str(item) for item in capabilities
                                       if isinstance(item, str)),
                ))
        return models

    async def _capabilities_for(self, model: str,
                                known: tuple[str, ...] = ()) -> tuple[str, ...]:
        """Return advertised model capabilities, cached per process.

        The installed ollama client omits `capabilities` from its list
        response, so fall back to the public `show` endpoint.
        """
        if known:
            return known
        if model in self._capability_cache:
            return self._capability_cache[model]
        capabilities: tuple[str, ...] = ()
        try:
            response = await asyncio.wait_for(
                self._client.show(model), timeout=min(self.timeout, 10.0))
            payload = self._as_dict(response)
            capabilities = tuple(str(item) for item in (payload.get("capabilities") or [])
                                 if isinstance(item, str))
        except Exception:
            capabilities = ()
        self._capability_cache[model] = capabilities
        return capabilities

    async def select_model(self) -> str:
        models = await self.list_models()
        names = {model.name for model in models}
        if not names:
            raise LocalModelError(
                "Ollama is running, but no local models are installed. "
                "Install or configure a model explicitly, then retry."
            )
        if self.preferred_model:
            if self.preferred_model not in names:
                raise LocalModelError(
                    f"Configured OLLAMA_MODEL '{self.preferred_model}' is not "
                    f"installed. Available models: {', '.join(sorted(names))}"
                )
            return self.preferred_model
        return models[0].name

    async def generate(
        self,
        prompt: str,
        *,
        system: str = "Be accurate, concise, and explicit about uncertainty.",
        model: str | None = None,
        temperature: float = 0.2,
        context_length: int = 4096,
        stream: bool = False,
        format: str | dict[str, Any] | None = None,
        think: bool | None = None,
        num_predict: int | None = None,
    ) -> Any:
        started = time.perf_counter()
        selected = model or await self.select_model()
        # Validate explicit model arguments too; Ollama otherwise attempts a pull.
        installed = {item.name: item for item in await self.list_models()}
        if selected not in installed:
            raise LocalModelError(f"Model '{selected}' is not installed locally.")
        wants_thinking = self.think if think is None else think
        try:
            log.info("ollama generation started model=%s prompt_chars=%d context=%d",
                     selected, len(prompt), context_length)
            arguments = dict(
                model=selected,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                options={"temperature": temperature, "num_ctx": context_length},
                stream=stream,
            )
            if num_predict is not None:
                arguments["options"]["num_predict"] = max(1, int(num_predict))
            # `think` is rejected by models without thinking support, so only
            # send it when the installed model advertises that capability.
            capabilities = await self._capabilities_for(
                selected, installed[selected].capabilities)
            if "thinking" in capabilities:
                arguments["think"] = wants_thinking
            if format is not None:
                arguments["format"] = format
            response = await asyncio.wait_for(self._client.chat(**arguments), timeout=self.timeout)
            log.info("ollama generation response_received model=%s elapsed=%.2fs",
                     selected, time.perf_counter()-started)
            return response
        except Exception as exc:
            log.error("ollama generation failed model=%s error_type=%s elapsed=%.2fs",
                      selected, type(exc).__name__, time.perf_counter()-started)
            if isinstance(exc, TimeoutError):
                raise LocalModelError(
                    f"Local model generation timed out after {self.timeout:g}s "
                    f"(model '{selected}'). Increase OLLAMA_TIMEOUT or disable "
                    "thinking with OLLAMA_THINK=0."
                ) from exc
            raise LocalModelError(f"Local model generation failed: {exc}") from exc

    async def generate_text(self, prompt: str, **kwargs: Any) -> str:
        started = time.perf_counter()
        response = await self.generate(prompt, **kwargs)
        if hasattr(response, "__aiter__"):
            chunks = []
            async for item in response:
                message = self._as_dict(item).get("message", {})
                chunks.append(message.get("content", ""))
            text = "".join(chunks)
            log.info("ollama generation complete output_chars=%d elapsed=%.2fs", len(text), time.perf_counter()-started)
            return text
        message = self._as_dict(response).get("message", {})
        text = str(message.get("content", ""))
        log.info("ollama generation complete output_chars=%d elapsed=%.2fs", len(text), time.perf_counter()-started)
        return text

    async def generate_json(self, prompt: str, **kwargs: Any) -> Any:
        kwargs.setdefault("format", "json")
        response = await self.generate(prompt, **kwargs)
        message = self._as_dict(response).get("message", {})
        content = message.get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            recovered = _recover_json(content)
            if recovered is not None:
                log.warning("ollama json recovered partial records count=%d",
                            len(next(iter(recovered.values()), [])))
                return recovered
            raise LocalModelError("Local model returned invalid JSON.") from exc


def _recover_json(text: str) -> dict[str, Any] | None:
    """Recover complete objects from a truncated JSON array.

    Small local models sometimes exceed the output token cap and leave the
    final object unterminated. Parsing each balanced object inside the array
    salvages the complete records instead of discarding the whole response.
    """
    key = None
    start = 0
    for candidate in ("listings", "notices", "events", "items", "results"):
        marker = f'"{candidate}"'
        position = text.find(marker)
        if position == -1:
            continue
        bracket = text.find("[", position)
        if bracket != -1:
            key = candidate
            start = bracket + 1
            break
    if key is None:
        return None
    objects: list[Any] = []
    index = start
    length = len(text)
    while index < length:
        if text[index] != "{":
            index += 1
            continue
        depth = 0
        in_string = False
        escaped = False
        begin = index
        cursor = index
        while cursor < length:
            char = text[cursor]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            objects.append(json.loads(text[begin:cursor + 1]))
                        except json.JSONDecodeError:
                            pass
                        index = cursor
                        break
            cursor += 1
        index += 1
    return {key: objects} if objects else None


async def generate_response(prompt: str) -> str:
    """Compatibility function retained for current callers."""
    return await OllamaProvider().generate_text(prompt)

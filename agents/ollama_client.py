"""Async Ollama client."""

from __future__ import annotations

import sys
from typing import TypeVar

from ollama import AsyncClient
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

class _TransportFailure:
    """Singleton sentinel for transport-level failures."""
    _instance: "_TransportFailure | None" = None
    def __new__(cls) -> "_TransportFailure":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

TRANSPORT_FAILURE = _TransportFailure()


class OllamaClient:
    """Minimal wrapper around `ollama.AsyncClient.chat` with schema output."""

    def __init__(
        self,
        model: str,
        debug: bool = True,
        client: AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.debug = debug
        # `client` is a test seam; otherwise use the SDK default (localhost).
        self._client = client if client is not None else AsyncClient()

    async def chat_schema(
        self,
        system: str,
        user: str,
        schema: type[T],
        temperature: float = 0.7,
    ) -> "T | _TransportFailure | None":
        """Ask Ollama for one object matching ``schema``.

        Returns the parsed Pydantic instance, or ``None`` on transport /
        validation failure (each failure is logged to stderr so the
        director loop has something actionable).
        """
        try:
            if self.debug:
                print(f"[ollama] sending chat with system={system[:60]!r} user={user[:60]!r} ")
            response = await self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                format=schema.model_json_schema(),
                options={
                    "temperature": temperature,
                    # Default ollama ctx is 2048 — our system prompt alone
                    # is larger than that, which silently truncates the
                    # input and produces empty output.
                    "num_ctx": 8192,
                    "num_predict": 2048,
                },
            )
        except Exception as e:  # ollama raises ResponseError / httpx errors
            print(f"[ollama] request failed: {e}", file=sys.stderr)
            return TRANSPORT_FAILURE

        content = (response.message.content or "").strip()
        done_reason = getattr(response, "done_reason", None)
        if self.debug:
            print(f"[ollama] raw content: {content!r}", file=sys.stderr)
            prompt_tokens = getattr(response, "prompt_eval_count", None)
            eval_tokens = getattr(response, "eval_count", None)
            print(
                f"[ollama] done_reason={done_reason} "
                f"prompt_tokens={prompt_tokens} eval_tokens={eval_tokens}",
                file=sys.stderr,
            )
        if not content:
            print(f"[ollama] empty content (done_reason={done_reason})", file=sys.stderr)
            return TRANSPORT_FAILURE

        try:
            return schema.model_validate_json(content)
        except ValidationError as e:
            print(
                f"[ollama] schema validation failed: {e}\n"
                f"         content={content[:400]!r}",
                file=sys.stderr,
            )
            return None

    async def aclose(self) -> None:
        inner = getattr(self._client, "_client", None)
        if inner is not None and hasattr(inner, "aclose"):
            try:
                await inner.aclose()
            except Exception:
                pass

"""Shared Claude client: one place for credentials, fallbacks, structured output and error mapping."""

from functools import lru_cache
from typing import Any

import anthropic

from app.core.config import settings


class EngineError(Exception):
    """The AI could not produce a usable answer (not configured, outage, refusal...)."""


class ClaudeClient:
    def __init__(self) -> None:
        try:
            self.client = (
                anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
                if settings.anthropic_api_key
                else anthropic.AsyncAnthropic()
            )
        except Exception as exc:  # no credentials resolvable
            raise EngineError("The AI assistant is not configured") from exc

    async def call(
        self,
        *,
        model: str,
        effort: str,
        system: str,
        content: str | list[dict[str, Any]],
        schema: dict | None = None,
        max_tokens: int = 16000,
    ) -> str:
        """One request; returns the text answer (JSON text when `schema` is given)."""
        output_config: dict[str, Any] = {"effort": effort}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        try:
            response = await self.client.beta.messages.create(
                model=model,
                max_tokens=max_tokens,
                # On a safety-classifier decline, retry server-side on Anthropic's recommended fallback model
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                output_config=output_config,
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.AuthenticationError as exc:
            raise EngineError("The AI assistant is not configured correctly") from exc
        except anthropic.RateLimitError as exc:
            raise EngineError("The AI assistant is busy, please try again in a moment") from exc
        except anthropic.APIStatusError as exc:
            raise EngineError(f"The AI assistant failed ({exc.status_code})") from exc
        except anthropic.APIConnectionError as exc:
            raise EngineError("Could not reach the AI assistant") from exc
        except TypeError as exc:  # the SDK raises this when no credentials can be resolved
            raise EngineError("The AI assistant is not configured") from exc

        if response.stop_reason in ("refusal", "max_tokens"):
            raise EngineError(f"The AI assistant could not answer ({response.stop_reason})")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise EngineError("The AI assistant returned no answer")
        return text


@lru_cache
def claude() -> ClaudeClient:
    return ClaudeClient()

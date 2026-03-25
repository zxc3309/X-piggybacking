"""Anthropic (Claude) provider implementation."""
from __future__ import annotations

import os

from .base import LLMProvider, retry_request


class AnthropicProvider(LLMProvider):

    default_model = "claude-sonnet-4-20250514"

    def __init__(self) -> None:
        self.api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )

    def call(self, prompt: str, content: str, model: str, max_tokens: int) -> str:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "system": prompt,
            "messages": [
                {"role": "user", "content": content},
            ],
        }
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        resp = retry_request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers, body,
            provider_name="Anthropic",
        )
        data = resp.json()
        return data["content"][0]["text"].strip()

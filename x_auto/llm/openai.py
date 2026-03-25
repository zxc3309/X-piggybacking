"""OpenAI provider implementation."""
from __future__ import annotations

import os

from .base import LLMProvider, retry_request


class OpenAIProvider(LLMProvider):

    default_model = "gpt-5.2"

    def __init__(self) -> None:
        self.api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

    def call(self, prompt: str, content: str, model: str, max_tokens: int) -> str:
        # GPT-5.x models use max_completion_tokens instead of max_tokens
        token_param = (
            "max_completion_tokens" if model.startswith("gpt-5") else "max_tokens"
        )
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            token_param: max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        resp = retry_request(
            "POST",
            "https://api.openai.com/v1/chat/completions",
            headers, body,
            provider_name="OpenAI",
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

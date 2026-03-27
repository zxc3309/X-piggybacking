"""OpenAI provider implementation."""
from __future__ import annotations

import os

from .base import LLMProvider, retry_request

# Models that require max_completion_tokens instead of max_tokens
_COMPLETION_TOKEN_MODELS = ("gpt-5", "o1", "o3", "o4")


class OpenAIProvider(LLMProvider):

    default_model = "gpt-5.4-mini"

    def __init__(self) -> None:
        self.api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")

    def call(self, prompt: str, content: str, model: str, max_tokens: int) -> str:
        # GPT-5.x and o-series reasoning models use max_completion_tokens
        token_param = (
            "max_completion_tokens"
            if model.startswith(_COMPLETION_TOKEN_MODELS)
            else "max_tokens"
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

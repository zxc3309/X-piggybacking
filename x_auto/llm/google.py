"""Google Gemini provider implementation."""
from __future__ import annotations

import os

from .base import LLMProvider, retry_request


class GoogleProvider(LLMProvider):

    default_model = "gemini-2.5-pro"

    def __init__(self) -> None:
        self.api_key = (os.getenv("GOOGLE_API_KEY") or "").strip()
        if not self.api_key:
            raise RuntimeError(
                "GOOGLE_API_KEY is required when LLM_PROVIDER=google"
            )

    def call(self, prompt: str, content: str, model: str, max_tokens: int, *, timeout: int = 60) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={self.api_key}"
        )
        body = {
            "system_instruction": {
                "parts": [{"text": prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": content}],
                }
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
            },
        }
        headers = {"Content-Type": "application/json"}
        resp = retry_request(
            "POST", url, headers, body,
            timeout=timeout,
            provider_name="Google",
        )
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

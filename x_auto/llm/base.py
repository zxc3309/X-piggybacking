"""Base class for LLM providers and shared retry logic."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

import requests


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    default_model: str = ""

    @abstractmethod
    def call(self, prompt: str, content: str, model: str, max_tokens: int) -> str:
        """Send a system prompt + user content to the LLM and return response text."""
        ...


def retry_request(
    method: str,
    url: str,
    headers: dict,
    body: dict,
    *,
    timeout: int = 30,
    retries: int = 3,
    provider_name: str = "LLM",
) -> requests.Response:
    """HTTP request with retry, exponential backoff, and 429 handling.

    Returns the successful response or raises RuntimeError.
    """
    last_err: str | None = None
    for attempt in range(retries):
        try:
            resp = requests.request(
                method, url, json=body, headers=headers, timeout=timeout,
            )
            if resp.status_code == 429:
                wait = 2 ** attempt * 2  # 2s, 4s, 8s
                print(f"[{provider_name}] Rate limited (429), waiting {wait}s "
                      f"(attempt {attempt + 1}/{retries})")
                time.sleep(wait)
                continue
            if not resp.ok:
                raise RuntimeError(
                    f"{provider_name} API error {resp.status_code}: {resp.text}"
                )
            return resp
        except requests.exceptions.Timeout:
            last_err = f"Timeout after {timeout}s (attempt {attempt + 1}/{retries})"
            print(f"[{provider_name}] {last_err}")
            time.sleep(2 ** attempt)
        except RuntimeError:
            raise
        except Exception as e:
            last_err = str(e)
            print(f"[{provider_name}] Error: {last_err} (attempt {attempt + 1}/{retries})")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{provider_name} failed after {retries} attempts: {last_err}")

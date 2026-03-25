"""Multi-provider LLM abstraction layer.

Switch providers by setting the ``LLM_PROVIDER`` environment variable:

    LLM_PROVIDER=openai       # default
    LLM_PROVIDER=anthropic
    LLM_PROVIDER=google

Optionally override the default model with ``LLM_MODEL``.
"""
from __future__ import annotations

import importlib
import os

from .base import LLMProvider

_PROVIDERS: dict[str, tuple[str, str]] = {
    "openai": ("x_auto.llm.openai", "OpenAIProvider"),
    "anthropic": ("x_auto.llm.anthropic", "AnthropicProvider"),
    "google": ("x_auto.llm.google", "GoogleProvider"),
}

_instance: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Return a cached provider instance based on LLM_PROVIDER env var."""
    global _instance
    if _instance is not None:
        return _instance

    name = os.getenv("LLM_PROVIDER", "openai").lower().strip()
    if name not in _PROVIDERS:
        available = ", ".join(sorted(_PROVIDERS))
        raise ValueError(
            f"Unknown LLM_PROVIDER '{name}'. Available: {available}"
        )

    module_path, class_name = _PROVIDERS[name]
    mod = importlib.import_module(module_path)
    _instance = getattr(mod, class_name)()

    # Allow env-var model override
    model_override = os.getenv("LLM_MODEL", "").strip()
    if model_override:
        _instance.default_model = model_override

    print(f"[LLM] Provider: {name}, Model: {_instance.default_model}")
    return _instance


def call_llm(
    prompt: str,
    content: str,
    model: str = "",
    max_tokens: int = 50,
) -> str:
    """Drop-in replacement for the old ``call_chatgpt`` function.

    If *model* is empty, the provider's default model is used.
    """
    provider = get_provider()
    effective_model = model or provider.default_model
    return provider.call(prompt, content, effective_model, max_tokens)


# Backward-compatible alias
call_chatgpt = call_llm

__all__ = ["LLMProvider", "get_provider", "call_llm", "call_chatgpt"]

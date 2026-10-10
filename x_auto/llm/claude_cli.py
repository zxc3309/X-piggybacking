"""Claude Code CLI provider (``claude -p``), billed to the logged-in subscription.

Only works on a machine with a logged-in Claude Code (the Mac mini runner), not on
Railway. Runs with no tools, no MCP servers and no settings/CLAUDE.md so the call
is a plain completion.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from .base import LLMProvider


class ClaudeCLIProvider(LLMProvider):

    default_model = "opus"

    def __init__(self) -> None:
        self.binary = os.getenv("CLAUDE_BIN", "claude")

    def call(self, prompt: str, content: str, model: str, max_tokens: int, *, timeout: int = 60) -> str:
        # max_tokens has no CLI equivalent; prompts already ask for short output.
        # The CLI start-up alone takes a few seconds, so allow more than the API default.
        timeout = max(timeout, int(os.getenv("CLAUDE_CLI_TIMEOUT", "180")))
        with tempfile.TemporaryDirectory(prefix="xpiggy-claude-") as workdir:
            prompt_file = os.path.join(workdir, "system.txt")
            with open(prompt_file, "w") as handle:
                handle.write(prompt)
            cmd = [
                self.binary, "-p",
                "--model", model,
                "--system-prompt-file", prompt_file,
                "--tools", "",
                "--strict-mcp-config",
                "--setting-sources", "",
                "--no-session-persistence",
                "--output-format", "json",
            ]
            proc = subprocess.run(
                cmd, input=content, capture_output=True, text=True,
                timeout=timeout, cwd=workdir,
            )
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p exited {proc.returncode}: {proc.stderr.strip()[:300]}")
        data = json.loads(proc.stdout)
        if data.get("is_error"):
            raise RuntimeError(f"claude -p error: {str(data.get('result'))[:300]}")
        return str(data.get("result") or "").strip()

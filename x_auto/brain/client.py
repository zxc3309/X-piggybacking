"""Client for cesecondbrain-api + LLM brain context generation."""
from __future__ import annotations
import logging
import os
import re
from typing import Optional
import requests

logger = logging.getLogger(__name__)

BRAIN_ANALYSIS_PROMPT = """\
你是一位知識管理專家，正在幫助使用者分析一篇 X (Twitter) 貼文與他的 Second Brain（個人知識庫）的關聯。

以下是使用者的相關筆記摘要（從個人知識庫搜尋得到）：
{notes_context}

請根據以上筆記，對這篇貼文生成一份「Second Brain 連結分析」，格式如下：

## 🔗 Second Brain 連結分析

### 文章核心重點
- [3-5 個重點，聚焦在與知識庫最相關的面向]

### 直接相關筆記（強連結）
**[[筆記名稱]]**
- 連結理由：為什麼相關（要具體，不只是關鍵字相同）
- 延伸思考：這篇文章如何補充、挑戰、或延伸你原有的想法

（只列出真正有強連結的筆記，沒有就跳過此段）

### 間接相關筆記（弱連結）
**[[筆記名稱]]** — 概念交集或可延伸的方向

（只列出有弱連結的筆記，沒有就跳過此段）

### 💡 新的思考與寫作靈感
- 這篇文章帶給你的新觀點，以及可以延伸成什麼新的 Card 或 Content Idea

關鍵原則：
- 不只找「提到相同關鍵字」的筆記，更要找「概念可以互相補充或對話」的筆記
- 思考這篇文章是否補充、挑戰、或延伸了既有筆記的觀點
- 如果某篇筆記的連結不夠強，就放到「弱連結」而非強連結

只輸出分析結果，不要其他說明文字。\
"""


def _build_notes_context(results: list[dict]) -> str:
    """Format search results into context string for LLM prompt."""
    lines = []
    for r in results:
        title = r.get("title", "")
        folder = r.get("folder", "")
        tags = ", ".join(r.get("tags", []))
        content = r.get("content", "")[:400]
        linked = [ln.get("title", "") for ln in r.get("linked_notes", [])]

        lines.append(f"### [[{title}]] ({folder})")
        if tags:
            lines.append(f"Tags: {tags}")
        lines.append(content)
        if linked:
            lines.append(f"相關連結: {', '.join(f'[[{t}]]' for t in linked)}")
        lines.append("")
    return "\n".join(lines)


class BrainClient:
    def __init__(self):
        self.base_url = os.getenv("BRAIN_API_URL", "").rstrip("/")
        self.api_key = os.getenv("BRAIN_API_KEY", "")
        self.limit = int(os.getenv("BRAIN_SEARCH_LIMIT", "5"))
        self.enabled = os.getenv("BRAIN_ENABLED", "true").lower() == "true"

    def get_note_context(self, post_text: str, call_llm_fn) -> Optional[dict]:
        """
        1. Call POST /search to get related notes
        2. Call LLM to generate rich brain_context analysis
        Returns: {"brain_context": str, "total": int} or None
        """
        if not self.enabled:
            logger.warning("[Brain] Disabled (BRAIN_ENABLED != true)")
            return None
        if not self.base_url or not self.api_key:
            logger.warning(
                "[Brain] Missing config: url=%s key=%s",
                "SET" if self.base_url else "MISSING",
                "SET" if self.api_key else "MISSING",
            )
            return None
        try:
            # Sanitize query: remove punctuation that may break FTS5 on server
            sanitized = re.sub(r"[.,;:!?\-\—\–\"'`()\[\]{}/\\]", " ", post_text[:500])
            sanitized = re.sub(r"\s+", " ", sanitized).strip()
            resp = requests.post(
                f"{self.base_url}/search",
                json={
                    "query": sanitized,
                    "mode": "hybrid",
                    "limit": self.limit,
                    "include_linked": True,
                    "link_depth": 1,
                },
                headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if not results:
                logger.info("[Brain] No matching notes for: %s", post_text[:80])
                return None

            logger.info("[Brain] Found %d notes, generating context...", len(results))
            # Build notes context for LLM
            notes_context = _build_notes_context(results)
            analysis_prompt = BRAIN_ANALYSIS_PROMPT.format(notes_context=notes_context)

            # Call LLM to generate rich analysis
            brain_context = call_llm_fn(
                prompt=analysis_prompt,
                content=post_text[:1000],
                model="gpt-5.2",       # Use gpt-5.2 for reasoning quality
                max_tokens=600,
            )

            return {
                "brain_context": brain_context.strip(),
                "total": data.get("total", len(results)),
            }
        except Exception as e:
            logger.error(f"Brain API failed for query (first 80 chars): {post_text[:80]!r}: {e}")
            return None

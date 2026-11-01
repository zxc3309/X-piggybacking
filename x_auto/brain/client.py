"""Client for cesecondbrain-api + LLM brain context generation."""
from __future__ import annotations
import logging
import os
import re
import time
from typing import Optional
import requests

logger = logging.getLogger(__name__)

# Bill 2026-11-01: the dashboard is for reading a post fast and seeing which notes echo it.
# Only high-relevance notes are kept; weak links and writing ideas were dropped (they were the
# bulk of the text and rarely used). review/brain_digest.py parses this exact layout.
BRAIN_ANALYSIS_PROMPT = """\
你是一位知識管理專家，幫使用者判斷一篇 X (Twitter) 貼文跟他的 Second Brain（個人知識庫）有沒有高度相關的筆記。

以下是從知識庫搜尋到的候選筆記：
{notes_context}

請嚴格照下面的格式輸出，不要加其他段落：

### 文章核心重點
- **一句話講一個重點（25 字以內）**
（2～3 條，講貼文本身在說什麼，讓人 10 秒看懂）

### 直接相關筆記（強連結）
**[[筆記名稱]]**
- 連結理由：一句話講具體呼應點，例如這篇貼文補充、挑戰或延伸了筆記裡的哪個觀點
- 延伸思考：一句話講可以怎麼用這個呼應（回覆角度、筆記要補什麼）

判斷標準：
- 只列「高相關」：能具體講出貼文跟筆記哪一個觀點互相補充、挑戰或延伸。最多 2 篇。
- 只是主題相近、關鍵字重疊、或要經過好幾步聯想才連得上的，一律不列。
- 筆記內容是空的，或只有標題（例如 Portfolio Log），沒辦法確認呼應點，就不列。
- 沒有任何高相關筆記時，「直接相關筆記（強連結）」這段只寫一行：（無高相關筆記）

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

    def _search_notes(self, sanitized_query: str) -> Optional[dict]:
        """Search brain API with retry (up to 3 attempts)."""
        last_err = None
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{self.base_url}/search",
                    json={
                        "query": sanitized_query,
                        "mode": "hybrid",
                        "limit": self.limit,
                        "include_linked": True,
                        "link_depth": 1,
                    },
                    headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
                    timeout=15,
                )
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.Timeout:
                last_err = f"Timeout after 15s (attempt {attempt + 1}/3)"
                print(f"   [Brain] {last_err}")
            except Exception as e:
                last_err = str(e)
                print(f"   [Brain] Search error: {last_err} (attempt {attempt + 1}/3)")
            if attempt < 2:
                time.sleep(2 ** attempt)
        print(f"   [Brain] Search failed after 3 attempts: {last_err}")
        return None

    def get_note_context(self, post_text: str, call_llm_fn) -> Optional[dict]:
        """
        1. Call POST /search to get related notes
        2. Call LLM to generate rich brain_context analysis
        Returns: {"brain_context": str, "total": int} or None
        """
        if not self.enabled:
            print("   [Brain] Disabled (BRAIN_ENABLED != true)")
            return None
        if not self.base_url or not self.api_key:
            print(
                f"   [Brain] Missing config: url={'SET' if self.base_url else 'MISSING'} "
                f"key={'SET' if self.api_key else 'MISSING'}"
            )
            return None

        # Sanitize query: remove punctuation that may break FTS5 on server
        sanitized = re.sub(r"[.,;:!?\-\—\–\"'`()\[\]{}/\\]", " ", post_text[:500])
        sanitized = re.sub(r"\s+", " ", sanitized).strip()

        # Step 1: Search brain API (with retry)
        data = self._search_notes(sanitized)
        if data is None:
            return None

        results = data.get("results", [])
        if not results:
            print(f"   [Brain] No matching notes for: {post_text[:80]}")
            return None

        print(f"   [Brain] Found {len(results)} notes, generating context...")

        # Step 2: Build notes context and call LLM for analysis
        notes_context = _build_notes_context(results)
        analysis_prompt = BRAIN_ANALYSIS_PROMPT.format(notes_context=notes_context)

        try:
            brain_context = call_llm_fn(
                prompt=analysis_prompt,
                content=post_text[:1000],
                max_tokens=8192,
                timeout=90,
            )
            return {
                "brain_context": brain_context.strip(),
                "total": data.get("total", len(results)),
            }
        except Exception as e:
            print(f"   [Brain] LLM analysis failed: {e}")
            logger.error("[Brain] LLM analysis failed: %s", e)
            return None

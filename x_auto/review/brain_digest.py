"""
Condense a stored brain_context (the Markdown from brain/client.py) for the queue list.

The list shows only what Bill needs to triage a post in seconds (Bill 2026-11-01):
what the post says, and the notes that strongly echo it. Weak links ("弱連結") and the
writing-ideas section are dropped here; the full analysis stays on the detail page.
Works on both the old prompt output (strong + weak + ideas) and the current one.
"""
from __future__ import annotations

import re
from typing import Dict, List

_HEADING = re.compile(r"^#{2,4}\s*(.+?)\s*$")
_NOTE_LINE = re.compile(r"^\*\*\[\[(.+?)\]\][^*]*\*\*")
_FIELD = re.compile(r"^-\s*(連結理由|延伸思考|呼應點|為什麼相關)\s*[:：]\s*(.*)$")
_POINT_MAX = 80
_WHY_MAX = 120
_MAX_LINKS = 2  # same cap the analysis prompt now uses; older analyses list up to 6 "strong" notes


def _clean(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\[\[(.+?)\]\]", r"\1", text)
    return text.strip()


def _first_sentence(text: str, cap: int) -> str:
    first = re.split(r"(?<=[。！？!?])\s*", text, maxsplit=1)[0]
    return first if len(first) <= cap else first[: cap - 1] + "…"


def _short_point(line: str) -> str:
    """Bold lead if the bullet has one, else the first sentence, capped."""
    body = line[2:].strip()
    m = re.match(r"^\*\*(.+?)\*\*", body)
    if m:
        return m.group(1).strip().rstrip("：:")
    return _first_sentence(_clean(body), _POINT_MAX)


def _sections(text: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    current = None
    for raw in text.splitlines():
        m = _HEADING.match(raw.strip())
        if m:
            current = m.group(1)
            out[current] = []
        elif current is not None:
            out[current].append(raw.rstrip())
    return out


def digest(brain_context: str) -> Dict:
    """Return {"points": [...], "links": [{"title", "why", "why_full", "more": [...]}], "extra": int, "analysed": bool}.
    why = first sentence of the reason (the card line); why_full and more go behind an expander."""
    if not brain_context or not brain_context.strip():
        return {"points": [], "links": [], "extra": 0, "analysed": False}

    points: List[str] = []
    links: List[Dict] = []
    for heading, lines in _sections(brain_context).items():
        if "核心重點" in heading or "在講什麼" in heading:
            points = [_short_point(ln.strip()) for ln in lines if ln.startswith("- ")][:3]
        elif "強連結" in heading and "弱" not in heading:
            note = None
            field = None
            for ln in lines:
                s = ln.strip()
                m = _NOTE_LINE.match(s)
                if m:
                    note = {"title": m.group(1).strip(), "why": "", "why_full": "", "more": []}
                    links.append(note)
                    field = None
                    continue
                if note is None or not s:
                    continue
                f = _FIELD.match(s)
                if f:
                    field = f.group(1)
                    value = _clean(f.group(2))
                    if field == "延伸思考":
                        if value:
                            note["more"].append(value)
                    elif not note["why_full"]:
                        note["why_full"] = value
                        note["why"] = _first_sentence(value, _WHY_MAX)
                elif s.startswith("- ") and field == "延伸思考":
                    note["more"].append(_clean(s[2:]))
    return {"points": points, "links": links[:_MAX_LINKS], "extra": max(0, len(links) - _MAX_LINKS),
            "analysed": True}

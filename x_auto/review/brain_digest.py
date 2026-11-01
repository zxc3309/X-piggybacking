"""
Condense a stored brain_context (the Markdown from brain/client.py) for the queue list.

The list shows only what Bill needs to triage a post in seconds (Bill 2026-11-01):
what the post says, and the notes that strongly echo it. Weak links ("弱連結") and the
writing-ideas section are dropped here; the full analysis stays on the detail page.

Analyses written before 2026-11-01 came from a looser prompt (strong + weak links + ideas);
a 2026-11-01 review judged most of their "strong" links medium or low relevance. They are
still parsed, but flagged fresh=False so the list can label them and the high-relevance
filter can leave them out.
"""
from __future__ import annotations

import re
from typing import Dict, List

_HEADING = re.compile(r"^#{2,4}\s*(.+?)\s*$")
# Note title line: "**[[X]]**", "**[[X]] (Readwise)**", "- **[[X]]**", "### [[X]]", "[[X]]"; a title may end in "]".
_NOTE_LINE = re.compile(r"^(?:-\s*)?(?:#{1,4}\s*)?\*{0,2}\[\[(.+?)\]\](?!\])([^*\n]*)\*{0,2}\s*(.*)$")
_FIELD = re.compile(r"^-\s*(連結理由|延伸思考|呼應點|為什麼相關)\s*[:：]\s*(.*)$")
# Reasons that guess at a note the analysis could not read (e.g. "GLX 很可能是 Helix 的產品（名稱縮寫相近）").
_HEDGE = re.compile(r"推測|很可能是|名稱(?:縮寫)?相近|如果.{0,20}(?:有涵蓋|有提到|是你)|只看到標題|無法確認|內容摘要為空")
_POINT_MAX = 80
_SHORT_LEAD = 10
_WHY_FULL_SHOWN = 90
_WHY_MAX = 120
_MAX_LINKS = 2  # same cap the analysis prompt uses


def _clean(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\[\[(.+?)\]\](?!\])", r"\1", text)
    return text.strip()


def _cap(text: str, cap: int) -> str:
    return text if len(text) <= cap else text[: cap - 1] + "…"


def _first_sentence(text: str, cap: int) -> str:
    return _cap(re.split(r"(?<=[。！？!?])\s*", text, maxsplit=1)[0], cap)


def _short_point(line: str) -> str:
    """Bold lead if it carries the claim; a short label ("滲透率極低") keeps the text after it."""
    body = line[2:].strip()
    m = re.match(r"^\*\*(.+?)\*\*\s*[:：]?\s*(.*)$", body)
    if m:
        lead = m.group(1).strip().rstrip("：:")
        rest = _clean(m.group(2))
        if len(lead) > _SHORT_LEAD or not rest:
            return _cap(lead, _POINT_MAX)
        return _first_sentence(lead + "：" + rest, _POINT_MAX)
    return _first_sentence(_clean(body), _POINT_MAX)


def _sections(text: str) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    current = None
    for raw in text.splitlines():
        s = raw.strip()
        m = _HEADING.match(s)
        if m and not _NOTE_LINE.match(s):  # "### [[note]]" is a note, not a section
            current = m.group(1)
            out[current] = []
        elif current is not None:
            out[current].append(raw.rstrip())
    return out


def _finish(note: Dict) -> None:
    why = note["why_full"]
    note["why"] = why if len(why) <= _WHY_FULL_SHOWN else _first_sentence(why, _WHY_MAX)


def _parse_links(lines: List[str]) -> List[Dict]:
    links: List[Dict] = []
    note = None
    field = None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        m = _NOTE_LINE.match(s)
        if m:
            note = {"title": m.group(1).strip(), "why": "", "why_full": "", "more": []}
            links.append(note)
            field = None
            # "**[[X]]** — reason" carries the reason inline; "**[[X]]**（含子卡 …）" is only an annotation
            tail = m.group(3)
            inline = _clean(re.sub(r"^[—–\-:：\s]+", "", tail)) if re.match(r"^[—–\-:：]", tail) else ""
            if inline:
                note["why_full"] = inline
                field = "連結理由"
            continue
        if note is None:
            continue
        f = _FIELD.match(s.replace("**", ""))
        if f:
            field = f.group(1)
            value = _clean(f.group(2))
            if field == "延伸思考":
                if value:
                    note["more"].append(value)
            elif not note["why_full"]:
                note["why_full"] = value
        elif s.startswith("- ") and field == "延伸思考":
            note["more"].append(_clean(s[2:]))
        elif s.startswith("- ") and field and note["why_full"].endswith(("：", ":")):
            # reason that introduces sub-bullets: keep the first one so the line is not left hanging
            note["why_full"] += " " + _clean(s[2:])
    for n in links:
        _finish(n)
    return links


def digest(brain_context: str) -> Dict:
    """Return {"points", "links", "extra", "analysed", "fresh"}.

    links: [{"title", "why", "why_full", "more"}], high-relevance only, at most _MAX_LINKS.
    why = the card line (the whole reason when short, else its first sentence).
    fresh = written by the current high-relevance-only prompt.
    """
    if not brain_context or not brain_context.strip():
        return {"points": [], "links": [], "extra": 0, "analysed": False, "fresh": False}

    fresh = "弱連結" not in brain_context and "💡" not in brain_context
    points: List[str] = []
    links: List[Dict] = []
    for heading, lines in _sections(brain_context).items():
        if "核心重點" in heading or "在講什麼" in heading:
            points = [_short_point(ln.strip()) for ln in lines if ln.strip().startswith("- ")][:3]
        elif "強連結" in heading and "弱" not in heading:
            links = [n for n in _parse_links(lines) if not _HEDGE.search(n["why_full"])]
    return {"points": points, "links": links[:_MAX_LINKS], "extra": max(0, len(links) - _MAX_LINKS),
            "analysed": True, "fresh": fresh}

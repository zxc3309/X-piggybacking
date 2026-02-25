"""
FastAPI web dashboard for reviewing AI-generated X reply candidates.

Endpoints:
    GET  /review              — List all pending replies for review
    GET  /review/{queue_id}   — Detail view for a single reply (edit + approve)
    POST /review/{id}/approve — Approve a reply (with optional edited text)
    POST /review/{id}/reject  — Reject a reply
    POST /review/{id}/save    — Save edits without approving
    GET  /api/stats           — JSON stats (daily quota, status counts)

    JSON API (for AJAX non-blocking UI):
    POST /api/approve/{id}    — Approve via AJAX (returns JSON)
    POST /api/reject/{id}     — Reject via AJAX (returns JSON)
    POST /api/save/{id}       — Save draft via AJAX (returns JSON)
"""

from __future__ import annotations

import os
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from x_auto.review import queue_manager

logger = logging.getLogger(__name__)

app = FastAPI(title="Reply Review Dashboard")

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _prefix(request: Request) -> str:
    """Return the mount prefix (e.g. '/dashboard') so redirects work correctly."""
    return request.scope.get("root_path", "")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Redirect root to the review queue."""
    return RedirectResponse(url=f"{_prefix(request)}/review", status_code=302)


@app.get("/review", response_class=HTMLResponse)
async def review_queue(request: Request, status: Optional[str] = None):
    """Show the review queue list, optionally filtered by status."""
    try:
        if status and status in queue_manager.VALID_STATUSES:
            items = queue_manager.get_items_by_status(status)
        else:
            items = queue_manager.get_all_items()
            status = None

        stats = queue_manager.get_stats()
    except Exception as e:
        logger.error(f"Failed to load review queue: {e}", exc_info=True)
        items = []
        stats = {"pending": 0, "approved": 0, "rejected": 0, "sent": 0, "failed": 0,
                 "total": 0, "daily_sent": 0, "daily_limit": 17}

    return templates.TemplateResponse("queue.html", {
        "request": request,
        "items": items,
        "stats": stats,
        "current_filter": status,
        "prefix": _prefix(request),
    })


@app.get("/review/{queue_id}", response_class=HTMLResponse)
async def review_detail(request: Request, queue_id: str):
    """Show detail view for a single reply candidate."""
    try:
        item = queue_manager.get_item_by_id(queue_id)
    except Exception as e:
        logger.error(f"Failed to load item {queue_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    stats = queue_manager.get_stats()
    # Character count for the reply text
    reply_text = item.get("edited_reply") or item.get("original_reply") or ""
    char_count = len(reply_text)

    return templates.TemplateResponse("review.html", {
        "request": request,
        "item": item,
        "stats": stats,
        "char_count": char_count,
        "prefix": _prefix(request),
    })


# ---------------------------------------------------------------------------
# Scraped Posts
# ---------------------------------------------------------------------------

# Cache for all_post data
_posts_cache: Dict[str, Any] = {"items": None, "timestamp": 0.0}
_POSTS_CACHE_TTL = 60  # seconds


def _load_all_posts() -> List[Dict[str, Any]]:
    """Load all posts from the all_post worksheet with caching."""
    now = time.monotonic()
    if _posts_cache["items"] is not None and (now - _posts_cache["timestamp"]) < _POSTS_CACHE_TTL:
        return _posts_cache["items"]

    from x_auto.sheets.client import GoogleSheetsClient

    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    ws_name = os.getenv("GOOGLE_WS_ALL_POST", "all_post")
    client = GoogleSheetsClient(spreadsheet_name="all_post", spreadsheet_id=sheet_id)
    ws = client.get_sheet(ws_name)
    rows = ws.get_all_values()

    if len(rows) <= 1:
        _posts_cache["items"] = []
        _posts_cache["timestamp"] = now
        return []

    headers = rows[0]
    items = []
    for row in rows[1:]:
        item = {}
        for col_idx, header in enumerate(headers):
            item[header] = row[col_idx] if col_idx < len(row) else ""
        items.append(item)

    _posts_cache["items"] = items
    _posts_cache["timestamp"] = now
    return items


@app.get("/posts", response_class=HTMLResponse)
async def posts_page(request: Request, author: Optional[str] = None):
    """Show all scraped posts, optionally filtered by author."""
    try:
        items = _load_all_posts()
    except Exception as e:
        logger.error(f"Failed to load posts: {e}", exc_info=True)
        items = []

    # Collect unique authors
    authors = sorted(set(item.get("author", "") for item in items if item.get("author")))

    # Filter by author if specified
    if author:
        items = [item for item in items if item.get("author") == author]

    # Calculate stats
    total = len(items)
    matched = sum(1 for item in items if item.get("llm_decision", "").lower() in ("yes", "1"))
    match_rate = round((matched / total * 100), 1) if total > 0 else 0

    return templates.TemplateResponse("posts.html", {
        "request": request,
        "items": items,
        "authors": authors,
        "current_author": author,
        "stats": {"total": total, "matched": matched, "match_rate": match_rate},
        "prefix": _prefix(request),
    })


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@app.post("/review/{queue_id}/approve")
async def approve(request: Request, queue_id: str, edited_reply: str = Form("")):
    """Approve a reply, optionally with edited text."""
    # Validate character count
    reply_text = edited_reply.strip()
    if len(reply_text) > 280:
        raise HTTPException(status_code=400, detail="Reply exceeds 280 characters")

    try:
        success = queue_manager.approve_item(queue_id, edited_reply=reply_text)
    except Exception as e:
        logger.error(f"Failed to approve {queue_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return RedirectResponse(url=f"{_prefix(request)}/review?status=pending", status_code=303)


@app.post("/review/{queue_id}/reject")
async def reject(request: Request, queue_id: str):
    """Reject a reply."""
    try:
        success = queue_manager.reject_item(queue_id)
    except Exception as e:
        logger.error(f"Failed to reject {queue_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return RedirectResponse(url=f"{_prefix(request)}/review?status=pending", status_code=303)


@app.post("/review/{queue_id}/save")
async def save_edit(request: Request, queue_id: str, edited_reply: str = Form("")):
    """Save edits without approving."""
    try:
        success = queue_manager.update_item(queue_id, {"edited_reply": edited_reply.strip()})
    except Exception as e:
        logger.error(f"Failed to save {queue_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return RedirectResponse(url=f"{_prefix(request)}/review/{queue_id}", status_code=303)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.get("/api/stats")
async def api_stats():
    """Return queue statistics as JSON."""
    try:
        return queue_manager.get_stats()
    except Exception as e:
        logger.error(f"Failed to get stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# JSON API for AJAX operations (non-blocking UI updates)
# ---------------------------------------------------------------------------

@app.post("/api/approve/{queue_id}")
async def api_approve(request: Request, queue_id: str):
    """Approve a reply via AJAX, optionally with edited text."""
    try:
        data = await request.json()
    except Exception:
        data = {}

    edited_reply = (data.get("edited_reply") or "").strip()

    # Validate character count
    if len(edited_reply) > 280:
        return JSONResponse(
            {"success": False, "error": "Reply exceeds 280 characters"},
            status_code=400
        )

    try:
        success = queue_manager.approve_item(queue_id, edited_reply=edited_reply)
    except Exception as e:
        logger.error(f"API: Failed to approve {queue_id}: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    if not success:
        return JSONResponse(
            {"success": False, "error": "Item not found"},
            status_code=404
        )

    return JSONResponse({"success": True, "status": "approved"})


@app.post("/api/reject/{queue_id}")
async def api_reject(queue_id: str):
    """Reject a reply via AJAX."""
    try:
        success = queue_manager.reject_item(queue_id)
    except Exception as e:
        logger.error(f"API: Failed to reject {queue_id}: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    if not success:
        return JSONResponse(
            {"success": False, "error": "Item not found"},
            status_code=404
        )

    return JSONResponse({"success": True, "status": "rejected"})


@app.post("/api/save/{queue_id}")
async def api_save(request: Request, queue_id: str):
    """Save edits without approving via AJAX."""
    try:
        data = await request.json()
    except Exception:
        data = {}

    edited_reply = (data.get("edited_reply") or "").strip()

    try:
        success = queue_manager.update_item(queue_id, {"edited_reply": edited_reply})
    except Exception as e:
        logger.error(f"API: Failed to save {queue_id}: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    if not success:
        return JSONResponse(
            {"success": False, "error": "Item not found"},
            status_code=404
        )

    return JSONResponse({"success": True})

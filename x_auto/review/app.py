"""
FastAPI web dashboard for reviewing AI-generated X reply candidates.

Endpoints:
    GET  /review              — List all pending replies for review
    GET  /review/{queue_id}   — Detail view for a single reply (edit + approve)
    POST /review/{id}/approve — Approve a reply (with optional edited text)
    POST /review/{id}/reject  — Reject a reply
    POST /review/{id}/save    — Save edits without approving
    GET  /api/stats           — JSON stats (daily quota, status counts)
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from x_auto.review import queue_manager

logger = logging.getLogger(__name__)

app = FastAPI(title="Reply Review Dashboard")

# Templates directory
TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Redirect root to the review queue."""
    return RedirectResponse(url="/review", status_code=302)


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
    })


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

@app.post("/review/{queue_id}/approve")
async def approve(queue_id: str, edited_reply: str = Form("")):
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

    return RedirectResponse(url="/review?status=pending", status_code=303)


@app.post("/review/{queue_id}/reject")
async def reject(queue_id: str):
    """Reject a reply."""
    try:
        success = queue_manager.reject_item(queue_id)
    except Exception as e:
        logger.error(f"Failed to reject {queue_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return RedirectResponse(url="/review?status=pending", status_code=303)


@app.post("/review/{queue_id}/save")
async def save_edit(queue_id: str, edited_reply: str = Form("")):
    """Save edits without approving."""
    try:
        success = queue_manager.update_item(queue_id, {"edited_reply": edited_reply.strip()})
    except Exception as e:
        logger.error(f"Failed to save {queue_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if not success:
        raise HTTPException(status_code=404, detail="Item not found")

    return RedirectResponse(url=f"/review/{queue_id}", status_code=303)


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

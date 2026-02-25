"""
Manages the reply_queue Google Sheets worksheet for the review workflow.

The reply_queue tracks AI-generated replies through their lifecycle:
pending → approved → sent  (happy path)
pending → rejected          (human rejects)
approved → failed           (X API error)

Each row represents one reply candidate with its review status,
original/edited text, and audit timestamps.
"""

from __future__ import annotations

import os
import re
import uuid
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from x_auto.sheets.client import GoogleSheetsClient

logger = logging.getLogger(__name__)

REPLY_QUEUE_HEADERS = [
    "queue_id",
    "post_id",
    "post_link",
    "author",
    "post_content",
    "original_reply",
    "edited_reply",
    "original_question",  # AI question-style recommendation for engagement
    "status",
    "created_at",
    "approved_at",
    "sent_at",
    "error_message",
    "brain_context",
    "bookmarks",
    "views",
]

VALID_STATUSES = {"pending", "approved", "rejected", "sent", "failed"}

# Simple in-memory cache to avoid repeated Google Sheets API calls
_cache: Dict[str, Any] = {"items": None, "timestamp": 0.0}
_CACHE_TTL = 30  # seconds (increased for better performance)


def _get_ws_name() -> str:
    return os.getenv("GOOGLE_WS_REPLY_QUEUE", "reply_queue")


def _get_client() -> GoogleSheetsClient:
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    return GoogleSheetsClient(spreadsheet_name="reply_queue", spreadsheet_id=sheet_id)


def _ensure_worksheet(client: GoogleSheetsClient, ws_name: str):
    """Get or create the reply_queue worksheet with headers.

    Also performs automatic migration to add any missing columns from
    REPLY_QUEUE_HEADERS to existing sheets.
    """
    try:
        ws = client.get_sheet(ws_name)
    except RuntimeError:
        logger.info(f"Worksheet '{ws_name}' not found, creating it...")
        ws = client.spreadsheet.add_worksheet(title=ws_name, rows=1000, cols=len(REPLY_QUEUE_HEADERS))
        ws.append_row(REPLY_QUEUE_HEADERS, value_input_option="USER_ENTERED")
        logger.info(f"Created worksheet '{ws_name}' with headers")
        return ws

    # Ensure headers exist
    existing = ws.get_all_values()
    if not existing or not any(cell for cell in existing[0]):
        ws.append_row(REPLY_QUEUE_HEADERS, value_input_option="USER_ENTERED")
        return ws

    # Auto-migrate: check for missing columns and remap data
    current_headers = existing[0] if existing else []
    missing = [h for h in REPLY_QUEUE_HEADERS if h not in current_headers]
    if missing:
        logger.info(f"Migrating: adding columns {missing}")
        # Build old header → column index mapping
        old_col_map = {h: i for i, h in enumerate(current_headers)}
        # Remap each data row to the new header order
        new_rows = [REPLY_QUEUE_HEADERS]
        for row in existing[1:]:
            new_row = []
            for h in REPLY_QUEUE_HEADERS:
                if h in old_col_map and old_col_map[h] < len(row):
                    new_row.append(row[old_col_map[h]])
                else:
                    new_row.append("")
            new_rows.append(new_row)
        # Clear sheet and rewrite
        ws.clear()
        ws.update(new_rows, value_input_option="USER_ENTERED")

    return ws


def extract_post_id(post_link: str) -> str:
    """Extract the numeric post ID from an X post URL.

    Handles formats:
        https://x.com/user/status/123456
        https://twitter.com/user/status/123456
        https://x.com/i/web/status/123456
    """
    match = re.search(r"/status/(\d+)", post_link or "")
    return match.group(1) if match else ""


def add_to_queue(items: List[Dict[str, Any]]) -> int:
    """Add matched posts with reply recommendations to the review queue.

    Args:
        items: List of dicts with keys: post_link, author, post_content,
               reply_recommendation, post_id (optional).

    Returns:
        Number of items added (excluding duplicates).
    """
    if not items:
        return 0

    ws_name = _get_ws_name()
    client = _get_client()
    ws = _ensure_worksheet(client, ws_name)

    # Build dedup set from existing post_links (column index 2 = post_link)
    existing = ws.get_all_values()
    existing_links = set()
    for row in existing[1:]:
        if len(row) >= 3:
            existing_links.add(row[2].strip())

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows = []
    for item in items:
        post_link = (item.get("post_link") or "").strip()
        if post_link in existing_links:
            continue

        queue_id = uuid.uuid4().hex[:12]
        post_id = item.get("post_id") or extract_post_id(post_link)
        rows.append([
            queue_id,
            str(post_id),
            post_link,
            item.get("author", ""),
            item.get("post_content", ""),
            item.get("reply_recommendation", ""),
            "",           # edited_reply
            item.get("question_recommendation", ""),  # original_question
            "pending",    # status
            now,          # created_at
            "",           # approved_at
            "",           # sent_at
            "",           # error_message
            item.get("brain_context", ""),  # brain_context
            str(item.get("bookmarks", "")),
            str(item.get("views", "")),
        ])

    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
        logger.info(f"Added {len(rows)} items to reply_queue")
        # Update cache with new items instead of invalidating
        for row in rows:
            new_item = dict(zip(REPLY_QUEUE_HEADERS, row))
            new_item["_row_index"] = len(existing) + rows.index(row) + 1
            _append_to_cache(new_item)

    return len(rows)


def _invalidate_cache():
    """Clear the cache so the next read fetches fresh data."""
    _cache["items"] = None
    _cache["timestamp"] = 0.0


def _update_cache_item(queue_id: str, updates: Dict[str, str]):
    """Update a single item in cache without invalidating.

    This allows instant UI feedback without refetching from Google Sheets.
    """
    if _cache["items"] is None:
        return
    for item in _cache["items"]:
        if item.get("queue_id") == queue_id:
            item.update(updates)
            break


def _append_to_cache(new_item: Dict[str, Any]):
    """Append a new item to the cache without invalidating.

    This allows instant UI feedback after adding items.
    """
    if _cache["items"] is not None:
        _cache["items"].append(new_item)


def get_all_items() -> List[Dict[str, Any]]:
    """Return all items in the reply queue as dicts (cached for 10s)."""
    now = time.monotonic()
    if _cache["items"] is not None and (now - _cache["timestamp"]) < _CACHE_TTL:
        return _cache["items"]

    ws_name = _get_ws_name()
    client = _get_client()
    ws = _ensure_worksheet(client, ws_name)

    rows = ws.get_all_values()
    if len(rows) <= 1:
        _cache["items"] = []
        _cache["timestamp"] = now
        return []

    headers = rows[0]
    items = []
    for row_idx, row in enumerate(rows[1:], start=2):
        item = {}
        for col_idx, header in enumerate(headers):
            item[header] = row[col_idx] if col_idx < len(row) else ""
        item["_row_index"] = row_idx  # 1-based gspread row number
        # Normalize status - invalid statuses default to "pending"
        status = item.get("status", "").strip().lower()
        if status not in VALID_STATUSES:
            if item.get("status"):  # Only log if there was a non-empty invalid status
                logger.warning(f"Invalid status '{item.get('status')}' for queue_id={item.get('queue_id')}, defaulting to 'pending'")
            item["status"] = "pending"
        else:
            item["status"] = status
        items.append(item)

    _cache["items"] = items
    _cache["timestamp"] = now
    return items


def get_items_by_status(status: str) -> List[Dict[str, Any]]:
    """Return items filtered by status."""
    return [item for item in get_all_items() if item.get("status") == status]


def get_item_by_id(queue_id: str) -> Optional[Dict[str, Any]]:
    """Return a single item by queue_id."""
    for item in get_all_items():
        if item.get("queue_id") == queue_id:
            return item
    return None


def _find_column_index(headers: List[str], col_name: str) -> int:
    """Return 1-based column index for a given header name."""
    try:
        return headers.index(col_name) + 1
    except ValueError:
        raise RuntimeError(f"Column '{col_name}' not found in reply_queue headers")


def update_item(queue_id: str, updates: Dict[str, str]) -> bool:
    """Update specific fields of a queue item by queue_id.

    Args:
        queue_id: The unique queue ID.
        updates: Dict of {column_name: new_value} to update.

    Returns:
        True if the item was found and updated.
    """
    ws_name = _get_ws_name()
    client = _get_client()
    ws = _ensure_worksheet(client, ws_name)

    rows = ws.get_all_values()
    if len(rows) <= 1:
        return False

    headers = rows[0]
    queue_id_col = _find_column_index(headers, "queue_id")

    for row_idx, row in enumerate(rows[1:], start=2):
        cell_val = row[queue_id_col - 1] if (queue_id_col - 1) < len(row) else ""
        if cell_val == queue_id:
            cells_to_update = []
            for col_name, value in updates.items():
                col_idx = _find_column_index(headers, col_name)
                cells_to_update.append(
                    gspread_cell(row_idx, col_idx, value)
                )
            if cells_to_update:
                ws.update_cells(cells_to_update, value_input_option="USER_ENTERED")
                # Update cache directly instead of invalidating
                _update_cache_item(queue_id, updates)
            return True
    return False


def gspread_cell(row: int, col: int, value: str):
    """Create a gspread Cell object for batch updates."""
    import gspread
    cell = gspread.Cell(row=row, col=col, value=value)
    return cell


def approve_item(queue_id: str, edited_reply: str = "") -> bool:
    """Mark an item as approved, optionally with an edited reply."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    updates = {"status": "approved", "approved_at": now}
    if edited_reply:
        updates["edited_reply"] = edited_reply
    return update_item(queue_id, updates)


def reject_item(queue_id: str) -> bool:
    """Mark an item as rejected."""
    return update_item(queue_id, {"status": "rejected"})


def mark_sent(queue_id: str) -> bool:
    """Mark an item as sent after successful X API post."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return update_item(queue_id, {"status": "sent", "sent_at": now})


def mark_failed(queue_id: str, error_message: str) -> bool:
    """Mark an item as failed with error details."""
    return update_item(queue_id, {"status": "failed", "error_message": error_message})


def get_daily_sent_count() -> int:
    """Count how many replies were sent today (UTC)."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    items = get_all_items()
    count = 0
    for item in items:
        if item.get("status") == "sent" and item.get("sent_at", "").startswith(today):
            count += 1
    return count


def get_stats() -> Dict[str, int]:
    """Return counts by status and daily sent count."""
    items = get_all_items()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stats = {"pending": 0, "approved": 0, "rejected": 0, "sent": 0, "failed": 0, "total": len(items)}
    daily_sent = 0
    for item in items:
        s = item.get("status", "")
        if s in stats:
            stats[s] += 1
        if s == "sent" and item.get("sent_at", "").startswith(today):
            daily_sent += 1

    stats["daily_sent"] = daily_sent
    stats["daily_limit"] = int(os.getenv("X_DAILY_REPLY_LIMIT", "17"))
    return stats

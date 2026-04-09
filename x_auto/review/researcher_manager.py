"""
Manages the Researcher Google Sheets worksheet for the dashboard.

Provides CRUD operations for the researcher list with in-memory caching
to reduce Google Sheets API calls. Follows the same patterns as queue_manager.py.

The Researcher worksheet is also read by the scraping pipeline (scrape_filter.py)
to get X profile URLs. This module must preserve the existing column structure.
"""

from __future__ import annotations

import os
import logging
import time
from typing import Any, Dict, List, Optional

from x_auto.sheets.client import GoogleSheetsClient

logger = logging.getLogger(__name__)

# In-memory cache (same pattern as queue_manager)
_cache: Dict[str, Any] = {"items": None, "headers": None, "timestamp": 0.0}
_CACHE_TTL = 30  # seconds

# Frontend field names → possible sheet column names (first match wins)
FIELD_TO_COLUMNS = {
    "company": ["Company"],
    "name": ["Name"],
    "role": ["Role"],
    "handle": ["Handle", "handle"],
    "x_link": ["X (link)", "X(link)", "X link"],
    "linkedin": ["LinkedIn (link)", "LinkedIn"],
    "coverage": ["Coverage"],
    "telegram": ["Telegram"],
}

# Display order for frontend
DISPLAY_FIELDS = ["company", "name", "role", "handle", "x_link", "linkedin", "coverage", "telegram"]


def _get_ws_name() -> str:
    return os.getenv("GOOGLE_WS_PROFILES", "Researcher")


def _get_client() -> GoogleSheetsClient:
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    return GoogleSheetsClient(spreadsheet_name="Researcher", spreadsheet_id=sheet_id)


def _resolve_column(field: str, headers: List[str]) -> Optional[str]:
    """Find the actual sheet column name for a frontend field name.

    If the field itself matches a header, use it directly.
    Otherwise check FIELD_TO_COLUMNS aliases.
    """
    if field in headers:
        return field
    for alias in FIELD_TO_COLUMNS.get(field, []):
        if alias in headers:
            return alias
    return None


def _invalidate_cache():
    _cache["items"] = None
    _cache["headers"] = None
    _cache["timestamp"] = 0.0


def _update_cache_item(row_index: int, updates: Dict[str, str]):
    """Update a single item in cache by row index."""
    if _cache["items"] is None:
        return
    for item in _cache["items"]:
        if item.get("_row_index") == row_index:
            item.update(updates)
            break


def _append_to_cache(new_item: Dict[str, Any]):
    """Append a new item to the cache."""
    if _cache["items"] is not None:
        _cache["items"].append(new_item)


def get_all_researchers() -> List[Dict[str, Any]]:
    """Return all researchers as dicts (cached for 30s).

    Each dict uses the actual sheet header names as keys,
    plus _row_index for update targeting.
    """
    now = time.monotonic()
    if _cache["items"] is not None and (now - _cache["timestamp"]) < _CACHE_TTL:
        return _cache["items"]

    ws_name = _get_ws_name()
    client = _get_client()
    ws = client.get_sheet(ws_name)

    rows = ws.get_all_values()
    if len(rows) <= 1:
        _cache["items"] = []
        _cache["headers"] = rows[0] if rows else []
        _cache["timestamp"] = now
        return []

    headers = rows[0]
    _cache["headers"] = headers

    items = []
    for row_idx, row in enumerate(rows[1:], start=2):
        item = {}
        for col_idx, header in enumerate(headers):
            item[header] = row[col_idx] if col_idx < len(row) else ""
        item["_row_index"] = row_idx
        items.append(item)

    _cache["items"] = items
    _cache["timestamp"] = now
    return items


def get_headers() -> List[str]:
    """Return the cached sheet headers (calls get_all_researchers if needed)."""
    if _cache["headers"] is None:
        get_all_researchers()
    return _cache["headers"] or []


def get_researcher_by_row(row_index: int) -> Optional[Dict[str, Any]]:
    """Find a researcher by sheet row index."""
    for item in get_all_researchers():
        if item.get("_row_index") == row_index:
            return item
    return None


def add_researcher(data: Dict[str, str]) -> bool:
    """Append a new researcher row to the worksheet.

    Args:
        data: Dict with frontend field names (company, name, role, handle, x_link, etc.)

    Returns:
        True on success.
    """
    ws_name = _get_ws_name()
    client = _get_client()
    ws = client.get_sheet(ws_name)

    # Read current headers
    all_values = ws.get_all_values()
    if not all_values:
        logger.error("Researcher worksheet is empty (no headers)")
        return False

    headers = all_values[0]

    # Build row matching header order
    row = []
    for header in headers:
        # Find matching frontend field for this header
        value = ""
        for field, aliases in FIELD_TO_COLUMNS.items():
            if header in aliases or header.lower() == field:
                value = data.get(field, "")
                break
        row.append(value)

    ws.append_row(row, value_input_option="USER_ENTERED")
    logger.info(f"Added researcher: {data.get('name', '?')} ({data.get('handle', '?')})")

    # Update cache
    new_item = dict(zip(headers, row))
    new_item["_row_index"] = len(all_values) + 1
    _append_to_cache(new_item)

    return True


def update_researcher(row_index: int, updates: Dict[str, str]) -> bool:
    """Update specific fields of a researcher by row index.

    Args:
        row_index: 1-based gspread row number.
        updates: Dict with frontend field names as keys.

    Returns:
        True if found and updated.
    """
    import gspread

    ws_name = _get_ws_name()
    client = _get_client()
    ws = client.get_sheet(ws_name)

    rows = ws.get_all_values()
    if len(rows) <= 1 or row_index < 2 or row_index > len(rows):
        return False

    headers = rows[0]

    cells_to_update = []
    resolved_updates = {}
    for field, value in updates.items():
        col_name = _resolve_column(field, headers)
        if col_name is None:
            logger.warning(f"Cannot resolve field '{field}' to any sheet column")
            continue
        col_idx = headers.index(col_name) + 1  # 1-based
        cells_to_update.append(gspread.Cell(row=row_index, col=col_idx, value=value))
        resolved_updates[col_name] = value

    if not cells_to_update:
        return False

    ws.update_cells(cells_to_update, value_input_option="USER_ENTERED")
    _update_cache_item(row_index, resolved_updates)
    logger.info(f"Updated researcher at row {row_index}: {list(resolved_updates.keys())}")
    return True


def get_stats() -> Dict[str, Any]:
    """Return total count and count by company."""
    items = get_all_researchers()
    companies: Dict[str, int] = {}
    for item in items:
        company = item.get("Company", "").strip() or "Unknown"
        companies[company] = companies.get(company, 0) + 1

    return {
        "total": len(items),
        "companies": companies,
    }

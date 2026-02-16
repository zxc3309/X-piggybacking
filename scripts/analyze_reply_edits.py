#!/usr/bin/env python3
"""
Analyze Reply Edits — Compare AI-generated replies vs user-edited versions.

Use this to understand how users modify AI replies, which informs reply_prompt iteration.

Usage:
    python scripts/analyze_reply_edits.py           # Show all edits
    python scripts/analyze_reply_edits.py --summary  # Summary stats only
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv()

from x_auto.sheets.client import GoogleSheetsClient


def load_reply_queue():
    """Load all items from reply_queue worksheet."""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("❌ GOOGLE_SHEET_ID not set")
        sys.exit(1)

    client = GoogleSheetsClient(spreadsheet_name="X-piggybacking", spreadsheet_id=sheet_id)
    ws_name = os.getenv("GOOGLE_WS_REPLY_QUEUE", "reply_queue")

    try:
        ws = client.get_sheet(ws_name)
    except RuntimeError:
        print(f"❌ Worksheet '{ws_name}' not found")
        sys.exit(1)

    rows = ws.get_all_values()
    if len(rows) <= 1:
        return []

    headers = rows[0]
    items = []
    for row in rows[1:]:
        items.append(dict(zip(headers, row)))
    return items


def find_edited_replies(items):
    """Find items where the user edited the AI reply."""
    edited = []
    for item in items:
        original = (item.get("original_reply") or "").strip()
        user_edit = (item.get("edited_reply") or "").strip()
        status = item.get("status", "")

        if user_edit and user_edit != original:
            edited.append({
                "author": item.get("author", ""),
                "post_content": item.get("post_content", ""),
                "post_link": item.get("post_link", ""),
                "original_reply": original,
                "edited_reply": user_edit,
                "status": status,
                "approved_at": item.get("approved_at", ""),
            })
    return edited


def main():
    parser = argparse.ArgumentParser(description="Analyze reply edits for prompt iteration")
    parser.add_argument("--summary", action="store_true", help="Show summary stats only")
    args = parser.parse_args()

    print("🔌 Connecting to Google Sheets...")
    items = load_reply_queue()
    print(f"✓ Loaded {len(items)} items from reply_queue\n")

    if not items:
        print("No items in reply_queue yet.")
        return

    # Stats
    total = len(items)
    by_status = {}
    for item in items:
        s = item.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1

    edited = find_edited_replies(items)
    approved = [i for i in items if i.get("status") in ("approved", "sent")]
    approved_without_edit = [i for i in approved
                            if not (i.get("edited_reply") or "").strip()
                            or (i.get("edited_reply") or "").strip() == (i.get("original_reply") or "").strip()]

    print("=" * 70)
    print("REPLY QUEUE SUMMARY")
    print("=" * 70)
    print(f"Total items:           {total}")
    for status, count in sorted(by_status.items()):
        print(f"  {status:20s} {count}")
    print(f"\nApproved/Sent total:   {len(approved)}")
    print(f"  Without edits:       {len(approved_without_edit)}")
    print(f"  With edits:          {len(edited)}")
    if approved:
        edit_rate = len(edited) / len(approved) * 100
        print(f"  Edit rate:           {edit_rate:.0f}%")

    if args.summary:
        return

    if not edited:
        print("\n📭 No edited replies yet.")
        print("   When you edit replies in the dashboard, they'll appear here.")
        return

    print("\n" + "=" * 70)
    print("EDITED REPLIES (AI original → User edit)")
    print("=" * 70)

    for i, edit in enumerate(edited, 1):
        print(f"\n[Edit #{i}] @{edit['author']}")
        print(f"Post: {edit['post_content'][:100]}...")
        if edit['post_link']:
            print(f"Link: {edit['post_link']}")
        print(f"\n  AI ORIGINAL:")
        print(f"  {edit['original_reply']}")
        print(f"\n  USER EDITED:")
        print(f"  {edit['edited_reply']}")
        print("-" * 70)

    # Identify patterns
    print("\n" + "=" * 70)
    print("EDIT PATTERNS (for reply_prompt iteration)")
    print("=" * 70)

    shorter = sum(1 for e in edited if len(e['edited_reply']) < len(e['original_reply']))
    longer = sum(1 for e in edited if len(e['edited_reply']) > len(e['original_reply']))
    same_len = len(edited) - shorter - longer

    print(f"Made shorter:  {shorter}/{len(edited)}")
    print(f"Made longer:   {longer}/{len(edited)}")
    print(f"Similar length: {same_len}/{len(edited)}")

    if edited:
        avg_original = sum(len(e['original_reply']) for e in edited) / len(edited)
        avg_edited = sum(len(e['edited_reply']) for e in edited) / len(edited)
        print(f"\nAvg AI length:   {avg_original:.0f} chars")
        print(f"Avg edit length: {avg_edited:.0f} chars")


if __name__ == "__main__":
    main()

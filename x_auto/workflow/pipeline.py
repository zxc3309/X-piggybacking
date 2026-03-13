"""
High-level automation pipeline:
(1) fetch posts → (2) keyword match → (3) score → (4) generate reply
→ (5) route to human review.

This module wires together the major components while leaving detailed
utilities (ID tracking, logging formatting, human approval) as stubs.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from x_auto.scrapers.apify_client import fetch_posts

from x_auto.matcher.keyword_matcher import match_keywords, score_matches
from x_auto.reply_engine.reply_generator import build_reply_text, select_best_template
from x_auto.sheets.client import GoogleSheetsClient


def run_pipeline() -> None:
    """
    Execute the end-to-end workflow using Sheets data, Apify scraper, and X API.

    Steps:
        1) Load profile handles and keyword/template rows from Google Sheets.
        2) Fetch recent posts for each handle via Apify.
        3) Filter out posts that have already been processed (placeholder utility).
        4) Perform keyword matching and compute scores.
        5) Choose the best template and generate a reply (delegated to reply_engine).
        6) Route to human review (replies are posted manually via X Intent URL).

    Note:
        This function focuses on orchestration; several utilities are intentionally
        left as stubs for future implementation.
    """
    # Use unified GOOGLE_SHEET_ID with fallback to legacy env vars
    sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_X_ACCOUNT_ID")
    spreadsheet_name = os.getenv("GOOGLE_SPREADSHEET_NAME", "Automation Config")
    sheet_client = GoogleSheetsClient(spreadsheet_name=spreadsheet_name, spreadsheet_id=sheet_id)

    profile_rows = sheet_client.read_records("profiles")
    keyword_rows = sheet_client.read_records("keywords")
    template_rows = sheet_client.read_records("templates")

    for profile in profile_rows:
        profile_url = profile.get("profile_url") or profile.get("x_profile_url") or ""
        if not profile_url:
            continue

        raw_posts = fetch_posts([profile_url], results_limit=20)
        new_posts = filter_already_processed(raw_posts)

        for post in new_posts:
            text = post.get("text", "")
            matches = match_keywords(text, keyword_rows)
            score = score_matches(matches, post_metadata=post)

            template = select_best_template(matches, template_rows)
            reply_text = build_reply_text(template, post, matches)

            if requires_human_approval(post, reply_text):
                # Route to human review via Dashboard (manual reply via X Intent URL).
                continue


# Placeholder utilities with docstrings for future implementation ----------------

def filter_already_processed(
    posts: List[Dict[str, Any]],
    sheet_client: GoogleSheetsClient | None = None,
    output_sheet_name: str | None = None
) -> List[Dict[str, Any]]:
    """
    Filter out posts that have already been processed by checking the output sheet.

    Args:
        posts: Raw posts returned by Apify.
        sheet_client: Optional GoogleSheetsClient instance. If None, creates a new one.
        output_sheet_name: Optional worksheet name. If None, uses GOOGLE_WS_SCRAPED_OUTPUT.

    Returns:
        A filtered list containing only new/unprocessed posts.
    """
    if not posts:
        return []

    # Get or create sheet client (新版整合 + 向後相容)
    if sheet_client is None:
        output_sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_X_SCRAPE_OUTPUT")
        if not output_sheet_id:
            # If no output sheet configured, return all posts (no filtering)
            return posts
        sheet_client = GoogleSheetsClient(
            spreadsheet_name="Scrape Output",
            spreadsheet_id=output_sheet_id
        )

    # Get worksheet name (新版整合 + 向後相容)
    if output_sheet_name is None:
        output_sheet_name = os.getenv("GOOGLE_WS_SCRAPED_OUTPUT") or os.getenv("GOOGLE_X_SCRAPE_OUTPUT_WORKSHEET", "scraped_output")

    # Fetch existing post IDs from the output sheet
    try:
        existing_records = sheet_client.read_records(output_sheet_name)
        existing_post_ids = {record.get("post_id", "") for record in existing_records if record.get("post_id")}
    except Exception:
        # If sheet doesn't exist or is empty, assume no posts have been processed
        existing_post_ids = set()

    # Filter posts
    new_posts = [post for post in posts if post.get("id", "") not in existing_post_ids]

    return new_posts


def format_log_row(post: Dict[str, Any], reply_text: str, response: Dict[str, Any]) -> List[Any]:
    """
    Placeholder for transforming an interaction into a log row for Sheets.

    Args:
        post: The source post dictionary.
        reply_text: Text sent to X.
        response: API response from X after posting.

    Returns:
        A sequence of values suitable for appending to a Google Sheet row.
    """
    raise NotImplementedError("Implement log formatting for Google Sheets.")


def requires_human_approval(post: Dict[str, Any], reply_text: str) -> bool:
    """
    Placeholder for deciding whether a reply should be routed to human approval.

    Args:
        post: The source post dictionary.
        reply_text: Generated reply text.

    Returns:
        True if human approval is required, otherwise False.
    """
    raise NotImplementedError("Implement human approval decision logic.")

"""
Google Sheets client utilities using gspread and service account credentials.

This module encapsulates authentication and basic worksheet operations:
fetching worksheets, reading rows as dictionaries, and appending new rows.

Example:
    >>> client = GoogleSheetsClient(spreadsheet_name="Automation Config")
    >>> rows = client.read_records("profiles")
    >>> client.append_row("logs", ["post_id", "status", "timestamp"])
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

import gspread
from google.oauth2.service_account import Credentials

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsClient:
    """
    Lightweight wrapper around gspread for interacting with a target spreadsheet.

    Purpose:
        Provide authenticated access to a Google Sheet for reading structured data
        and appending new rows used in the automation pipeline.

    API behavior:
        - Authenticates using a service account JSON file located at the path in
          environment variable GOOGLE_SERVICE_ACCOUNT_PATH.
        - Opens the spreadsheet by ID (GOOGLE_SPREADSHEET_ID) when set, otherwise
          by the provided spreadsheet name.
        - Exposes helper methods for fetching worksheets, reading records, and
          appending rows with type hints for clarity.

    Example usage:
        client = GoogleSheetsClient(spreadsheet_name="Automation Config")
        profiles = client.read_records("profiles")
        client.append_row("logs", ["post_id", "sent", "2024-01-01T00:00:00Z"])

    Note:
        The reference sheet for this project contains X profile URLs in column E
        (worksheet "profiles") of spreadsheet
        `1gr9wMTJTDEFlsqGF8nSMJ4fXyBjNP2RvTdVyWvmuG00`.
    """

    def __init__(self, spreadsheet_name: str, spreadsheet_id: str | None = None):
        # Option 1: Base64 environment variable (Railway/cloud deployment)
        creds_base64 = os.getenv("GOOGLE_SHEETS_CREDENTIALS_BASE64")

        if creds_base64:
            import base64
            import json
            creds_json = base64.b64decode(creds_base64).decode('utf-8')
            creds_dict = json.loads(creds_json)
            credentials = Credentials.from_service_account_info(
                creds_dict,
                scopes=DEFAULT_SCOPES
            )
        else:
            # Option 2: File path (local development)
            service_account_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH")
            if not service_account_path:
                raise RuntimeError(
                    "Either GOOGLE_SHEETS_CREDENTIALS_BASE64 or "
                    "GOOGLE_SERVICE_ACCOUNT_PATH is required but both are missing."
                )

            credentials_path = Path(service_account_path)
            if not credentials_path.is_file():
                raise RuntimeError(f"Service account file not found at {credentials_path}")

            credentials = Credentials.from_service_account_file(
                str(credentials_path),
                scopes=DEFAULT_SCOPES,
            )

        client = gspread.authorize(credentials)

        # Support unified GOOGLE_SHEET_ID (new) with fallback to GOOGLE_X_ACCOUNT_ID (legacy)
        env_spreadsheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_X_ACCOUNT_ID")
        spreadsheet_id = spreadsheet_id or env_spreadsheet_id

        # Check for placeholder values
        PLACEHOLDER_VALUES = [
            'your_google_sheet_id_here',
            'your_sheet_id',
            'REPLACE_WITH_YOUR_SHEET_ID',
        ]

        if spreadsheet_id and spreadsheet_id in PLACEHOLDER_VALUES:
            raise RuntimeError(
                f"❌ GOOGLE_SHEET_ID is set to a placeholder value: '{spreadsheet_id}'\n"
                f"\n"
                f"Please set the actual Google Sheet ID:\n"
                f"  1. Local: Update GOOGLE_SHEET_ID in your .env file\n"
                f"  2. Railway: Set GOOGLE_SHEET_ID in Railway Dashboard → Variables\n"
                f"\n"
                f"To find your Sheet ID:\n"
                f"  - Open your Google Sheet in browser\n"
                f"  - Copy the ID from URL: https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit\n"
                f"\n"
                f"Example: GOOGLE_SHEET_ID=1iXtgaweAlKHITZ_XRCmwIkSfar5YXKzK89ZTdppIlxA"
            )

        try:
            if spreadsheet_id:
                self.spreadsheet = client.open_by_key(spreadsheet_id)
            else:
                self.spreadsheet = client.open(spreadsheet_name)
        except gspread.SpreadsheetNotFound as exc:
            error_msg = (
                f"❌ Spreadsheet not found:\n"
                f"  Name: '{spreadsheet_name}'\n"
                f"  ID: '{spreadsheet_id or 'unset'}'\n"
                f"\n"
                f"Possible causes:\n"
                f"  1. Sheet ID is incorrect or not set\n"
                f"  2. Sheet not shared with service account:\n"
                f"     piggybacking@social-media-tracker-467416.iam.gserviceaccount.com\n"
                f"  3. Service account credentials are invalid\n"
                f"\n"
                f"To fix:\n"
                f"  - Verify GOOGLE_SHEET_ID in your environment\n"
                f"  - Share the Google Sheet with the service account email (Editor permission)\n"
                f"  - Check GOOGLE_SHEETS_CREDENTIALS_BASE64 is correctly set (Railway)\n"
                f"    or GOOGLE_SERVICE_ACCOUNT_PATH points to valid JSON (local)"
            )
            raise RuntimeError(error_msg) from exc

    def get_sheet(self, sheet_name: str) -> Any:
        """
        Retrieve a worksheet by name.

        Args:
            sheet_name: Name of the worksheet to fetch.

        Returns:
            A gspread Worksheet instance.

        Raises:
            RuntimeError: If the worksheet cannot be located.
        """
        try:
            return self.spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound as exc:
            raise RuntimeError(f"Worksheet '{sheet_name}' not found.") from exc

    def read_records(self, sheet_name: str) -> List[Dict[str, Any]]:
        """
        Read all rows from a worksheet as a list of dictionaries.

        Args:
            sheet_name: Name of the worksheet to read.

        Returns:
            A list where each element represents a row keyed by column header.

        Raises:
            RuntimeError: If the worksheet cannot be located.
        """
        worksheet = self.get_sheet(sheet_name)
        return worksheet.get_all_records()

    def append_row(self, sheet_name: str, row: List[Any]) -> None:
        """
        Append a row to the end of a worksheet.

        Args:
            sheet_name: Name of the worksheet to write to.
            row: Sequence of values to append as a new row.

        Returns:
            None. The operation writes data to the sheet.

        Raises:
            RuntimeError: If the worksheet cannot be located.
        """
        worksheet = self.get_sheet(sheet_name)
        worksheet.append_row(row, value_input_option="USER_ENTERED")


def write_rows_below(worksheet: gspread.Worksheet, rows: List[List[Any]], existing_count: int) -> int:
    """
    Write rows starting at an explicit row number, right below the rows just read.

    Worksheet.append_row(s) lets Sheets guess where the table ends. On 2026-11-02 that
    guess put a new Researcher row on top of an existing one (row 32 was overwritten), so
    writes that add records go to row existing_count + 1 instead, and refuse to run if
    those rows are no longer empty (someone added a row since the read).

    Returns:
        The 1-based row number of the first written row.
    """
    start = existing_count + 1
    end = existing_count + len(rows)
    if end > worksheet.row_count:
        worksheet.add_rows(end - worksheet.row_count)
    elif any(any(cell for cell in r) for r in worksheet.get(f"A{start}:{gspread.utils.rowcol_to_a1(end, worksheet.col_count)}")):
        raise RuntimeError(f"Rows {start}-{end} of '{worksheet.title}' are not empty; re-read before writing")
    worksheet.update(f"A{start}", rows, value_input_option="USER_ENTERED")
    return start


# Backward-compatible placeholders for higher-level workflow stubs.
def get_sheet_client(spreadsheet_name: str) -> GoogleSheetsClient:
    """
    Convenience wrapper to instantiate a GoogleSheetsClient.
    """
    return GoogleSheetsClient(spreadsheet_name=spreadsheet_name)


def read_profiles(sheet_client: GoogleSheetsClient, sheet_name: str) -> List[Dict[str, Any]]:
    """
    Placeholder for reading profile definitions; to be implemented with project-specific parsing.
    """
    raise NotImplementedError("Profile reading is not yet implemented.")


def log_interaction(sheet_client: GoogleSheetsClient, sheet_name: str, record: Dict[str, Any]) -> None:
    """
    Placeholder for logging interactions; to be implemented with project-specific parsing.
    """
    raise NotImplementedError("Logging interactions is not yet implemented.")


def write_review_queue(sheet_client: GoogleSheetsClient, sheet_name: str, rows: List[Dict[str, Any]]) -> None:
    """
    Placeholder for writing review queue entries; to be implemented with project-specific parsing.
    """
    raise NotImplementedError("Review queue writing is not yet implemented.")


def write_scraped_posts(
    sheet_client: GoogleSheetsClient,
    sheet_name: str,
    posts: List[Dict[str, Any]],
    ensure_headers: bool = True
) -> int:
    """
    Write scraped posts to a Google Sheet with proper column formatting.

    Args:
        sheet_client: Authenticated GoogleSheetsClient instance.
        sheet_name: Name of the worksheet to write to.
        posts: List of post dictionaries from Apify scraper.
        ensure_headers: If True, adds headers if the sheet is empty.

    Returns:
        Number of posts written to the sheet.

    Raises:
        RuntimeError: If the worksheet cannot be accessed.

    Column structure:
        post_id, author_username, author_name, text, created_at,
        url, likes, retweets, replies, views, scraped_at
    """
    if not posts:
        return 0

    worksheet = sheet_client.get_sheet(sheet_name)

    # Check if we need to add headers
    if ensure_headers:
        try:
            existing_data = worksheet.get_all_values()
            if not existing_data or not existing_data[0]:
                # Sheet is empty, add headers
                headers = [
                    "post_id", "author_username", "author_name", "text",
                    "created_at", "url", "likes", "retweets", "replies",
                    "views", "scraped_at"
                ]
                worksheet.append_row(headers, value_input_option="USER_ENTERED")
        except Exception as e:
            raise RuntimeError(f"Failed to check/add headers: {e}")

    # Prepare rows from posts
    from datetime import datetime
    scraped_at = datetime.now().isoformat()

    rows_to_add = []
    for post in posts:
        author = post.get("author", {})
        row = [
            post.get("id", ""),
            author.get("userName", ""),
            author.get("name", ""),
            post.get("text", ""),
            post.get("createdAt", ""),
            post.get("url", ""),
            post.get("likes", 0),
            post.get("retweetCount", 0),
            post.get("replyCount", 0),
            post.get("viewCount", 0),
            scraped_at
        ]
        rows_to_add.append(row)

    # Batch write all rows
    if rows_to_add:
        try:
            worksheet.append_rows(rows_to_add, value_input_option="USER_ENTERED")
        except Exception as e:
            raise RuntimeError(f"Failed to write posts to sheet: {e}")

    return len(rows_to_add)

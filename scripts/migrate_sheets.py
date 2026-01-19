#!/usr/bin/env python3
"""
Google Sheets Schema Migration Script

This script migrates the X-piggybacking Google Sheets to support
the feedback loop system for prompt iteration.

Changes:
1. Extends all_post worksheet from 15 columns (A-O) to 21 columns (A-U)
   - P: user_decision (0/1)
   - Q: user_comment (text)
   - R: feedback_timestamp
   - S: feedback_source ("telegram", "sheets", "both")
   - T: feedback_status ("pending", "reviewed", "resolved")
   - U: prompt_version (e.g., "v1.0", "v1.1")

2. Creates new prompt_history worksheet for tracking prompt versions
   - Columns: version_id, created_at, created_by, prompt_name, prompt_text,
     status, notes, total_evaluated, accuracy, false_positive_rate,
     false_negative_rate, avg_user_agreement, last_updated

3. Migrates current prompt from prompt_inuse to prompt_history as v1.0

Usage:
    python scripts/migrate_sheets.py                # Dry run (preview changes)
    python scripts/migrate_sheets.py --execute      # Execute migration
    python scripts/migrate_sheets.py --backup       # Backup before execute
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from x_auto.sheets.client import GoogleSheetsClient

# Load environment variables
load_dotenv()


def get_all_post_worksheet_name() -> str:
    """Get the all_post worksheet name from environment."""
    return os.getenv("GOOGLE_WS_ALL_POST") or os.getenv("GOOGLE_X_TESTING_WORKSHEET", "all_post")


def get_prompts_worksheet_name() -> str:
    """Get the prompts worksheet name from environment."""
    return os.getenv("GOOGLE_WS_PROMPTS") or os.getenv("GOOGLE_X_PROMPTS_WORKSHEET", "prompt_inuse")


def migrate_all_post_columns(sheet_client: GoogleSheetsClient, dry_run: bool = True) -> None:
    """
    Extend all_post worksheet to include feedback columns (P-U).
    Also renames existing P/Q columns if they have old headers.

    Args:
        sheet_client: Authenticated GoogleSheetsClient
        dry_run: If True, only preview changes without executing
    """
    print("\n" + "="*70)
    print("MIGRATION STEP 1: Extend all_post worksheet columns")
    print("="*70)

    worksheet_name = get_all_post_worksheet_name()
    print(f"Target worksheet: '{worksheet_name}'")

    try:
        worksheet = sheet_client.get_sheet(worksheet_name)
    except RuntimeError as e:
        print(f"❌ Error: Worksheet '{worksheet_name}' not found")
        print(f"   {e}")
        return

    # Get current headers
    current_headers = worksheet.row_values(1)
    current_col_count = len(current_headers)

    print(f"\nCurrent columns: {current_col_count}")
    print(f"Current headers (P-Q): {current_headers[15:17] if len(current_headers) > 16 else 'N/A'}")

    # Define expected headers (A-U, 21 columns)
    expected_headers = [
        "scraped_at",           # A
        "profile_url",          # B
        "author",               # C
        "post_content",         # D
        "timestamp",            # E
        "likes",                # F
        "reposts",              # G
        "replies",              # H
        "bookmarks",            # I
        "views",                # J
        "llm_decision",         # K
        "llm_reason",           # L
        "prompt_used",          # M
        "reply_recommendation", # N
        "post_link",            # O
        "user_decision",        # P - user's manual decision 0/1
        "user_comment",         # Q - user's feedback comment
        "feedback_timestamp",   # R - when feedback was given
        "feedback_source",      # S - "telegram", "sheets", "both"
        "feedback_status",      # T - "pending", "reviewed", "resolved"
        "prompt_version",       # U - which prompt version was used
    ]

    # Check if we need to rename P/Q columns
    rename_needed = []
    if current_col_count >= 16:
        if current_headers[15] != "user_decision":
            rename_needed.append(("P", current_headers[15], "user_decision"))
    if current_col_count >= 17:
        if current_headers[16] != "user_comment":
            rename_needed.append(("Q", current_headers[16], "user_comment"))

    # Determine what new columns need to be added
    new_headers = expected_headers[current_col_count:] if current_col_count < 21 else []

    if not rename_needed and not new_headers:
        print("\n✓ all_post worksheet already has all required columns with correct headers")
        return

    print(f"\n📝 Changes to be made:")

    if rename_needed:
        print(f"   Renaming existing columns:")
        for col, old, new in rename_needed:
            print(f"   - Column {col}: '{old}' → '{new}'")

    if new_headers:
        print(f"   Adding {len(new_headers)} new columns:")
        for i, header in enumerate(new_headers, start=current_col_count + 1):
            col_letter = chr(ord('A') + i - 1)  # Convert to column letter
            print(f"   - Column {col_letter}: {header}")

    if dry_run:
        print("\n⚠️  DRY RUN - No changes made")
        print("   Run with --execute to apply changes")
        return

    # Execute migration
    print("\n🔧 Executing migration...")

    try:
        # Step 1: Rename existing columns P/Q if needed
        if rename_needed:
            for col, old, new in rename_needed:
                col_index = ord(col) - ord('A') + 1
                worksheet.update_cell(1, col_index, new)
                print(f"✓ Renamed column {col}: '{old}' → '{new}'")

        # Step 2: Add new column headers
        if new_headers:
            col_start = current_col_count + 1
            worksheet.update(
                f"{chr(ord('A') + col_start - 1)}1",
                [new_headers],
                value_input_option="USER_ENTERED"
            )
            print(f"✓ Added {len(new_headers)} column headers")

        print("✓ Migration complete!")

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        raise


def create_prompt_history_worksheet(sheet_client: GoogleSheetsClient, dry_run: bool = True) -> None:
    """
    Create prompt_history worksheet for tracking prompt versions.

    Args:
        sheet_client: Authenticated GoogleSheetsClient
        dry_run: If True, only preview changes without executing
    """
    print("\n" + "="*70)
    print("MIGRATION STEP 2: Create prompt_history worksheet")
    print("="*70)

    worksheet_name = "prompt_history"

    # Check if worksheet already exists
    try:
        worksheet = sheet_client.get_sheet(worksheet_name)
        print(f"✓ Worksheet '{worksheet_name}' already exists")
        return
    except RuntimeError:
        print(f"📝 Worksheet '{worksheet_name}' does not exist")

    # Define headers for prompt_history
    headers = [
        "version_id",              # A: e.g., "v1.0", "v1.1"
        "created_at",              # B: timestamp
        "created_by",              # C: user identifier (default "manual")
        "prompt_name",             # D: "match_prompt", "reply_prompt", etc.
        "prompt_text",             # E: full prompt content
        "status",                  # F: "active", "testing", "archived"
        "notes",                   # G: user's notes on changes
        "total_evaluated",         # H: count of posts evaluated
        "accuracy",                # I: matching decisions / total
        "false_positive_rate",     # J: FP / total
        "false_negative_rate",     # K: FN / total
        "avg_user_agreement",      # L: percentage agreement
        "last_updated",            # M: last metric calculation
    ]

    print(f"\n📝 Changes to be made:")
    print(f"   Creating worksheet with {len(headers)} columns:")
    for i, header in enumerate(headers, start=1):
        print(f"   - Column {chr(ord('A') + i - 1)}: {header}")

    if dry_run:
        print("\n⚠️  DRY RUN - No changes made")
        print("   Run with --execute to apply changes")
        return

    # Execute creation
    print("\n🔧 Creating worksheet...")

    try:
        # Create new worksheet
        worksheet = sheet_client.spreadsheet.add_worksheet(
            title=worksheet_name,
            rows=1000,  # Start with 1000 rows
            cols=len(headers)
        )
        print(f"✓ Created worksheet '{worksheet_name}'")

        # Add headers
        worksheet.update('A1', [headers], value_input_option="USER_ENTERED")
        print(f"✓ Added {len(headers)} column headers")

        print("✓ Creation complete!")

    except Exception as e:
        print(f"❌ Error during creation: {e}")
        raise


def migrate_current_prompt(sheet_client: GoogleSheetsClient, dry_run: bool = True) -> None:
    """
    Migrate current match_prompt from prompt_inuse to prompt_history as v1.0.

    The prompt_inuse worksheet uses horizontal layout:
    - Row 1: [match_prompt, reply_prompt, summary_prompt, category_prompt]
    - Row 2: [match_prompt_text, reply_prompt_text, ...]

    Args:
        sheet_client: Authenticated GoogleSheetsClient
        dry_run: If True, only preview changes without executing
    """
    print("\n" + "="*70)
    print("MIGRATION STEP 3: Migrate current prompt to prompt_history")
    print("="*70)

    prompts_ws_name = get_prompts_worksheet_name()
    history_ws_name = "prompt_history"

    print(f"Source worksheet: '{prompts_ws_name}'")
    print(f"Target worksheet: '{history_ws_name}'")

    # Read current prompt (horizontal layout)
    try:
        prompts_ws = sheet_client.get_sheet(prompts_ws_name)
        all_values = prompts_ws.get_all_values()

        if len(all_values) < 2:
            print(f"⚠️  Warning: '{prompts_ws_name}' doesn't have enough rows")
            print("   Skipping prompt migration")
            return

        # Row 1 is headers (prompt names), Row 2 is values (prompt texts)
        headers = all_values[0]
        values = all_values[1]

        # Find match_prompt column
        match_prompt = None
        try:
            match_prompt_index = headers.index('match_prompt')
            match_prompt = values[match_prompt_index].strip()
        except (ValueError, IndexError):
            print(f"⚠️  Warning: 'match_prompt' column not found in '{prompts_ws_name}'")
            print(f"   Available columns: {headers}")
            print("   Skipping prompt migration")
            return

        if not match_prompt:
            print(f"⚠️  Warning: 'match_prompt' value is empty")
            print("   Skipping prompt migration")
            return

        print(f"\n✓ Found match_prompt in '{prompts_ws_name}'")
        print(f"   Prompt preview: {match_prompt[:100]}...")

    except Exception as e:
        print(f"❌ Error reading prompts: {e}")
        return

    # Check if already migrated
    try:
        history_ws = sheet_client.get_sheet(history_ws_name)
        existing_records = history_ws.get_all_records()

        for row in existing_records:
            if row.get("version_id") == "v1.0" and row.get("prompt_name") == "match_prompt":
                print(f"\n✓ Prompt already migrated as v1.0")
                return

    except RuntimeError:
        print(f"⚠️  Warning: '{history_ws_name}' worksheet not found")
        print("   Run STEP 2 first to create the worksheet")
        return

    # Prepare migration row
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    migration_row = [
        "v1.0",              # version_id
        now,                 # created_at
        "migration",         # created_by
        "match_prompt",      # prompt_name
        match_prompt,        # prompt_text
        "active",            # status
        "Initial version migrated from prompt_inuse",  # notes
        "",                  # total_evaluated (empty, will be calculated)
        "",                  # accuracy
        "",                  # false_positive_rate
        "",                  # false_negative_rate
        "",                  # avg_user_agreement
        "",                  # last_updated
    ]

    print(f"\n📝 Changes to be made:")
    print(f"   Adding v1.0 entry to prompt_history:")
    print(f"   - Version: v1.0")
    print(f"   - Status: active")
    print(f"   - Created: {now}")

    if dry_run:
        print("\n⚠️  DRY RUN - No changes made")
        print("   Run with --execute to apply changes")
        return

    # Execute migration
    print("\n🔧 Migrating prompt...")

    try:
        history_ws.append_row(migration_row, value_input_option="USER_ENTERED")
        print(f"✓ Added match_prompt v1.0 to prompt_history")
        print("✓ Migration complete!")

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        raise


def backup_sheets(sheet_client: GoogleSheetsClient) -> None:
    """
    Create a backup by duplicating the spreadsheet.

    Note: This requires the service account to have appropriate permissions.
    Alternatively, users can manually duplicate the sheet before running migration.

    Args:
        sheet_client: Authenticated GoogleSheetsClient
    """
    print("\n" + "="*70)
    print("BACKUP: Duplicating spreadsheet")
    print("="*70)

    print("\n⚠️  Automatic backup via API is not implemented yet.")
    print("   Please manually duplicate your Google Sheet before proceeding:")
    print("\n   1. Open your Google Sheet")
    print("   2. File → Make a copy")
    print("   3. Name it: 'X-piggybacking Backup {date}'")
    print("\n   Then run this script again with --execute")

    sys.exit(0)


def main():
    """Main migration script entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Migrate Google Sheets schema for feedback loop system"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute migration (default is dry run)"
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Prompt to create backup before migration"
    )
    args = parser.parse_args()

    dry_run = not args.execute

    print("="*70)
    print("GOOGLE SHEETS SCHEMA MIGRATION")
    print("="*70)
    print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'EXECUTE (will make changes)'}")

    if args.backup:
        # In a real implementation, we'd use Google Drive API to duplicate
        # For now, just prompt the user
        response = input("\n⚠️  Have you created a backup of your Google Sheet? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("\n❌ Aborted. Please create a backup first.")
            sys.exit(1)

    # Initialize Google Sheets client
    try:
        print("\n🔌 Connecting to Google Sheets...")
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if not sheet_id:
            print("❌ Error: GOOGLE_SHEET_ID not set in environment")
            sys.exit(1)

        sheet_client = GoogleSheetsClient(
            spreadsheet_name="X-piggybacking",
            spreadsheet_id=sheet_id
        )
        print(f"✓ Connected to spreadsheet: {sheet_client.spreadsheet.title}")

    except Exception as e:
        print(f"❌ Error connecting to Google Sheets: {e}")
        sys.exit(1)

    # Run migration steps
    try:
        # Step 1: Extend all_post columns
        migrate_all_post_columns(sheet_client, dry_run=dry_run)

        # Step 2: Create prompt_history worksheet
        create_prompt_history_worksheet(sheet_client, dry_run=dry_run)

        # Step 3: Migrate current prompt to v1.0
        migrate_current_prompt(sheet_client, dry_run=dry_run)

        # Summary
        print("\n" + "="*70)
        print("MIGRATION SUMMARY")
        print("="*70)

        if dry_run:
            print("\n✓ Dry run complete - no changes made")
            print("\nTo execute migration, run:")
            print("  python scripts/migrate_sheets.py --execute")
        else:
            print("\n✓ Migration complete!")
            print("\nNext steps:")
            print("  1. Verify changes in Google Sheets")
            print("  2. Update scrape_filter.py to write 21 columns")
            print("  3. Test with a scrape run")

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

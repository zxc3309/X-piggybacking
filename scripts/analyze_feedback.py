#!/usr/bin/env python3
"""
Feedback Analysis CLI Tool

Analyzes user feedback on LLM decisions to identify patterns and calculate metrics.

Usage:
    python scripts/analyze_feedback.py                    # Analyze all feedback
    python scripts/analyze_feedback.py --version v1.0     # Analyze specific prompt version
    python scripts/analyze_feedback.py --export console   # Export to console (default)
    python scripts/analyze_feedback.py --disagreements    # Show only disagreements
    python scripts/analyze_feedback.py --fp               # Show only false positives
    python scripts/analyze_feedback.py --fn               # Show only false negatives
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from x_auto.sheets.client import GoogleSheetsClient
from x_auto.feedback.analyzer import FeedbackAnalyzer

# Load environment variables
load_dotenv()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze user feedback on LLM match decisions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate full analysis report
  python scripts/analyze_feedback.py

  # Analyze specific prompt version
  python scripts/analyze_feedback.py --version v1.0

  # Show only false positives
  python scripts/analyze_feedback.py --fp

  # Show only false negatives
  python scripts/analyze_feedback.py --fn

  # Show all disagreements
  python scripts/analyze_feedback.py --disagreements
        """
    )

    parser.add_argument(
        "--version",
        type=str,
        help="Filter by specific prompt version (e.g., 'v1.0', 'v1.1')"
    )

    parser.add_argument(
        "--export",
        type=str,
        choices=["console", "markdown"],
        default="console",
        help="Export format (default: console)"
    )

    parser.add_argument(
        "--disagreements",
        action="store_true",
        help="Show only posts where LLM and user disagree"
    )

    parser.add_argument(
        "--fp",
        action="store_true",
        help="Show only false positives (LLM accept, user reject)"
    )

    parser.add_argument(
        "--fn",
        action="store_true",
        help="Show only false negatives (LLM reject, user accept)"
    )

    args = parser.parse_args()

    # Initialize Google Sheets client
    try:
        print("🔌 Connecting to Google Sheets...")
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

    # Initialize analyzer
    analyzer = FeedbackAnalyzer(sheet_client)

    try:
        # Load data
        print("📊 Loading feedback data...")
        data = analyzer.load_data()
        print(f"✓ Loaded {len(data)} posts with user feedback\n")

        if len(data) == 0:
            print("⚠️  No posts with user feedback found.")
            print("\nTo analyze feedback, you need posts with:")
            print("  - Column K (llm_decision): 0 or 1")
            print("  - Column P (user_decision): 0 or 1")
            print("\nPlease add your feedback to the all_post worksheet.")
            sys.exit(0)

        # Handle specific views
        if args.fp:
            print("🔴 FALSE POSITIVES (LLM Accept, User Reject)")
            print("=" * 70)
            fps = analyzer.find_disagreements("false_positive")
            if fps:
                for i, record in enumerate(fps, 1):
                    print(f"\n[FP #{i}] @{record.get('author', 'unknown')}")
                    print(f"Post: {record.get('post_content', '')[:150]}...")
                    print(f"LLM Reason: {record.get('llm_reason', 'N/A')}")
                    if record.get('user_comment'):
                        print(f"Your Comment: {record.get('user_comment')}")
                    print(f"Link: {record.get('post_link', 'N/A')}")
                    print("-" * 70)
                print(f"\nTotal false positives: {len(fps)}")
            else:
                print("✓ No false positives found!")
            sys.exit(0)

        if args.fn:
            print("🟡 FALSE NEGATIVES (LLM Reject, User Accept)")
            print("=" * 70)
            fns = analyzer.find_disagreements("false_negative")
            if fns:
                for i, record in enumerate(fns, 1):
                    print(f"\n[FN #{i}] @{record.get('author', 'unknown')}")
                    print(f"Post: {record.get('post_content', '')[:150]}...")
                    print(f"LLM Reason: {record.get('llm_reason', 'N/A')}")
                    if record.get('user_comment'):
                        print(f"Your Comment: {record.get('user_comment')}")
                    print(f"Link: {record.get('post_link', 'N/A')}")
                    print("-" * 70)
                print(f"\nTotal false negatives: {len(fns)}")
            else:
                print("✓ No false negatives found!")
            sys.exit(0)

        if args.disagreements:
            print("⚠️  ALL DISAGREEMENTS (LLM ≠ User)")
            print("=" * 70)
            disagreements = analyzer.find_disagreements()
            if disagreements:
                for i, record in enumerate(disagreements, 1):
                    dis_type = record.get('disagreement_type', 'unknown')
                    icon = "🔴" if dis_type == "false_positive" else "🟡"
                    print(f"\n{icon} [{dis_type.upper()} #{i}] @{record.get('author', 'unknown')}")
                    print(f"Post: {record.get('post_content', '')[:150]}...")
                    print(f"LLM: {'✅ ACCEPT' if record['llm_decision_normalized'] == 1 else '❌ REJECT'} - {record.get('llm_reason', 'N/A')}")
                    print(f"You: {'✅ ACCEPT' if record['user_decision_normalized'] == 1 else '❌ REJECT'} - {record.get('user_comment', 'N/A')}")
                    print(f"Link: {record.get('post_link', 'N/A')}")
                    print("-" * 70)
                print(f"\nTotal disagreements: {len(disagreements)}")
            else:
                print("✓ No disagreements found! LLM and user agree 100%")
            sys.exit(0)

        # Generate full report
        print("Generating analysis report...\n")
        report = analyzer.generate_report(format=args.export)
        print(report)

    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

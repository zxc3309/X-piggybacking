#!/usr/bin/env python3
"""
Interactive Prompt Update Tool

Helps you create, test, and activate new prompt versions based on feedback analysis.

Usage:
    python scripts/update_prompt.py match_prompt           # Interactive update
    python scripts/update_prompt.py --show-current         # Show current prompt
    python scripts/update_prompt.py --activate v1.1        # Activate a version
    python scripts/update_prompt.py --compare v1.0 v1.1    # Compare versions
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from x_auto.sheets.client import GoogleSheetsClient
from x_auto.feedback.prompt_manager import PromptManager
from x_auto.feedback.analyzer import FeedbackAnalyzer
from x_auto.feedback.prompt_tester import display_test_comparison

# Load environment variables
load_dotenv()


def show_current_prompt(manager: PromptManager, prompt_name: str = "match_prompt"):
    """Display current prompt and its performance."""
    print("=" * 70)
    print(f"CURRENT PROMPT: {prompt_name}")
    print("=" * 70)

    current_version = manager.get_current_version(prompt_name)
    current_text = manager.get_current_prompt_text(prompt_name)

    if current_version:
        print(f"Version: {current_version}")
    else:
        print("Version: Unknown (no prompt_history entry)")

    print("\nPrompt Text:")
    print("-" * 70)
    if current_text:
        print(current_text)
    else:
        print("(Could not retrieve prompt text)")
    print("-" * 70)


def show_recent_performance(analyzer: FeedbackAnalyzer):
    """Show recent performance metrics."""
    print("\n" + "=" * 70)
    print("RECENT PERFORMANCE (last 7 days)")
    print("=" * 70)

    metrics = analyzer.calculate_metrics()

    if metrics.get("error"):
        print(f"⚠️  {metrics['error']}")
        return

    print(f"Total Posts Evaluated: {metrics['total_posts']}")
    print(f"Accuracy: {metrics['accuracy']:.1%}")
    print(f"False Positive Rate: {metrics['false_positive_rate']:.1%}", end="")
    if metrics['false_positive_rate'] > 0.15:
        print(" ⚠ High")
    else:
        print(" ✓")
    print(f"False Negative Rate: {metrics['false_negative_rate']:.1%}", end="")
    if metrics['false_negative_rate'] > 0.15:
        print(" ⚠ High")
    else:
        print(" ✓")


def interactive_update(manager: PromptManager, analyzer: FeedbackAnalyzer, prompt_name: str = "match_prompt"):
    """Interactive prompt update workflow."""
    print("\n" + "=" * 70)
    print(f"INTERACTIVE PROMPT UPDATE - {prompt_name}")
    print("=" * 70)

    # Show current state
    show_current_prompt(manager, prompt_name)
    show_recent_performance(analyzer)

    # Show key insights
    print("\n" + "=" * 70)
    print("KEY INSIGHTS FROM FEEDBACK ANALYSIS")
    print("=" * 70)

    patterns = analyzer.identify_patterns()

    if patterns['false_positive_count'] > 0:
        print(f"\n🔴 False Positives: {patterns['false_positive_count']} cases")
        print("   Common issues:")
        disagreements = analyzer.find_disagreements("false_positive")

        # Show sample user comments
        comments = [d.get('user_comment', '') for d in disagreements if d.get('user_comment')]
        if comments:
            for comment in comments[:3]:
                print(f"   • \"{comment}\"")

    if patterns['false_negative_count'] > 0:
        print(f"\n🟡 False Negatives: {patterns['false_negative_count']} cases")

    # Menu
    print("\n" + "=" * 70)
    print("WHAT WOULD YOU LIKE TO DO?")
    print("=" * 70)
    print("[1] Edit prompt (opens in editor)")
    print("[2] View recent disagreements")
    print("[3] Cancel")

    choice = input("\nChoice (1-3): ").strip()

    if choice == "2":
        # Show disagreements
        print("\n" + "=" * 70)
        print("RECENT DISAGREEMENTS")
        print("=" * 70)

        disagreements = analyzer.find_disagreements()
        for i, record in enumerate(disagreements[:10], 1):
            dis_type = record.get('disagreement_type', 'unknown')
            icon = "🔴" if dis_type == "false_positive" else "🟡"
            print(f"\n{icon} [{dis_type.upper()} #{i}]")
            print(f"Post: {record.get('post_content', '')[:100]}...")
            print(f"LLM: {'ACCEPT' if record['llm_decision_normalized'] == 1 else 'REJECT'} - {record.get('llm_reason', '')[:80]}")
            print(f"You: {'ACCEPT' if record['user_decision_normalized'] == 1 else 'REJECT'} - {record.get('user_comment', 'N/A')}")

        print("\n" + "-" * 70)
        input("Press Enter to return to menu...")
        return interactive_update(manager, analyzer, prompt_name)

    elif choice == "1":
        # Edit prompt
        current_text = manager.get_current_prompt_text(prompt_name)

        if not current_text:
            print("\n❌ Could not retrieve current prompt text")
            return

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as tf:
            tf.write(current_text)
            temp_path = tf.name

        # Open in editor
        editor = os.environ.get('EDITOR', 'nano')
        print(f"\nOpening prompt in {editor}...")
        print("(Edit the prompt, save, and exit the editor)")

        try:
            subprocess.call([editor, temp_path])
        except Exception as e:
            print(f"❌ Error opening editor: {e}")
            print("Please set EDITOR environment variable (e.g., export EDITOR=nano)")
            os.unlink(temp_path)
            return

        # Read edited content
        with open(temp_path, 'r') as f:
            new_text = f.read().strip()

        os.unlink(temp_path)

        if new_text == current_text:
            print("\n⚠️  No changes detected")
            return

        # Show diff preview
        print("\n" + "=" * 70)
        print("NEW PROMPT PREVIEW")
        print("=" * 70)
        print(new_text[:200] + "..." if len(new_text) > 200 else new_text)
        print("=" * 70)

        # Confirm save
        save = input("\nSave this new prompt? (yes/no): ").strip().lower()
        if save not in ['yes', 'y']:
            print("❌ Cancelled")
            return

        # Get notes
        notes = input("Notes about changes (optional): ").strip()
        if not notes:
            notes = "Updated based on feedback analysis"

        # Create new version
        print("\n🔧 Creating new prompt version...")
        new_version = manager.create_new_version(prompt_name, new_text, notes)
        print(f"✓ Created {new_version} (status: testing)")

        # AUTO-TEST: Test the new version on past feedback posts
        print("\n" + "=" * 70)
        print("TESTING NEW VERSION ON PAST FEEDBACK")
        print("=" * 70)

        test_result = manager.test_and_save_metrics(
            new_version,
            new_text,
            prompt_name,
            auto_save=True,
            verbose=True
        )

        if test_result.get("error"):
            print(f"\n⚠️  {test_result['error']}")
            print("Cannot compare versions without test results.")
            print(f"\n{new_version} created but not activated.")
            print(f"To activate later: python scripts/update_prompt.py --activate {new_version}")
            return

        # Display test results
        metrics = test_result['metrics']
        test_results = test_result['test_results']
        print(f"\n✓ Test complete: {metrics['total_with_feedback']} posts evaluated")

        # Get previous version for comparison
        prev_version = manager.get_previous_version(prompt_name)
        current_version = manager.get_current_version(prompt_name)

        # Use current active version if no archived version
        compare_version = prev_version or current_version
        if compare_version and compare_version != new_version:
            prev_metrics = manager.get_version_metrics(compare_version, prompt_name)
            if prev_metrics:
                display_test_comparison(compare_version, prev_metrics, new_version, metrics)

        # Show fixed false positives if any
        fixed_fps = test_results.get('fixed_fps', [])
        if fixed_fps:
            print(f"\n✅ Fixed {len(fixed_fps)} false positives!")

        # Show new false negatives if any
        new_fns = test_results.get('new_fns', [])
        if new_fns:
            print(f"\n⚠️  Introduced {len(new_fns)} new false negatives")

        # Ask about activation (with test results visible)
        print("\n" + "=" * 70)
        print("ACTIVATION DECISION")
        print("=" * 70)
        print(f"[1] Activate {new_version} now (will be used in next scrape)")
        print(f"[2] Keep as 'testing' (don't activate yet)")

        activate_choice = input("\nChoice (1-2): ").strip()

        if activate_choice == "1":
            print(f"\n🔧 Activating {new_version}...")
            manager.activate_version(new_version, prompt_name)
            print(f"\n✅ SUCCESS! {new_version} is now active")
            print(f"   Next scrape will use the updated prompt")
        else:
            print(f"\n✓ {new_version} kept as 'testing'")
            print(f"   Metrics already saved to prompt_history")
            print(f"   To activate later: python scripts/update_prompt.py --activate {new_version}")

    elif choice == "3":
        print("\n❌ Cancelled")
        return
    else:
        print("\n❌ Invalid choice")
        return


def activate_version_cmd(manager: PromptManager, version_id: str, prompt_name: str = "match_prompt"):
    """Activate a specific version."""
    print(f"\n🔧 Activating {version_id} for {prompt_name}...")

    try:
        manager.activate_version(version_id, prompt_name)
        print(f"\n✅ SUCCESS! {version_id} is now active")
        print(f"   Next scrape will use this prompt version")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


def compare_versions_cmd(manager: PromptManager, version_a: str, version_b: str, prompt_name: str = "match_prompt"):
    """Compare two versions."""
    print(f"\n📊 Comparing {version_a} vs {version_b}")
    print("=" * 70)

    result = manager.compare_versions(version_a, version_b, prompt_name)

    if result.get("error"):
        print(f"❌ {result['error']}")
        sys.exit(1)

    # Display comparison
    v_a = result["version_a"]
    v_b = result["version_b"]

    print(f"\n{version_a}:")
    print(f"  Status: {v_a.get('status')}")
    print(f"  Created: {v_a.get('created_at')}")
    print(f"  Accuracy: {v_a.get('accuracy') or 'N/A'}")
    print(f"  FP Rate: {v_a.get('false_positive_rate') or 'N/A'}")

    print(f"\n{version_b}:")
    print(f"  Status: {v_b.get('status')}")
    print(f"  Created: {v_b.get('created_at')}")
    print(f"  Accuracy: {v_b.get('accuracy') or 'N/A'}")
    print(f"  FP Rate: {v_b.get('false_positive_rate') or 'N/A'}")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Interactive prompt update and version management tool",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        "prompt_name",
        nargs="?",
        default="match_prompt",
        help="Name of prompt to update (default: match_prompt)"
    )

    parser.add_argument(
        "--show-current",
        action="store_true",
        help="Show current prompt and exit"
    )

    parser.add_argument(
        "--activate",
        type=str,
        metavar="VERSION",
        help="Activate a specific version (e.g., 'v1.1')"
    )

    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("VERSION_A", "VERSION_B"),
        help="Compare two versions"
    )

    args = parser.parse_args()

    # Initialize clients
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

    manager = PromptManager(sheet_client)
    analyzer = FeedbackAnalyzer(sheet_client)

    # Handle commands
    if args.show_current:
        show_current_prompt(manager, args.prompt_name)
        show_recent_performance(analyzer)

    elif args.activate:
        activate_version_cmd(manager, args.activate, args.prompt_name)

    elif args.compare:
        compare_versions_cmd(manager, args.compare[0], args.compare[1], args.prompt_name)

    else:
        # Interactive mode
        interactive_update(manager, analyzer, args.prompt_name)


if __name__ == "__main__":
    main()

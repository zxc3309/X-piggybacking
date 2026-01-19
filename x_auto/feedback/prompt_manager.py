"""
Prompt Management Module

Manages prompt versions, testing, and activation for iterative improvement.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone

from x_auto.sheets.client import GoogleSheetsClient
from x_auto.feedback.analyzer import FeedbackAnalyzer


class PromptManager:
    """
    Manages prompt versions and performance tracking.

    Handles creating new versions, testing on past posts, comparing performance,
    and activating new prompts.
    """

    def __init__(self, sheet_client: GoogleSheetsClient):
        """
        Initialize prompt manager.

        Args:
            sheet_client: Authenticated GoogleSheetsClient instance
        """
        self.sheet_client = sheet_client
        self.prompts_ws_name = os.getenv("GOOGLE_WS_PROMPTS", "prompt_inuse")
        self.history_ws_name = "prompt_history"

    def get_current_version(self, prompt_name: str = "match_prompt") -> Optional[str]:
        """
        Get the active prompt version ID.

        Args:
            prompt_name: Name of prompt (default: "match_prompt")

        Returns:
            Version ID (e.g., "v1.0") or None if not found
        """
        try:
            history_ws = self.sheet_client.get_sheet(self.history_ws_name)
            records = history_ws.get_all_records()

            for record in records:
                if (record.get("prompt_name") == prompt_name and
                    record.get("status") == "active"):
                    return record.get("version_id")

            return None
        except Exception as e:
            print(f"Warning: Could not get current version: {e}")
            return None

    def get_current_prompt_text(self, prompt_name: str = "match_prompt") -> Optional[str]:
        """
        Get the current active prompt text from prompt_inuse worksheet.

        Args:
            prompt_name: Name of prompt (default: "match_prompt")

        Returns:
            Prompt text or None if not found
        """
        try:
            prompts_ws = self.sheet_client.get_sheet(self.prompts_ws_name)
            all_values = prompts_ws.get_all_values()

            if len(all_values) < 2:
                return None

            # Horizontal layout: row 1 = headers, row 2 = values
            headers = all_values[0]
            values = all_values[1]

            try:
                prompt_index = headers.index(prompt_name)
                return values[prompt_index].strip()
            except (ValueError, IndexError):
                return None

        except Exception as e:
            print(f"Warning: Could not get current prompt text: {e}")
            return None

    def create_new_version(
        self,
        prompt_name: str,
        prompt_text: str,
        notes: str = ""
    ) -> str:
        """
        Create new prompt version in prompt_history.

        Does NOT activate it yet (status="testing").

        Args:
            prompt_name: Name of prompt (e.g., "match_prompt")
            prompt_text: Full prompt content
            notes: User's notes on changes made

        Returns:
            New version ID (e.g., "v1.1")
        """
        # Get next version number
        current_version = self.get_current_version(prompt_name)
        if current_version:
            # Parse version number (e.g., "v1.0" -> 1.0)
            try:
                version_num = float(current_version.replace("v", ""))
                new_version_num = version_num + 0.1
                new_version_id = f"v{new_version_num:.1f}"
            except ValueError:
                new_version_id = "v1.1"
        else:
            new_version_id = "v1.1"

        # Create new record
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        new_record = [
            new_version_id,              # version_id
            now,                          # created_at
            "manual",                     # created_by
            prompt_name,                  # prompt_name
            prompt_text,                  # prompt_text
            "testing",                    # status
            notes,                        # notes
            "",                           # total_evaluated (empty initially)
            "",                           # accuracy
            "",                           # false_positive_rate
            "",                           # false_negative_rate
            "",                           # avg_user_agreement
            "",                           # last_updated
        ]

        # Append to prompt_history
        history_ws = self.sheet_client.get_sheet(self.history_ws_name)
        history_ws.append_row(new_record, value_input_option="USER_ENTERED")

        return new_version_id

    def test_prompt_on_past_posts(
        self,
        version_id: str,
        sample_size: int = 50,
        prompt_name: str = "match_prompt"
    ) -> Dict[str, Any]:
        """
        Re-evaluate past posts with a new prompt version.

        Does NOT write results to all_post (test mode only).
        Compares new prompt's decisions vs user decisions.

        Args:
            version_id: Version to test (e.g., "v1.1")
            sample_size: Number of posts to test (default: 50)
            prompt_name: Name of prompt to test

        Returns:
            Dict with test results and metrics
        """
        # Get the prompt text for this version
        history_ws = self.sheet_client.get_sheet(self.history_ws_name)
        records = history_ws.get_all_records()

        prompt_text = None
        for record in records:
            if (record.get("version_id") == version_id and
                record.get("prompt_name") == prompt_name):
                prompt_text = record.get("prompt_text")
                break

        if not prompt_text:
            return {"error": f"Prompt version {version_id} not found"}

        # Load posts with user feedback
        analyzer = FeedbackAnalyzer(self.sheet_client)
        data = analyzer.load_data()

        if not data:
            return {"error": "No posts with user feedback found"}

        # Sample posts
        import random
        if len(data) > sample_size:
            test_posts = random.sample(data, sample_size)
        else:
            test_posts = data

        # Re-evaluate each post with new prompt
        # NOTE: This would require calling the LLM API
        # For now, return a placeholder structure
        return {
            "version_id": version_id,
            "prompt_text_preview": prompt_text[:100] + "...",
            "total_tested": len(test_posts),
            "note": "LLM re-evaluation not implemented yet - use manual testing",
            "test_posts_sample": [
                {
                    "post_content": p.get("post_content", "")[:100],
                    "user_decision": p.get("user_decision"),
                    "original_llm_decision": p.get("llm_decision"),
                }
                for p in test_posts[:5]
            ]
        }

    def test_and_save_metrics(
        self,
        version_id: str,
        prompt_text: str,
        prompt_name: str = "match_prompt",
        auto_save: bool = True,
        verbose: bool = True
    ) -> Dict[str, Any]:
        """
        Test a prompt version on past feedback posts and save metrics.

        This is the integrated testing function that:
        1. Loads posts with user feedback
        2. Tests the new prompt on each post (calls LLM)
        3. Calculates metrics (accuracy, FP rate, FN rate)
        4. Optionally saves metrics to prompt_history

        Args:
            version_id: Version to test (e.g., "v1.2")
            prompt_text: The prompt text to test
            prompt_name: Name of prompt
            auto_save: Automatically save metrics to prompt_history
            verbose: Print progress during testing

        Returns:
            Dict with test results and metrics
        """
        from x_auto.feedback.prompt_tester import test_prompt_on_feedback_posts

        # Load posts with user feedback
        analyzer = FeedbackAnalyzer(self.sheet_client)
        posts = analyzer.load_data()

        if not posts or len(posts) < 5:
            return {"error": "Not enough feedback posts for testing (need at least 5)"}

        # Run test
        test_results = test_prompt_on_feedback_posts(
            prompt_text, posts, version_id, verbose=verbose
        )

        if test_results.get("error"):
            return test_results

        # Convert to metrics format for saving
        metrics = {
            "total_with_feedback": test_results['total_tested'],
            "accuracy": test_results['accuracy'],
            "false_positive_rate": test_results['fp_rate'],
            "false_negative_rate": test_results['fn_rate'],
            "user_agreement_rate": test_results['accuracy'],
        }

        # Auto-save if requested
        if auto_save:
            self.update_version_metrics(version_id, metrics, prompt_name)
            if verbose:
                print(f"✓ Metrics saved to prompt_history for {version_id}")

        return {
            "metrics": metrics,
            "test_results": test_results
        }

    def get_version_metrics(self, version_id: str, prompt_name: str = "match_prompt") -> Dict[str, Any]:
        """
        Get metrics for a specific version from prompt_history.

        Args:
            version_id: Version to get metrics for
            prompt_name: Name of prompt

        Returns:
            Dict with accuracy, false_positive_rate, false_negative_rate
        """
        history_ws = self.sheet_client.get_sheet(self.history_ws_name)
        records = history_ws.get_all_records()

        for record in records:
            if (record.get("version_id") == version_id and
                record.get("prompt_name") == prompt_name):
                return {
                    "accuracy": record.get("accuracy"),
                    "false_positive_rate": record.get("false_positive_rate"),
                    "false_negative_rate": record.get("false_negative_rate"),
                    "total_evaluated": record.get("total_evaluated"),
                    "status": record.get("status"),
                }
        return {}

    def get_previous_version(self, prompt_name: str = "match_prompt") -> Optional[str]:
        """
        Get the most recently archived version (previous active).

        Args:
            prompt_name: Name of prompt

        Returns:
            Version ID of the archived version, or None
        """
        history_ws = self.sheet_client.get_sheet(self.history_ws_name)
        records = history_ws.get_all_records()

        # Find archived versions, return the most recent one
        archived_versions = []
        for record in records:
            if (record.get("prompt_name") == prompt_name and
                record.get("status") == "archived"):
                archived_versions.append(record)

        if archived_versions:
            # Return the last one (most recently archived)
            return archived_versions[-1].get("version_id")
        return None

    def activate_version(self, version_id: str, prompt_name: str = "match_prompt") -> None:
        """
        Activate a prompt version.

        Updates:
        1. prompt_history: Set specified version status to "active"
        2. prompt_history: Archive previous active version
        3. prompt_inuse: Update with new prompt text

        Args:
            version_id: Version to activate (e.g., "v1.1")
            prompt_name: Name of prompt to activate
        """
        history_ws = self.sheet_client.get_sheet(self.history_ws_name)
        records = history_ws.get_all_records()

        # Find the version to activate
        activate_row = None
        activate_prompt_text = None
        for i, record in enumerate(records, start=2):  # Start at 2 (row 1 is header)
            if (record.get("version_id") == version_id and
                record.get("prompt_name") == prompt_name):
                activate_row = i
                activate_prompt_text = record.get("prompt_text")
                break

        if not activate_row or not activate_prompt_text:
            raise ValueError(f"Version {version_id} for {prompt_name} not found")

        # Step 1: Archive previous active version
        for i, record in enumerate(records, start=2):
            if (record.get("prompt_name") == prompt_name and
                record.get("status") == "active"):
                # Set status to "archived"
                status_col = 6  # Column F (status)
                history_ws.update_cell(i, status_col, "archived")
                print(f"✓ Archived previous active version: {record.get('version_id')}")

        # Step 2: Set new version to active
        status_col = 6  # Column F (status)
        history_ws.update_cell(activate_row, status_col, "active")
        print(f"✓ Set {version_id} status to 'active'")

        # Step 3: Update prompt_inuse worksheet
        prompts_ws = self.sheet_client.get_sheet(self.prompts_ws_name)
        all_values = prompts_ws.get_all_values()

        if len(all_values) < 2:
            raise ValueError(f"prompt_inuse worksheet is empty or malformed")

        # Horizontal layout: row 1 = headers, row 2 = values
        headers = all_values[0]
        try:
            prompt_col = headers.index(prompt_name) + 1  # Convert to 1-indexed
            prompts_ws.update_cell(2, prompt_col, activate_prompt_text)
            print(f"✓ Updated {self.prompts_ws_name} with new prompt text")
        except ValueError:
            raise ValueError(f"Prompt '{prompt_name}' not found in {self.prompts_ws_name}")

    def compare_versions(
        self,
        version_a: str,
        version_b: str,
        prompt_name: str = "match_prompt"
    ) -> Dict[str, Any]:
        """
        Compare metrics between two prompt versions.

        Args:
            version_a: First version ID (e.g., "v1.0")
            version_b: Second version ID (e.g., "v1.1")
            prompt_name: Name of prompt to compare

        Returns:
            Dict with comparison data
        """
        history_ws = self.sheet_client.get_sheet(self.history_ws_name)
        records = history_ws.get_all_records()

        # Find both versions
        version_a_data = None
        version_b_data = None

        for record in records:
            if (record.get("version_id") == version_a and
                record.get("prompt_name") == prompt_name):
                version_a_data = record
            if (record.get("version_id") == version_b and
                record.get("prompt_name") == prompt_name):
                version_b_data = record

        if not version_a_data:
            return {"error": f"Version {version_a} not found"}
        if not version_b_data:
            return {"error": f"Version {version_b} not found"}

        # Calculate metrics for both if available
        # For now, return structure
        return {
            "version_a": {
                "version_id": version_a,
                "status": version_a_data.get("status"),
                "created_at": version_a_data.get("created_at"),
                "accuracy": version_a_data.get("accuracy"),
                "false_positive_rate": version_a_data.get("false_positive_rate"),
            },
            "version_b": {
                "version_id": version_b,
                "status": version_b_data.get("status"),
                "created_at": version_b_data.get("created_at"),
                "accuracy": version_b_data.get("accuracy"),
                "false_positive_rate": version_b_data.get("false_positive_rate"),
            }
        }

    def update_version_metrics(
        self,
        version_id: str,
        metrics: Dict[str, Any],
        prompt_name: str = "match_prompt"
    ) -> None:
        """
        Update performance metrics for a prompt version.

        Args:
            version_id: Version to update
            metrics: Dict with accuracy, false_positive_rate, etc.
            prompt_name: Name of prompt
        """
        history_ws = self.sheet_client.get_sheet(self.history_ws_name)
        records = history_ws.get_all_records()

        # Find the version row
        target_row = None
        for i, record in enumerate(records, start=2):  # Start at 2 (row 1 is header)
            if (record.get("version_id") == version_id and
                record.get("prompt_name") == prompt_name):
                target_row = i
                break

        if not target_row:
            raise ValueError(f"Version {version_id} not found")

        # Update metrics columns
        # Columns: H=total_evaluated, I=accuracy, J=fp_rate, K=fn_rate, L=agreement, M=last_updated
        total_evaluated = metrics.get("total_with_feedback", "")
        accuracy = metrics.get("accuracy", "")
        fp_rate = metrics.get("false_positive_rate", "")
        fn_rate = metrics.get("false_negative_rate", "")
        agreement = metrics.get("user_agreement_rate", "")
        last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        history_ws.update_cell(target_row, 8, total_evaluated)  # Column H
        history_ws.update_cell(target_row, 9, f"{accuracy:.2%}" if isinstance(accuracy, float) else accuracy)  # Column I
        history_ws.update_cell(target_row, 10, f"{fp_rate:.2%}" if isinstance(fp_rate, float) else fp_rate)  # Column J
        history_ws.update_cell(target_row, 11, f"{fn_rate:.2%}" if isinstance(fn_rate, float) else fn_rate)  # Column K
        history_ws.update_cell(target_row, 12, f"{agreement:.2%}" if isinstance(agreement, float) else agreement)  # Column L
        history_ws.update_cell(target_row, 13, last_updated)  # Column M

        print(f"✓ Updated metrics for {version_id}")

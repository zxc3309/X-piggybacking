"""
Feedback Analysis Module

Analyzes user feedback on LLM decisions to identify patterns and calculate metrics.
Compares LLM decisions (column K) with user decisions (column P) to find disagreements.
"""

from __future__ import annotations

import os
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter
from datetime import datetime, timezone

from x_auto.sheets.client import GoogleSheetsClient


class FeedbackAnalyzer:
    """
    Analyzes user feedback on LLM match decisions.

    Compares LLM decisions (column K: llm_decision) with user decisions
    (column P: user_decision) to calculate accuracy and identify patterns.
    """

    def __init__(self, sheet_client: GoogleSheetsClient):
        """
        Initialize analyzer with Google Sheets client.

        Args:
            sheet_client: Authenticated GoogleSheetsClient instance
        """
        self.sheet_client = sheet_client
        self.all_post_ws_name = os.getenv("GOOGLE_WS_ALL_POST", "all_post")
        self._data: Optional[List[Dict[str, Any]]] = None

    def load_data(self, force_reload: bool = False) -> List[Dict[str, Any]]:
        """
        Load all_post data from Google Sheets.

        Args:
            force_reload: If True, reload data even if cached

        Returns:
            List of post dictionaries with feedback data
        """
        if self._data is not None and not force_reload:
            return self._data

        worksheet = self.sheet_client.get_sheet(self.all_post_ws_name)
        records = worksheet.get_all_records()

        # Filter to only posts with both LLM and user decisions
        self._data = []
        for record in records:
            llm_dec = self._normalize_decision(record.get("llm_decision"))
            user_dec = self._normalize_decision(record.get("user_decision"))

            # Only include if both decisions are present
            if llm_dec is not None and user_dec is not None:
                record["llm_decision_normalized"] = llm_dec
                record["user_decision_normalized"] = user_dec
                self._data.append(record)

        return self._data

    def _normalize_decision(self, value: Any) -> Optional[int]:
        """
        Normalize decision value to 0 or 1.

        Args:
            value: Decision value (could be int, str, empty)

        Returns:
            0 or 1, or None if invalid/empty
        """
        if value is None or value == "":
            return None

        # Handle string values
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
            try:
                value = int(value)
            except ValueError:
                return None

        # Convert to int
        if value in [0, 1]:
            return int(value)

        return None

    def calculate_metrics(self, prompt_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Calculate performance metrics comparing LLM vs user decisions.

        Args:
            prompt_version: Filter by specific prompt version (e.g., "v1.0")

        Returns:
            Dictionary with metrics:
                - total_posts: Total posts evaluated
                - total_with_feedback: Posts with user feedback
                - accuracy: (TP + TN) / total
                - precision: TP / (TP + FP)
                - recall: TP / (TP + FN)
                - f1_score: Harmonic mean of precision and recall
                - false_positive_rate: FP / total
                - false_negative_rate: FN / total
                - user_agreement_rate: Matching decisions / total
                - confusion_matrix: {TP, TN, FP, FN}
        """
        data = self.load_data()

        # Filter by prompt version if specified
        if prompt_version:
            data = [d for d in data if d.get("prompt_version") == prompt_version]

        if not data:
            return {
                "total_posts": 0,
                "total_with_feedback": 0,
                "error": "No posts with feedback found"
            }

        # Calculate confusion matrix
        tp = sum(1 for d in data if d["llm_decision_normalized"] == 1 and d["user_decision_normalized"] == 1)
        tn = sum(1 for d in data if d["llm_decision_normalized"] == 0 and d["user_decision_normalized"] == 0)
        fp = sum(1 for d in data if d["llm_decision_normalized"] == 1 and d["user_decision_normalized"] == 0)
        fn = sum(1 for d in data if d["llm_decision_normalized"] == 0 and d["user_decision_normalized"] == 1)

        total = len(data)

        # Calculate metrics
        accuracy = (tp + tn) / total if total > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1_score = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        fp_rate = fp / total if total > 0 else 0
        fn_rate = fn / total if total > 0 else 0
        agreement_rate = (tp + tn) / total if total > 0 else 0

        return {
            "total_posts": total,
            "total_with_feedback": total,
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": f1_score,
            "false_positive_rate": fp_rate,
            "false_negative_rate": fn_rate,
            "user_agreement_rate": agreement_rate,
            "confusion_matrix": {
                "true_positives": tp,
                "true_negatives": tn,
                "false_positives": fp,
                "false_negatives": fn,
            }
        }

    def find_disagreements(self, disagreement_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find posts where LLM and user disagree.

        Args:
            disagreement_type: Filter by type:
                - "false_positive": LLM said yes, user said no
                - "false_negative": LLM said no, user said yes
                - None: All disagreements

        Returns:
            List of post records with disagreements
        """
        data = self.load_data()

        disagreements = []
        for record in data:
            llm = record["llm_decision_normalized"]
            user = record["user_decision_normalized"]

            is_fp = llm == 1 and user == 0
            is_fn = llm == 0 and user == 1

            if disagreement_type == "false_positive" and is_fp:
                record["disagreement_type"] = "false_positive"
                disagreements.append(record)
            elif disagreement_type == "false_negative" and is_fn:
                record["disagreement_type"] = "false_negative"
                disagreements.append(record)
            elif disagreement_type is None and (is_fp or is_fn):
                record["disagreement_type"] = "false_positive" if is_fp else "false_negative"
                disagreements.append(record)

        return disagreements

    def identify_patterns(self) -> Dict[str, Any]:
        """
        Analyze disagreements to identify common patterns.

        Returns:
            Dictionary with pattern analysis:
                - common_keywords_fp: Keywords in false positives
                - common_keywords_fn: Keywords in false negatives
                - author_patterns: Authors with high disagreement rates
                - category_patterns: Categories with accuracy issues
        """
        false_positives = self.find_disagreements("false_positive")
        false_negatives = self.find_disagreements("false_negative")

        # Extract keywords from false positives
        fp_keywords = self._extract_keywords([d.get("post_content", "") for d in false_positives])
        fn_keywords = self._extract_keywords([d.get("post_content", "") for d in false_negatives])

        # Analyze by author
        data = self.load_data()
        author_stats = {}
        for record in data:
            author = record.get("author", "unknown")
            if author not in author_stats:
                author_stats[author] = {"total": 0, "disagreements": 0}

            author_stats[author]["total"] += 1
            if record["llm_decision_normalized"] != record["user_decision_normalized"]:
                author_stats[author]["disagreements"] += 1

        # Calculate disagreement rates
        author_patterns = []
        for author, stats in author_stats.items():
            if stats["total"] >= 3:  # Only include authors with 3+ posts
                rate = stats["disagreements"] / stats["total"]
                author_patterns.append({
                    "author": author,
                    "total_posts": stats["total"],
                    "disagreements": stats["disagreements"],
                    "disagreement_rate": rate
                })

        # Sort by disagreement rate
        author_patterns.sort(key=lambda x: x["disagreement_rate"], reverse=True)

        return {
            "common_keywords_fp": fp_keywords[:10],  # Top 10 keywords in FP
            "common_keywords_fn": fn_keywords[:10],  # Top 10 keywords in FN
            "author_patterns": author_patterns[:10],  # Top 10 authors by disagreement rate
            "false_positive_count": len(false_positives),
            "false_negative_count": len(false_negatives),
        }

    def _extract_keywords(self, texts: List[str]) -> List[Tuple[str, int]]:
        """
        Extract common keywords from text list.

        Args:
            texts: List of post content texts

        Returns:
            List of (keyword, count) tuples sorted by frequency
        """
        # Simple keyword extraction (count word frequencies)
        words = []
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                     "of", "with", "is", "it", "this", "that", "from", "as", "by", "be"}

        for text in texts:
            # Simple tokenization
            text_lower = text.lower()
            tokens = text_lower.split()
            for token in tokens:
                # Remove punctuation
                token = ''.join(c for c in token if c.isalnum())
                if token and len(token) > 3 and token not in stopwords:
                    words.append(token)

        # Count frequencies
        counter = Counter(words)
        return counter.most_common(20)

    def generate_report(self, format: str = "console") -> str:
        """
        Generate human-readable analysis report.

        Args:
            format: Output format ("console", "markdown")

        Returns:
            Formatted report string
        """
        metrics = self.calculate_metrics()
        patterns = self.identify_patterns()
        disagreements = self.find_disagreements()

        if metrics.get("error"):
            return f"❌ {metrics['error']}"

        # Build report
        lines = []

        if format == "console":
            lines.append("=" * 70)
            lines.append("           PROMPT PERFORMANCE ANALYSIS")
            lines.append("=" * 70)
            lines.append(f"Analysis Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
            lines.append(f"Total Posts Evaluated: {metrics['total_posts']}")
            lines.append(f"Posts With User Feedback: {metrics['total_with_feedback']}")
            lines.append("")

            lines.append("OVERALL METRICS")
            lines.append("-" * 70)
            lines.append(f"Accuracy:              {metrics['accuracy']:.1%}  [{metrics['confusion_matrix']['true_positives'] + metrics['confusion_matrix']['true_negatives']}/{metrics['total_posts']}]")
            lines.append(f"Precision:             {metrics['precision']:.1%}  [TP/(TP+FP)]")
            lines.append(f"Recall:                {metrics['recall']:.1%}  [TP/(TP+FN)]")
            lines.append(f"F1 Score:              {metrics['f1_score']:.1%}")

            # Add warning indicators
            fp_warning = "⚠ High" if metrics['false_positive_rate'] > 0.15 else "✓ Low"
            fn_warning = "⚠ High" if metrics['false_negative_rate'] > 0.15 else "✓ Low"

            lines.append(f"False Positive Rate:   {metrics['false_positive_rate']:.1%}  {fp_warning} ({metrics['confusion_matrix']['false_positives']} posts)")
            lines.append(f"False Negative Rate:   {metrics['false_negative_rate']:.1%}  {fn_warning} ({metrics['confusion_matrix']['false_negatives']} posts)")
            lines.append(f"User Agreement:        {metrics['user_agreement_rate']:.1%}")
            lines.append("")

            lines.append("CONFUSION MATRIX")
            lines.append("-" * 70)
            lines.append("                 User ACCEPT    User REJECT")
            lines.append(f"LLM ACCEPT          {metrics['confusion_matrix']['true_positives']:3d}            {metrics['confusion_matrix']['false_positives']:3d}  (FP)")
            lines.append(f"LLM REJECT          {metrics['confusion_matrix']['false_negatives']:3d}  (FN)      {metrics['confusion_matrix']['true_negatives']:3d}")
            lines.append("")

            # Pattern analysis
            lines.append("KEY FINDINGS")
            lines.append("-" * 70)

            if patterns['false_positive_count'] > 0:
                lines.append(f"1. 🔴 False Positive Patterns ({patterns['false_positive_count']} cases)")
                lines.append(f"   LLM incorrectly accepts posts that users reject:")
                lines.append("")

                if patterns['common_keywords_fp']:
                    lines.append("   Common keywords in false positives:")
                    for keyword, count in patterns['common_keywords_fp'][:5]:
                        lines.append(f"   • \"{keyword}\" ({count} occurrences)")
                    lines.append("")

            if patterns['false_negative_count'] > 0:
                lines.append(f"2. 🟡 False Negative Patterns ({patterns['false_negative_count']} cases)")
                lines.append(f"   LLM incorrectly rejects posts that users accept:")
                lines.append("")

                if patterns['common_keywords_fn']:
                    lines.append("   Common keywords in false negatives:")
                    for keyword, count in patterns['common_keywords_fn'][:5]:
                        lines.append(f"   • \"{keyword}\" ({count} occurrences)")
                    lines.append("")

            if patterns['author_patterns']:
                lines.append("3. 📊 Author-Level Patterns")
                lines.append("   Authors with high disagreement rates:")
                lines.append("")
                for author_data in patterns['author_patterns'][:5]:
                    lines.append(f"   • @{author_data['author']}: "
                                f"{author_data['disagreement_rate']:.0%} disagreement "
                                f"({author_data['disagreements']}/{author_data['total_posts']} posts)")
                lines.append("")

            # Sample disagreements
            if disagreements:
                lines.append("SAMPLE DISAGREEMENTS")
                lines.append("-" * 70)

                for i, record in enumerate(disagreements[:3], 1):
                    lines.append(f"[{record['disagreement_type'].upper()} #{i}]")
                    lines.append(f"Author: @{record.get('author', 'unknown')}")
                    lines.append(f"Post: {record.get('post_content', '')[:100]}...")
                    lines.append(f"LLM Decision: {'✅ ACCEPT' if record['llm_decision_normalized'] == 1 else '❌ REJECT'}")
                    lines.append(f"LLM Reason: {record.get('llm_reason', 'N/A')}")
                    lines.append(f"User Decision: {'✅ ACCEPT' if record['user_decision_normalized'] == 1 else '❌ REJECT'}")
                    if record.get('user_comment'):
                        lines.append(f"User Comment: {record.get('user_comment')}")
                    lines.append(f"Link: {record.get('post_link', 'N/A')}")
                    lines.append("-" * 70)

            lines.append("")
            lines.append("RECOMMENDATIONS")
            lines.append("-" * 70)

            # Generate recommendations based on metrics
            if metrics['false_positive_rate'] > 0.15:
                lines.append("⚠ High false positive rate detected:")
                lines.append("  → Review prompt to add rejection criteria")
                if patterns['common_keywords_fp']:
                    top_fp_keyword = patterns['common_keywords_fp'][0][0]
                    lines.append(f"  → Consider rejecting posts with \"{top_fp_keyword}\" pattern")

            if metrics['false_negative_rate'] > 0.15:
                lines.append("⚠ High false negative rate detected:")
                lines.append("  → Review prompt to clarify acceptance criteria")
                if patterns['common_keywords_fn']:
                    top_fn_keyword = patterns['common_keywords_fn'][0][0]
                    lines.append(f"  → Consider accepting posts with \"{top_fn_keyword}\" pattern")

            if metrics['accuracy'] > 0.90:
                lines.append("✓ Excellent accuracy! Prompt is performing well.")

            lines.append("")
            lines.append("=" * 70)

        return "\n".join(lines)

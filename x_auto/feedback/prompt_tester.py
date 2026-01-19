"""
Prompt Testing Module

Provides reusable functions to test prompts on posts with user feedback.
"""

from __future__ import annotations

from typing import Dict, List, Any

from x_auto.workflow.scrape_filter import get_llm_decision_with_reason


def test_prompt_on_feedback_posts(
    prompt_text: str,
    posts_with_feedback: List[Dict[str, Any]],
    version_id: str = "new",
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Test a prompt on posts with user feedback.

    Calls LLM for each post and compares decisions with user feedback.

    Args:
        prompt_text: The prompt to test
        posts_with_feedback: Posts with user_decision_normalized field
        version_id: Version being tested (for display)
        verbose: Print progress during testing

    Returns:
        Dict with:
            - total_tested: Number of posts tested
            - accuracy: (TP + TN) / total
            - fp_rate: False positive rate
            - fn_rate: False negative rate
            - tp, tn, fp, fn: Confusion matrix counts
            - results: Detailed results per post
            - fixed_fps: Posts where FP was fixed
            - new_fns: Posts where new FN was introduced
    """
    if verbose:
        print(f"\n🧪 Testing {version_id} on {len(posts_with_feedback)} posts with user feedback...\n")

    results = []

    for i, post in enumerate(posts_with_feedback, 1):
        post_content = post.get('post_content', '')
        user_decision = post.get('user_decision_normalized')

        # Skip if no user decision
        if user_decision is None:
            continue

        if verbose:
            print(f"[{i}/{len(posts_with_feedback)}] Testing post by @{post.get('author', 'unknown')}...", end=' ')

        # Call LLM with prompt
        try:
            llm_response = get_llm_decision_with_reason(prompt_text, post_content)
            new_decision = llm_response.get('decision_text', 0)

            results.append({
                'post_content': post_content[:100],
                'author': post.get('author'),
                'user_decision': user_decision,
                'old_decision': post.get('llm_decision_normalized'),
                'new_decision': new_decision,
                'old_reason': post.get('llm_reason', ''),
                'new_reason': llm_response.get('reason', ''),
                'user_comment': post.get('user_comment', ''),
            })

            # Show if decision changed
            old_decision = post.get('llm_decision_normalized')
            if verbose:
                if old_decision != new_decision:
                    if old_decision == 1 and new_decision == 0:
                        print("✓ Now REJECTS (was false positive)")
                    elif old_decision == 0 and new_decision == 1:
                        print("⚠ Now ACCEPTS (was false negative)")
                else:
                    print("Same")

        except Exception as e:
            if verbose:
                print(f"❌ Error: {e}")
            continue

    # Calculate metrics
    total = len(results)
    if total == 0:
        return {
            'total_tested': 0,
            'accuracy': 0,
            'fp_rate': 0,
            'fn_rate': 0,
            'tp': 0, 'tn': 0, 'fp': 0, 'fn': 0,
            'results': [],
            'fixed_fps': [],
            'new_fns': [],
            'error': 'No posts could be tested'
        }

    # New prompt metrics
    tp = sum(1 for r in results if r['new_decision'] == 1 and r['user_decision'] == 1)
    tn = sum(1 for r in results if r['new_decision'] == 0 and r['user_decision'] == 0)
    fp = sum(1 for r in results if r['new_decision'] == 1 and r['user_decision'] == 0)
    fn = sum(1 for r in results if r['new_decision'] == 0 and r['user_decision'] == 1)

    accuracy = (tp + tn) / total
    fp_rate = fp / total
    fn_rate = fn / total

    # Find fixed false positives (old=1, user=0, new=0)
    fixed_fps = [r for r in results
                 if r['old_decision'] == 1 and r['user_decision'] == 0
                 and r['new_decision'] == 0]

    # Find new false negatives (old=1 or old matched user, but now new=0 when user=1)
    new_fns = [r for r in results
               if r['new_decision'] == 0 and r['user_decision'] == 1
               and r['old_decision'] == 1]  # Was correct, now wrong

    return {
        'total_tested': total,
        'accuracy': accuracy,
        'fp_rate': fp_rate,
        'fn_rate': fn_rate,
        'tp': tp,
        'tn': tn,
        'fp': fp,
        'fn': fn,
        'results': results,
        'fixed_fps': fixed_fps,
        'new_fns': new_fns,
    }


def display_test_comparison(
    old_version: str,
    old_metrics: Dict[str, Any],
    new_version: str,
    new_metrics: Dict[str, Any]
) -> None:
    """
    Display side-by-side comparison of two prompt versions.

    Args:
        old_version: Previous version ID
        old_metrics: Metrics from previous version (from prompt_history)
        new_version: New version ID
        new_metrics: Metrics from testing new version
    """
    print("\n" + "=" * 70)
    print("VERSION COMPARISON")
    print("=" * 70)

    # Parse percentages if they're strings
    def parse_pct(val):
        if val is None:
            return 0.0
        if isinstance(val, str):
            return float(val.strip('%')) / 100
        return float(val)

    old_acc = parse_pct(old_metrics.get("accuracy"))
    new_acc = new_metrics.get("accuracy", 0)
    old_fp = parse_pct(old_metrics.get("false_positive_rate"))
    new_fp = new_metrics.get("fp_rate", 0)
    old_fn = parse_pct(old_metrics.get("false_negative_rate"))
    new_fn = new_metrics.get("fn_rate", 0)

    print(f"\n{old_version} (previous):")
    print(f"  Accuracy: {old_acc:.1%}")
    print(f"  False Positive Rate: {old_fp:.1%}")
    print(f"  False Negative Rate: {old_fn:.1%}")

    print(f"\n{new_version} (new):")
    print(f"  Accuracy: {new_acc:.1%}", end='')
    if new_acc > old_acc:
        print(f" ✓ +{(new_acc - old_acc):.1%}")
    elif new_acc < old_acc:
        print(f" ⚠️  {(new_acc - old_acc):.1%}")
    else:
        print(" (no change)")

    print(f"  False Positive Rate: {new_fp:.1%}", end='')
    if new_fp < old_fp:
        print(f" ✓ {(new_fp - old_fp):.1%}")
    elif new_fp > old_fp:
        print(f" ⚠️  +{(new_fp - old_fp):.1%}")
    else:
        print(" (no change)")

    print(f"  False Negative Rate: {new_fn:.1%}", end='')
    if new_fn < old_fn:
        print(f" ✓ {(new_fn - old_fn):.1%}")
    elif new_fn > old_fn:
        print(f" ⚠️  +{(new_fn - old_fn):.1%}")
    else:
        print(" (no change)")

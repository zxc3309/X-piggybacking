"""
Automatic sender that checks the reply queue for approved items and posts
them to X via the API.

Runs on a 5-minute interval via APScheduler. Respects the daily post limit
for the X Free tier (default 17/day) and sends Telegram failure notifications.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone

from x_auto.review import queue_manager

logger = logging.getLogger(__name__)

DEFAULT_DAILY_LIMIT = 17
DEFAULT_CHECK_INTERVAL_MIN = 5


def get_daily_limit() -> int:
    return int(os.getenv("X_DAILY_REPLY_LIMIT", str(DEFAULT_DAILY_LIMIT)))


def check_and_send() -> None:
    """Check for approved replies and send them via the X API.

    This function is called by the scheduler every N minutes.
    It processes approved items in FIFO order (earliest approved first)
    and stops when the daily quota is reached.
    """
    logger.info("[AutoSender] Checking for approved replies...")

    daily_limit = get_daily_limit()
    daily_sent = queue_manager.get_daily_sent_count()

    if daily_sent >= daily_limit:
        logger.info(f"[AutoSender] Daily limit reached ({daily_sent}/{daily_limit}), skipping")
        return

    remaining = daily_limit - daily_sent

    try:
        approved_items = queue_manager.get_items_by_status("approved")
    except Exception as e:
        logger.error(f"[AutoSender] Failed to fetch approved items: {e}", exc_info=True)
        return

    if not approved_items:
        logger.info("[AutoSender] No approved items to send")
        return

    # Sort by approved_at (FIFO)
    approved_items.sort(key=lambda x: x.get("approved_at", ""))

    sent_count = 0
    for item in approved_items:
        if sent_count >= remaining:
            logger.info(f"[AutoSender] Daily limit reached after sending {sent_count} replies")
            break

        queue_id = item.get("queue_id", "")
        post_id = item.get("post_id", "") or queue_manager.extract_post_id(item.get("post_link", ""))
        reply_text = (item.get("edited_reply") or "").strip() or (item.get("original_reply") or "").strip()

        if not post_id:
            error_msg = "Cannot extract post_id from post_link"
            logger.error(f"[AutoSender] {error_msg}: {item.get('post_link')}")
            queue_manager.mark_failed(queue_id, error_msg)
            _notify_failure(item, error_msg)
            continue

        if not reply_text:
            error_msg = "No reply text (both edited_reply and original_reply are empty)"
            logger.error(f"[AutoSender] {error_msg} for queue_id={queue_id}")
            queue_manager.mark_failed(queue_id, error_msg)
            _notify_failure(item, error_msg)
            continue

        if len(reply_text) > 280:
            error_msg = f"Reply exceeds 280 chars ({len(reply_text)})"
            logger.error(f"[AutoSender] {error_msg} for queue_id={queue_id}")
            queue_manager.mark_failed(queue_id, error_msg)
            _notify_failure(item, error_msg)
            continue

        # Check if X posting is enabled
        if os.getenv("ENABLE_X_POSTING", "false").lower() != "true":
            logger.warning(f"[AutoSender] X posting disabled (ENABLE_X_POSTING != true), marking as sent for testing")
            queue_manager.mark_sent(queue_id)
            sent_count += 1
            continue

        # Post the reply via X API
        try:
            from x_auto.x_api.x_client import post_reply
            response = post_reply(text=reply_text, in_reply_to_post_id=post_id)
            logger.info(f"[AutoSender] Reply sent for queue_id={queue_id}, response={response}")
            queue_manager.mark_sent(queue_id)
            sent_count += 1
        except Exception as e:
            error_msg = str(e)[:500]
            logger.error(f"[AutoSender] Failed to send reply for queue_id={queue_id}: {e}", exc_info=True)
            queue_manager.mark_failed(queue_id, error_msg)
            _notify_failure(item, error_msg)

    logger.info(f"[AutoSender] Finished. Sent {sent_count} replies. "
                f"Daily total: {daily_sent + sent_count}/{daily_limit}")


def _notify_failure(item: dict, error: str) -> None:
    """Send a Telegram notification about a failed reply."""
    try:
        if os.getenv("ENABLE_TELEGRAM_NOTIFICATIONS", "true").lower() != "true":
            return

        from x_auto.notifications.telegram_bot import send_telegram_message

        author = item.get("author", "unknown")
        post_link = item.get("post_link", "")
        queue_id = item.get("queue_id", "")

        # Use HTML parse mode to avoid Markdown escaping issues
        message = (
            f"❌ Reply Failed\n\n"
            f"Author: @{author}\n"
            f"Post: {post_link}\n"
            f"Queue ID: {queue_id}\n"
            f"Error: {error[:200]}"
        )
        send_telegram_message(message, parse_mode=None)
    except Exception as e:
        logger.error(f"[AutoSender] Failed to send failure notification: {e}")

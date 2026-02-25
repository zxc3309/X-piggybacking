"""
Telegram Bot integration for sending daily crypto intelligence summaries.

This module handles:
- Sending formatted messages to Telegram
- Grouping posts by category with emojis
- Handling edge cases (no posts, message too long, API failures)
"""

from __future__ import annotations

import os
import logging
import asyncio
from typing import List, Dict, Any
from datetime import datetime, timezone

from telegram import Bot
from telegram.error import TelegramError, NetworkError, Forbidden
from telegram.constants import ParseMode

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Category emoji and display name mappings
CATEGORY_EMOJIS = {
    "token_analysis": "📊",
    "industry_analysis": "🏭",
    "market_comment": "💬",
    "tokenomic_comment": "💰",
    "others": "🔍"
}

CATEGORY_DISPLAY_NAMES = {
    "token_analysis": "Token Analysis",
    "industry_analysis": "Industry Analysis",
    "market_comment": "General Market Comment",
    "tokenomic_comment": "Tokenomic Comment",
    "others": "Others"
}

# Telegram message size limit
MAX_MESSAGE_LENGTH = 4000  # Leave buffer below 4096 limit


async def _send_message_async(bot_token: str, chat_id: str, message: str, parse_mode: str) -> bool:
    """
    Async helper to send a message to Telegram.

    Args:
        bot_token: Telegram bot token
        chat_id: Telegram chat ID
        message: Message text to send
        parse_mode: Telegram parse mode (Markdown or HTML)

    Returns:
        True if message sent successfully, False otherwise
    """
    try:
        bot = Bot(token=bot_token)
        async with bot:
            await bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode=parse_mode,
                disable_web_page_preview=False  # Show link previews
            )
        logger.info(f"Telegram message sent successfully to chat {chat_id}")
        return True

    except Forbidden as e:
        logger.critical(f"Telegram bot token is invalid or unauthorized: {e}")
        return False

    except NetworkError as e:
        logger.error(f"Telegram network error: {e}")
        return False

    except TelegramError as e:
        logger.error(f"Telegram API error: {e}")
        return False

    except Exception as e:
        logger.error(f"Unexpected error sending Telegram message: {e}", exc_info=True)
        return False


def escape_html(text: str) -> str:
    """Escape special HTML characters."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def send_telegram_message(message: str, parse_mode: str = ParseMode.HTML) -> bool:
    """
    Send a message to the configured Telegram chat.

    Args:
        message: Message text to send
        parse_mode: Telegram parse mode (Markdown or HTML)

    Returns:
        True if message sent successfully, False otherwise

    Raises:
        RuntimeError: If Telegram credentials are not configured
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        raise RuntimeError(
            "Telegram credentials not configured. "
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
        )

    # Run the async function in a new event loop
    return asyncio.run(_send_message_async(bot_token, chat_id, message, parse_mode))


def format_posts_by_category(posts: List[Dict[str, Any]]) -> str:
    """
    Format posts grouped by category with emojis and markdown links.

    Args:
        posts: List of post dictionaries with 'summary', 'category', and 'post_link'

    Returns:
        Formatted markdown message string
    """
    # Group posts by category
    categorized: Dict[str, List[Dict[str, Any]]] = {}
    for post in posts:
        category = post.get("category", "others")
        if category not in categorized:
            categorized[category] = []
        categorized[category].append(post)

    # Build message header
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_count = len(posts)

    message_parts = [
        "🚨 <b>Daily Crypto Intelligence Summary</b>",
        f"📅 {today} - {total_count} posts",
        ""
    ]

    # Sort categories to ensure consistent order
    category_order = ["token_analysis", "industry_analysis", "market_comment",
                     "tokenomic_comment", "others"]

    # Add each category section
    for category in category_order:
        if category not in categorized:
            continue

        posts_in_category = categorized[category]
        emoji = CATEGORY_EMOJIS.get(category, "🔍")
        display_name = CATEGORY_DISPLAY_NAMES.get(category, category.replace("_", " ").title())
        count = len(posts_in_category)

        message_parts.append(f"{emoji} <b>{display_name}</b> ({count})")

        # Add each post as a markdown link
        for post in posts_in_category:
            summary = post.get("summary", "Untitled post")
            summary_escaped = escape_html(summary)

            post_link = post.get("post_link", "")
            if not post_link:
                # Fallback: construct link from post_id with author for mobile deep linking
                post_id = post.get("post_id", "")
                if post_id:
                    # Try to get author from nested post data for standard URL format
                    post_data = post.get("post", {})
                    author = post_data.get("author", {}).get("userName", "")
                    if author:
                        # Standard format triggers iOS/Android Universal Links for X app
                        post_link = f"https://x.com/{author}/status/{post_id}"
                    else:
                        post_link = f"https://x.com/i/web/status/{post_id}"

            if post_link:
                message_parts.append(f'→ <a href="{post_link}">{summary_escaped}</a>')
            else:
                message_parts.append(f"→ {summary_escaped}")

        message_parts.append("")  # Blank line between categories

    # Add review dashboard link if configured
    dashboard_url = os.getenv("REVIEW_DASHBOARD_URL", "")
    if dashboard_url:
        pending_count = len(posts)
        message_parts.append(
            f'📝 <a href="{dashboard_url}/review?status=pending">{pending_count} replies pending review</a>'
        )
        message_parts.append("")

    # Add footer
    message_parts.append("---")
    message_parts.append("<i>Powered by X-Piggybacking Analyzer</i>")

    return "\n".join(message_parts)


def split_message_if_needed(message: str, max_length: int = MAX_MESSAGE_LENGTH) -> List[str]:
    """
    Split a long message into multiple parts if it exceeds Telegram's limit.

    Args:
        message: The message to potentially split
        max_length: Maximum length per message

    Returns:
        List of message parts (single item if no split needed)
    """
    if len(message) <= max_length:
        return [message]

    # Split by sections (category groups)
    parts = []
    lines = message.split("\n")
    current_part = []
    current_length = 0

    for line in lines:
        line_length = len(line) + 1  # +1 for newline

        # If adding this line would exceed limit, start new part
        if current_length + line_length > max_length and current_part:
            parts.append("\n".join(current_part))
            current_part = [line]
            current_length = line_length
        else:
            current_part.append(line)
            current_length += line_length

    # Add remaining lines
    if current_part:
        parts.append("\n".join(current_part))

    return parts


def send_daily_summary(matched_posts: List[Dict[str, Any]]) -> bool:
    """
    Send daily summary of matched posts to Telegram.

    Handles edge cases:
    - No posts: Sends "No matches today" message
    - Too many posts: Splits into multiple messages
    - API failures: Logs and returns False without crashing

    Args:
        matched_posts: List of post dictionaries with summary, category, and link

    Returns:
        True if all messages sent successfully, False otherwise
    """
    # Check if Telegram notifications are enabled
    if os.getenv("ENABLE_TELEGRAM_NOTIFICATIONS", "true").lower() != "true":
        logger.info("Telegram notifications disabled, skipping send")
        return True

    try:
        # Handle case: no matched posts
        if not matched_posts or len(matched_posts) == 0:
            no_posts_message = (
                "🚨 <b>Daily Crypto Intelligence Summary</b>\n"
                f"📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n"
                "ℹ️ No matching posts found today.\n\n"
                "---\n"
                "<i>Powered by X-Piggybacking Analyzer</i>"
            )
            return send_telegram_message(no_posts_message)

        # Format posts by category
        formatted_message = format_posts_by_category(matched_posts)

        # Split if message is too long
        message_parts = split_message_if_needed(formatted_message)

        # Send all parts
        all_success = True
        dashboard_url = os.getenv("REVIEW_DASHBOARD_URL", "")
        for idx, part in enumerate(message_parts, 1):
            if len(message_parts) > 1:
                logger.info(f"Sending part {idx}/{len(message_parts)} to Telegram")

            # Append dashboard link to every part if not already present
            if dashboard_url and dashboard_url not in part:
                part += f'\n\n📋 <a href="{dashboard_url}/review?status=pending">Open Dashboard</a>'

            success = send_telegram_message(part)
            if not success:
                all_success = False
                logger.error(f"Failed to send message part {idx}")

        return all_success

    except Exception as e:
        logger.error(f"Error in send_daily_summary: {e}", exc_info=True)
        return False

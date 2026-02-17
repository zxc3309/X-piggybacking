"""
Article detector for X (Twitter) posts.

This module detects when a post contains an X Article link.
X Articles are long-form content that cannot be easily scraped,
so posts containing them are auto-passed through the LLM filter.

Implementation:
- Finds t.co short URLs in post text
- Expands t.co URLs to get the actual destination
- Checks if the destination matches x.com/i/article/ pattern
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Regex patterns
TCO_URL_PATTERN = re.compile(r'https?://t\.co/\w+')
ARTICLE_URL_PATTERN = re.compile(r'https?://x\.com/i/article/\d+')


def expand_tco_url(tco_url: str, timeout: int = 10) -> Optional[str]:
    """
    Expand a t.co short URL to get the actual destination URL.

    Uses a HEAD request with redirect following disabled to get the Location header.

    Args:
        tco_url: The t.co URL to expand (e.g., "https://t.co/14zSYHXGZv")
        timeout: Request timeout in seconds

    Returns:
        The expanded URL, or None if expansion failed
    """
    try:
        # Use HEAD request with allow_redirects=False to get redirect location
        response = requests.head(
            tco_url,
            allow_redirects=False,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; ArticleDetector/1.0)'
            }
        )

        # Check for redirect (301, 302, 303, 307, 308)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get('Location')
            if location:
                logger.debug(f"Expanded {tco_url} -> {location}")
                return location

        # Some t.co URLs might use meta refresh, try GET as fallback
        response = requests.get(
            tco_url,
            allow_redirects=True,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; ArticleDetector/1.0)'
            }
        )

        # Return final URL after redirects
        if response.url != tco_url:
            logger.debug(f"Expanded {tco_url} -> {response.url}")
            return response.url

        return None

    except requests.RequestException as e:
        logger.warning(f"Failed to expand t.co URL {tco_url}: {e}")
        return None


def contains_tco_link(text: str) -> bool:
    """
    Check if text contains any t.co links.

    Args:
        text: The text to check

    Returns:
        True if text contains at least one t.co link
    """
    return bool(TCO_URL_PATTERN.search(text))


def extract_tco_urls(text: str) -> list[str]:
    """
    Extract all t.co URLs from text.

    Args:
        text: The text to extract URLs from

    Returns:
        List of t.co URLs found in the text
    """
    return TCO_URL_PATTERN.findall(text)


def is_article_url(url: str) -> bool:
    """
    Check if a URL is an X Article URL.

    Args:
        url: The URL to check

    Returns:
        True if the URL matches x.com/i/article/ pattern
    """
    return bool(ARTICLE_URL_PATTERN.match(url))


def is_article_post(post: dict) -> Tuple[bool, Optional[str]]:
    """
    Check if a post contains an X Article link.

    This function:
    1. Extracts t.co links from the post text
    2. Expands each t.co link to get the actual URL
    3. Checks if any expanded URL is an X Article

    Args:
        post: The post dictionary (must have 'text' or 'postText' field)

    Returns:
        Tuple of (is_article, article_url):
        - is_article: True if post contains an X Article link
        - article_url: The Article URL if found, None otherwise
    """
    text = post.get("text") or post.get("postText") or ""

    if not text:
        return False, None

    # First check if there are any t.co links
    tco_urls = extract_tco_urls(text)

    if not tco_urls:
        return False, None

    # Expand each t.co URL and check if it's an Article
    for tco_url in tco_urls:
        expanded_url = expand_tco_url(tco_url)

        if expanded_url and is_article_url(expanded_url):
            logger.info(f"Detected X Article: {expanded_url}")
            return True, expanded_url

    return False, None


def fetch_article_content(username: str, tweet_id: str, timeout: int = 15) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch full article content from fxtwitter API.

    Args:
        username: The X username (without @)
        tweet_id: The tweet/post ID
        timeout: Request timeout in seconds

    Returns:
        Tuple of (content, article_url):
        - content: Plain text article content, or None on failure
        - article_url: The constructed article URL, or None
    """
    url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        article = data.get("tweet", {}).get("article")
        if not article:
            logger.debug(f"No article content found for {username}/{tweet_id}")
            return None, None

        # Construct article URL from article ID
        article_id = article.get("id", "")
        article_url = f"https://x.com/i/article/{article_id}" if article_id else None

        blocks = article.get("content", {}).get("blocks", [])
        if not blocks:
            return None, article_url

        title = article.get("title", "")
        text = _extract_text_from_blocks(blocks)
        if title and text:
            text = f"{title}\n\n{text}"
        if text:
            logger.info(f"Fetched article content ({len(text)} chars) for {username}/{tweet_id}")
        return text or None, article_url

    except requests.RequestException as e:
        logger.warning(f"Failed to fetch article from fxtwitter for {username}/{tweet_id}: {e}")
        return None, None
    except (KeyError, ValueError) as e:
        logger.warning(f"Failed to parse fxtwitter response for {username}/{tweet_id}: {e}")
        return None, None


def _extract_text_from_blocks(blocks: list) -> str:
    """
    Convert structured article blocks into plain text.

    Handles the fxtwitter article block format where each block has:
    - "type": "unstyled", "header-one", "header-two", "ordered-list-item", "atomic", etc.
    - "text": the text content of the block

    Args:
        blocks: List of article block dicts from fxtwitter API

    Returns:
        Plain text string
    """
    parts = []
    for block in blocks:
        block_type = block.get("type", "")
        text = block.get("text", "")

        if not text:
            continue

        if block_type == "unstyled":
            parts.append(text)
        elif block_type in ("header-one", "header-two", "header-three"):
            parts.append(f"\n{text}\n")
        elif block_type in ("ordered-list-item", "unordered-list-item"):
            parts.append(f"  - {text}")
        else:
            parts.append(text)

    return "\n".join(parts).strip()


def get_article_content_for_post(post: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract article content for a post using fxtwitter API.

    Extracts username and tweet_id from the post dict and fetches the article.

    Args:
        post: The post dictionary

    Returns:
        Tuple of (content, article_url):
        - content: Plain text article content, or None on failure
        - article_url: The article URL, or None
    """
    username = post.get("username") or post.get("authorUsername") or post.get("author", {}).get("userName", "")
    tweet_id = post.get("id") or post.get("postId") or ""

    if not username or not tweet_id:
        logger.debug("Cannot fetch article: missing username or tweet_id")
        return None, None

    return fetch_article_content(username, str(tweet_id))

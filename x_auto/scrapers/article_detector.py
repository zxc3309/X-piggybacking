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

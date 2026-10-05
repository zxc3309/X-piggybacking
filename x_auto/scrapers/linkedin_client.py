"""
Connector for the Apify actor `harvestapi/linkedin-profile-posts` (no cookies).

Fetches recent posts from LinkedIn profiles and normalizes them into the same
shape the X pipeline uses (text / id / timestamp / url / author.userName), so
downstream filtering, sheet logging and the review queue work unchanged.

Normalized posts carry `platform="linkedin"`; callers use it to avoid X-only
actions such as building an X reply intent.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests

APIFY_LINKEDIN_RUN_URL = (
    "https://api.apify.com/v2/acts/"
    "harvestapi~linkedin-profile-posts/run-sync-get-dataset-items"
)


def posted_limit_for_days(days: int) -> str:
    """Map the pipeline lookback window onto the actor's postedLimit options."""
    if days <= 1:
        return "24h"
    if days <= 7:
        return "week"
    if days <= 31:
        return "month"
    return "3months"


def normalize_profile_url(url: str) -> str:
    """Strip query/trailing slash so actor targetUrl and sheet URL compare equal."""
    return url.split("?")[0].rstrip("/").lower()


def normalize_post(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert one actor item into the X-like post dict used by the workflow."""
    author = raw.get("author") or {}
    posted = raw.get("postedAt") or {}
    engagement = raw.get("engagement") or {}
    url = raw.get("linkedinUrl") or (raw.get("socialContent") or {}).get("shareUrl") or ""
    return {
        "platform": "linkedin",
        "id": str(raw.get("id") or raw.get("entityId") or ""),
        "text": raw.get("content") or "",
        "url": url,
        "postUrl": url,
        "timestamp": posted.get("timestamp"),
        "author": {
            "userName": author.get("publicIdentifier") or author.get("universalName") or "",
            "name": author.get("name") or "",
        },
        "likes": engagement.get("likes", 0),
        "replyCount": engagement.get("comments", 0),
        "retweetCount": engagement.get("shares", 0),
        "bookmarkCount": 0,
        "viewCount": 0,
        "_target_url": normalize_profile_url((raw.get("query") or {}).get("targetUrl") or ""),
    }


def fetch_linkedin_posts(
    profile_urls: List[str],
    max_posts: int = 5,
    lookback_days: int = 1,
    timeout_seconds: int = 600,
) -> List[Dict[str, Any]]:
    """
    Fetch recent original posts (no plain reposts) for the given LinkedIn profiles.

    Args:
        profile_urls: LinkedIn profile or company URLs.
        max_posts: Maximum posts per profile (caps Apify cost).
        lookback_days: Only posts newer than this window are requested.
        timeout_seconds: Request timeout in seconds.

    Returns:
        Normalized post dictionaries (see normalize_post).

    Raises:
        ValueError: If APIFY_TOKEN is missing.
        requests.HTTPError: If the Apify API response status is not 2xx.
    """
    if not profile_urls:
        return []
    token = os.getenv("APIFY_TOKEN")
    if not token:
        raise ValueError("APIFY_TOKEN environment variable is required but missing.")

    payload: Dict[str, Any] = {
        "targetUrls": profile_urls,
        "maxPosts": max_posts,
        "postedLimit": posted_limit_for_days(lookback_days),
        "includeReposts": False,
        "includeQuotePosts": True,
    }
    response = requests.post(
        APIFY_LINKEDIN_RUN_URL,
        params={"token": token},
        json=payload,
        timeout=timeout_seconds,
    )
    if not 200 <= response.status_code < 300:
        raise requests.HTTPError(
            f"Apify LinkedIn request failed with status {response.status_code}: {response.text}",
            response=response,
        )
    items = response.json()
    return [normalize_post(item) for item in items if item.get("type", "post") == "post"]

"""
Read-only client utilities for the X (Twitter) v2 API.

Supports OAuth1.0a (user context) or OAuth2.0 Bearer token for authentication.

Note: Posting/reply functions were removed due to X API's 2026-02 restriction
on programmatic replies (affects Free/Basic/Pro/Pay-Per-Use tiers).
Replies are now handled via X Intent URLs in the Dashboard UI.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests
from requests_oauthlib import OAuth1

TWEETS_ENDPOINT = "https://api.twitter.com/2/tweets"


def _get_auth() -> Dict[str, Optional[str]]:
    """
    Load credentials from environment variables and determine auth mode.

    Returns:
        Dict containing credentials and a flag for oauth1 usage.

    Raises:
        RuntimeError: If required credentials are missing.
    """
    api_key = os.getenv("X_API_KEY") or ""
    api_secret = os.getenv("X_API_SECRET") or ""
    access_token_secret = os.getenv("X_ACCESS_TOKEN_SECRET") or ""

    # OAuth2 bearer token (user context with tweet.read scope).
    bearer = (
        os.getenv("X_BEARER_TOKEN")
        or os.getenv("X_OAUTH2_ACCESS_TOKEN")
        or ""
    )
    if bearer:
        return {
            "oauth1": False,
            "api_key": os.getenv("X_CLIENT_ID"),
            "api_secret": os.getenv("X_CLIENT_SECRET"),
            "access_token": bearer,
            "access_token_secret": None,
        }

    # Fallback: use OAuth1 if bearer not supplied.
    access_token = os.getenv("X_ACCESS_TOKEN") or ""
    if access_token_secret:
        if not (api_key and api_secret and access_token):
            raise RuntimeError("OAuth1 requires X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, and X_ACCESS_TOKEN_SECRET.")
        return {
            "oauth1": True,
            "api_key": api_key,
            "api_secret": api_secret,
            "access_token": access_token,
            "access_token_secret": access_token_secret,
        }

    raise RuntimeError(
        "Missing credentials: set X_BEARER_TOKEN (OAuth2) or OAuth1 keys including X_ACCESS_TOKEN_SECRET."
    )


def _build_request_args() -> tuple:
    """Build (auth_obj_or_None, headers) from environment credentials."""
    auth_conf = _get_auth()
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    auth_obj = None

    if auth_conf["oauth1"]:
        auth_obj = OAuth1(
            auth_conf["api_key"],
            auth_conf["api_secret"],
            auth_conf["access_token"],
            auth_conf["access_token_secret"],
        )
    else:
        headers["Authorization"] = f"Bearer {auth_conf['access_token']}"

    return auth_obj, headers


def get_tweet(tweet_id: str, tweet_fields: str = "reply_settings,author_id") -> Optional[Dict[str, Any]]:
    """
    GET /2/tweets/:id — look up a tweet's metadata.

    Returns parsed JSON on success, or None if the request fails
    (e.g. Free tier doesn't support this endpoint).
    """
    auth_obj, headers = _build_request_args()
    url = f"{TWEETS_ENDPOINT}/{tweet_id}"
    params = {"tweet.fields": tweet_fields} if tweet_fields else {}

    try:
        response = requests.get(
            url, params=params, headers=headers, auth=auth_obj, timeout=15,
        )
    except Exception:
        return None

    if 200 <= response.status_code < 300:
        try:
            return response.json()
        except ValueError:
            return None
    return None

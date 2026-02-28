"""
Client utilities for posting replies to X (Twitter) via the v2 API.

Supports OAuth1.0a (user context) when both access token and secret are present,
or OAuth2.0 Bearer token when only an access token is provided.

Example:
    >>> from x_auto.x_api.x_client import post_reply
    >>> response = post_reply("Hello world", in_reply_to_post_id="1234567890")
    >>> print(response.get("data"))
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests
from requests_oauthlib import OAuth1

TWEETS_ENDPOINT = "https://api.twitter.com/2/tweets"

# Substring in X API error body that indicates conversation control restriction
_CONVERSATION_CONTROL_MSG = "not been mentioned or otherwise engaged"


class ConversationControlError(Exception):
    """Raised when a reply is blocked by the tweet author's conversation control settings."""
    pass


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

    # OAuth2 bearer token (user context with tweet.write scope). If explicitly provided, prefer bearer even if
    # OAuth1 secrets are set, to avoid unexpected mode selection.
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
        "Missing credentials: set X_BEARER_TOKEN (OAuth2 user token with tweet.write) or OAuth1 keys including X_ACCESS_TOKEN_SECRET."
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


def post_tweet(text: str) -> Dict[str, Any]:
    """
    POST /2/tweets — post a standalone tweet (not a reply).

    Returns:
        Parsed JSON response from the X API.

    Raises:
        requests.HTTPError: For non-success HTTP responses.
    """
    auth_obj, headers = _build_request_args()
    payload = {"text": text}

    response = requests.post(
        TWEETS_ENDPOINT,
        json=payload,
        headers=headers,
        auth=auth_obj,
        timeout=30,
    )

    if not 200 <= response.status_code < 300:
        print("X API response headers:", dict(response.headers))
        message = f"X API request failed ({response.status_code}): {response.text}"
        raise requests.HTTPError(message, response=response)

    try:
        return response.json()
    except ValueError as exc:
        raise ValueError("Failed to decode X API response as JSON.") from exc


def post_reply(text: str, in_reply_to_post_id: str) -> Dict[str, Any]:
    """
    Post a reply to an existing X (Twitter) post using the v2 tweets endpoint.

    Args:
        text: Reply body to publish.
        in_reply_to_post_id: The tweet ID to reply to.

    Returns:
        Parsed JSON response from the X API.

    Raises:
        ConversationControlError: When the tweet author's conversation settings block replies.
        RuntimeError: For missing credentials.
        requests.HTTPError: For non-success HTTP responses.
        ValueError: For JSON decoding errors in the API response.
    """
    auth_obj, headers = _build_request_args()

    payload = {
        "text": text,
        "reply": {"in_reply_to_tweet_id": in_reply_to_post_id},
    }

    response = requests.post(
        TWEETS_ENDPOINT,
        json=payload,
        headers=headers,
        auth=auth_obj,
        timeout=30,
    )

    if not 200 <= response.status_code < 300:
        # Aid debugging by exposing returned headers (e.g., x-access-level).
        print("X API response headers:", dict(response.headers))
        resp_text = response.text

        # Detect conversation control restriction
        if response.status_code == 403 and _CONVERSATION_CONTROL_MSG in resp_text.lower():
            raise ConversationControlError(
                f"Reply blocked by conversation control (403): {resp_text}"
            )

        message = f"X API request failed ({response.status_code}): {resp_text}"
        raise requests.HTTPError(message, response=response)

    try:
        return response.json()
    except ValueError as exc:
        raise ValueError("Failed to decode X API response as JSON.") from exc

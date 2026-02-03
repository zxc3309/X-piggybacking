"""
Scrape X posts from profile URLs listed in Google Sheets and filter them via LLM.

Workflow:
1) Read profile URLs from header columns `X(handle)` / `X(link)` in the profiles worksheet.
2) Read a decision prompt from the "prompts" worksheet (first row/column or a
   "prompt" column if present).
3) Fetch recent posts for each profile via the Apify actor.
4) Send post text to the ChatGPT API with the decision prompt to get a yes/no.
5) Print or return posts that satisfy the requirement.

This module focuses on scraping and LLM-based filtering, leaving reply/posting
to other modules.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

from x_auto.scrapers.apify_client import fetch_posts
from x_auto.scrapers.article_detector import is_article_post
from x_auto.sheets.client import GoogleSheetsClient


def load_env() -> None:
    """
    Load environment variables from .env if present.

    In cloud environments (Railway, Docker, etc.), skip loading .env files
    since environment variables are managed by the platform.
    """
    # Check if running in a cloud environment
    is_cloud = (
        os.getenv("RAILWAY_ENVIRONMENT") is not None or  # Railway
        os.getenv("RAILWAY_ENVIRONMENT_NAME") is not None or
        os.getenv("DOCKER_CONTAINER") is not None or  # Docker
        os.getenv("KUBERNETES_SERVICE_HOST") is not None  # Kubernetes
    )

    if is_cloud:
        # In cloud: use platform-provided environment variables
        print("INFO: Detected cloud environment, using platform environment variables")
        return

    # In local development: try to load from .env
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    env_path = os.path.join(project_root, ".env")

    if os.path.isfile(env_path):
        load_dotenv(env_path, override=True)
        print("INFO: Loaded environment variables from .env")
    else:
        print("WARNING: No .env file found in local development")

    # IMPORTANT: Do NOT fallback to .env.example
    # .env.example is a template only and should never be loaded


def get_profile_urls(sheet_client: GoogleSheetsClient, sheet_name: str = "profiles") -> List[str]:
    """
    Extract profile URLs using header columns `X(handle)` / `X(link)` or the 5th column.

    Args:
        sheet_client: Authenticated GoogleSheetsClient instance.
        sheet_name: Worksheet name containing profile rows.

    Returns:
        List of validated X profile URLs.
    """
    # New env var with fallback to legacy
    worksheet_name = os.getenv("GOOGLE_WS_PROFILES") or os.getenv("GOOGLE_X_PROFILES_WORKSHEET", sheet_name)
    try:
        worksheet = sheet_client.get_sheet(worksheet_name)
    except RuntimeError:
        variants = {worksheet_name.strip(), f"{worksheet_name} ", worksheet_name}
        last_exc: Optional[Exception] = None
        for candidate in variants:
            if not candidate:
                continue
            try:
                worksheet = sheet_client.get_sheet(candidate)
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        else:
            raise RuntimeError(f"Worksheet '{worksheet_name}' not found.") from last_exc

    urls: List[str] = []
    def normalize_links(raw: str) -> List[str]:
        cleaned: List[str] = []
        # Split on common separators (whitespace, commas, pipes, newlines)
        parts = re.split("[\\s,|]+", raw)
        for part in parts:
            p = part.replace("\u00a0", " ").strip().strip('"').strip("'")
            if not p or p.lower() in {"n/a", "na", "(full link not provided)"}:
                continue
            # Normalize twitter.com → x.com
            p = p.replace("twitter.com", "x.com")
            # Add protocol if missing
            if p.startswith("x.com/") or p.startswith("www.x.com/"):
                p = "https://" + p
            if not p.startswith("http"):
                continue
            cleaned.append(p)
        return cleaned

    def is_valid(url: str) -> bool:
        cleaned = url.replace("\u00a0", " ").strip()
        if "x.com/" not in cleaned:
            return False
        if cleaned.startswith("http://"):
            cleaned = "https://" + cleaned[len("http://") :]
        # Accept any https URL containing x.com with no spaces.
        return cleaned.startswith("https://") and ("x.com/" in cleaned) and (" " not in cleaned)

    try:
        records = worksheet.get_all_records()
        for row in records:
            handle = row.get("X(handle)") or row.get("X handle") or row.get("handle") or row.get("Handle")
            link = row.get("X(link)") or row.get("X link") or row.get("link")
            handle_str = (handle or "").strip()
            link = (link or "").strip()

            if link:
                urls.extend(normalize_links(link))
            if handle_str:
                # Split multiple handles by newlines, commas, spaces, pipes, or slashes
                handle_parts = re.split(r'[\n,|/]+', handle_str)
                for h in handle_parts:
                    # Clean each handle: remove @, whitespace, and parenthetical notes
                    h = h.strip().lstrip("@")
                    # Remove anything in parentheses (e.g., "(founder)")
                    h = re.sub(r'\s*\([^)]*\)\s*', '', h).strip()
                    # Filter out invalid handles
                    if h and h.lower() not in {"n/a", "na", "https:", "http:", "x.com", "twitter.com"}:
                        # Validate handle format (alphanumeric, underscore, no spaces/special chars)
                        if re.match(r'^[a-zA-Z0-9_]+$', h):
                            urls.append(f"https://x.com/{h}")
    except Exception:
        records = None

    # Fallback if headers are not unique or URLs are empty: use 5th column (index 4).
    if not urls:
        values = worksheet.get_all_values()
        if values:
            for row in values[1:]:
                if len(row) > 4 and row[4].strip():
                    urls.extend(normalize_links(row[4].strip()))

    # Deduplicate and validate.
    seen = set()
    valid_urls: List[str] = []
    for u in urls:
        if not is_valid(u):
            continue
        if u in seen:
            continue
        seen.add(u)
        valid_urls.append(u)

    if len(valid_urls) != len(urls):
        print(f"Filtered out {len(urls) - len(valid_urls)} invalid profile URLs.")
    return valid_urls


def is_recent_post(post: Dict[str, Any], days: int = 30) -> bool:
    """
    Check whether a post's timestamp falls within the last N days.

    Args:
        post: Post dictionary (expects a 'timestamp' field in milliseconds or 'createdAt' string).
        days: Window size in days to treat as recent.

    Returns:
        True if timestamp is within the window; False otherwise.
    """
    # Try timestamp field first (milliseconds)
    ts = post.get("timestamp")
    if ts is not None:
        try:
            ts_dt = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
        except Exception:
            ts_dt = None
    else:
        # Fallback to createdAt string (e.g., "Sat Jan 03 12:55:35 +0000 2026")
        created_at = post.get("createdAt")
        if not created_at:
            return False
        try:
            # Parse format: "Sat Jan 03 12:55:35 +0000 2026"
            ts_dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
            # Convert to UTC
            ts_dt = ts_dt.astimezone(timezone.utc)
        except Exception:
            return False

    if ts_dt is None:
        return False

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    return ts_dt >= cutoff


def merge_threaded_posts(posts: List[Dict[str, Any]], window_ms: int = 120_000) -> List[Dict[str, Any]]:
    """
    Merge posts (including replies) from the same profile that belong to the same conversation
    and occur within a short window (default 2 minutes).

    Args:
        posts: List of post dicts for a single profile.
        window_ms: Time window in milliseconds to merge contiguous posts.

    Returns:
        A list of merged post dictionaries.
    """
    # Group by conversation id (fallback to post id if missing).
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for p in posts:
        cid = str(p.get("conversationId") or p.get("postId") or p.get("id") or "")
        groups.setdefault(cid, []).append(p)

    merged_all: List[Dict[str, Any]] = []
    for group in groups.values():
        posts_with_ts = [p for p in group if p.get("timestamp") is not None]
        posts_no_ts = [p for p in group if p.get("timestamp") is None]

        merged: List[Dict[str, Any]] = []
        for p in sorted(posts_with_ts, key=lambda x: x["timestamp"]):
            if not merged:
                merged.append(p)
                continue
            prev = merged[-1]
            if p["timestamp"] - prev["timestamp"] <= window_ms:
                # Merge content fields and track IDs/URLs.
                prev_text = prev.get("text") or prev.get("postText") or ""
                new_text = (p.get("text") or p.get("postText") or "")
                prev["text"] = (prev_text + " " + new_text).strip()
                # Concatenate IDs and post URLs to retain references.
                pid = prev.get("postId") or prev.get("id") or ""
                nid = p.get("postId") or p.get("id") or ""
                if nid and nid not in pid:
                    prev["postId"] = f"{pid},{nid}".strip(",")
                purl = prev.get("postUrl") or prev.get("url") or ""
                nurl = p.get("postUrl") or p.get("url") or ""
                if nurl and nurl not in purl:
                    prev["postUrl"] = f"{purl} {nurl}".strip()
            else:
                merged.append(p)

        merged.extend(posts_no_ts)
        merged_all.extend(merged)

    return merged_all


def is_reply(post: Dict[str, Any]) -> bool:
    """
    Determine if a post is a reply rather than a root/original post.

    Heuristics:
        - conversationId present and different from post id
        - presence of reply-specific fields like inReplyTo* keys
    """
    post_id = post.get("postId") or post.get("id")
    conv_id = post.get("conversationId")
    if conv_id and post_id and str(conv_id) != str(post_id):
        return True
    for key in ("inReplyToStatusId", "inReplyToPostId", "inReplyTo", "parentPostId"):
        if post.get(key):
            return True
    return False


def is_retweet(post: Dict[str, Any]) -> bool:
    """
    Determine if a post is a simple retweet (repost without comments).

    Quote tweets (retweets with comments) are NOT considered retweets
    and should pass this filter as they contain original content.

    Heuristics:
        - Check for isRetweet field
        - Check for retweeted_status field
        - Check for RT @username pattern in text

    Returns:
        True if post is a simple retweet, False otherwise
    """
    # Check for isRetweet field
    if post.get("isRetweet") is True:
        return True

    # Check for retweeted_status field (indicates retweet)
    if post.get("retweeted_status") or post.get("retweetedStatus"):
        return True

    # Check text for RT pattern (backup check)
    text = post.get("text") or post.get("postText") or ""
    if text.strip().startswith("RT @"):
        return True

    return False


def get_prompt(sheet_client: GoogleSheetsClient, sheet_name: str = "prompts") -> str:
    """
    Retrieve the decision prompt from the prompts worksheet.

    Strategy:
        - If the sheet has headers and a "prompt" column, use the first row's value.
        - Otherwise, use the first cell.

    Args:
        sheet_client: Authenticated GoogleSheetsClient instance.
        sheet_name: Worksheet name containing the prompt.

    Returns:
        Prompt string to send to the ChatGPT API.

    Raises:
        RuntimeError: If no prompt can be found.
    """
    worksheet = sheet_client.get_sheet(sheet_name)
    records = worksheet.get_all_records()
    if records and "prompt" in records[0] and records[0]["prompt"]:
        return str(records[0]["prompt"])

    values = worksheet.get_all_values()
    if values and values[0] and values[0][0]:
        return str(values[0][0])

    raise RuntimeError("No prompt found in the prompts sheet.")


def call_chatgpt(
    prompt: str,
    content: str,
    model: str = "gpt-5.2",
    max_tokens: int = 50,
) -> str:
    """
    Call the OpenAI Chat Completions API and return the model's content response.

    Args:
        prompt: Instruction describing acceptance criteria.
        content: Post text to evaluate.
        model: Model name to call.
        max_tokens: Maximum tokens to generate in the response.

    Returns:
        Response content string.

    Raises:
        RuntimeError: If OPENAI_API_KEY is missing or the request fails.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for ChatGPT calls.")

    # Strip whitespace and ensure proper encoding
    api_key = api_key.strip()

    # GPT-5.x models use max_completion_tokens instead of max_tokens
    if model.startswith("gpt-5"):
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            "max_completion_tokens": max_tokens,
        }
    else:
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            "max_tokens": max_tokens,
        }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }
    resp = requests.post("https://api.openai.com/v1/chat/completions", json=body, headers=headers, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"ChatGPT API error {resp.status_code}: {resp.text}")
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def is_match_via_llm(prompt: str, post_text: str) -> bool:
    """
    Send post text to the LLM and interpret a yes/no style response.

    Args:
        prompt: Decision prompt.
        post_text: Text of the post.

    Returns:
        True if the response contains 'yes' (case-insensitive), otherwise False.
    """
    reply = call_chatgpt(prompt, post_text, max_tokens=10)
    return "yes" in reply.lower()


def get_llm_decision_with_reason(prompt: str, post_text: str) -> Dict[str, Any]:
    """
    Get both decision and reason from LLM in a single call.

    Args:
        prompt: Decision prompt.
        post_text: Text of the post.

    Returns:
        Dict with 'decision' (bool), 'decision_text' (str), and 'reason' (str).
    """
    enhanced_prompt = (
        f"{prompt}\n\n"
        "After your yes/no decision, provide a brief reason (1 sentence) for your decision. "
        "Format: 'yes' or 'no', then reason on next line."
    )

    try:
        reply = call_chatgpt(enhanced_prompt, post_text, model="gpt-5.2", max_tokens=80)
        lines = reply.strip().split('\n', 1)
        decision_text = lines[0].strip().lower()
        reason = lines[1].strip() if len(lines) > 1 else "No reason provided"

        return {
            "decision": "yes" in decision_text,
            "decision_text": 1 if "yes" in decision_text else 0,
            "reason": reason
        }
    except Exception as e:
        return {
            "decision": False,
            "decision_text": 0,
            "reason": f"Error getting LLM decision: {str(e)}"
        }


def generate_reply_recommendation(post_text: str, prompt: str) -> str:
    """
    Produce a concise, humanized reply recommendation for a given post.

    Args:
        post_text: The original X post text.
        prompt: Prompt text to guide the reply generation.

    Returns:
        A short recommendation string suitable as a draft reply.
    """
    try:
        recommendation = call_chatgpt(prompt, post_text, model="gpt-5.2", max_tokens=120)
        return recommendation.strip()
    except Exception:
        return "No recommendation generated."


def generate_post_summary(post_text: str, prompt: str) -> str:
    """
    Generate a concise headline-style summary for Telegram notification.

    Args:
        post_text: Original X post content
        prompt: Summarization prompt from prompt_inuse worksheet

    Returns:
        Brief summary (10-15 words) suitable as clickable link text
    """
    try:
        summary = call_chatgpt(prompt, post_text, model="gpt-5.2", max_tokens=30)
        return summary.strip()
    except Exception as e:
        import logging
        logging.warning(f"Summary generation failed: {e}")
        # Fallback: Use first 50 characters of post
        return post_text[:50] + "..." if len(post_text) > 50 else post_text


def categorize_post(post_text: str, prompt: str) -> str:
    """
    Classify post into one of five predefined categories.

    Args:
        post_text: Original X post content
        prompt: Classification prompt from prompt_inuse worksheet

    Returns:
        Category name: "token_analysis" | "industry_analysis" |
                       "market_comment" | "tokenomic_comment" | "others"
    """
    enhanced_prompt = (
        f"{prompt}\n\n"
        "Respond with ONLY ONE of these exact category names: "
        "token_analysis, industry_analysis, market_comment, tokenomic_comment, others"
    )

    try:
        reply = call_chatgpt(enhanced_prompt, post_text, model="gpt-5.2", max_tokens=10)
        category = reply.strip().lower().replace(" ", "_")

        # Validation with fallback
        valid_categories = ["token_analysis", "industry_analysis", "market_comment",
                          "tokenomic_comment", "others"]
        return category if category in valid_categories else "others"
    except Exception as e:
        import logging
        logging.warning(f"Categorization failed: {e}")
        return "others"


def get_content_provided() -> str:
    """
    Load reference content from a separate Google Sheet (first column).

    Uses env:
        - GOOGLE_X_CONTENT_SHEET_ID: Spreadsheet ID holding reference content.
        - GOOGLE_X_CONTENT_WORKSHEET: Worksheet name (default: 'content').

    Returns:
        Concatenated string of non-empty first-column values.

    Raises:
        RuntimeError: If required envs are missing or sheet cannot be read.
    """
    content_sheet_id = os.getenv("GOOGLE_X_CONTENT_SHEET_ID")
    if not content_sheet_id:
        raise RuntimeError("GOOGLE_X_CONTENT_SHEET_ID is required for content lookup.")

    worksheet_name = os.getenv("GOOGLE_X_CONTENT_WORKSHEET", "content")
    client = GoogleSheetsClient(spreadsheet_name="content_sheet", spreadsheet_id=content_sheet_id)
    ws = client.get_sheet(worksheet_name)
    values = ws.col_values(1)
    # Skip header and join meaningful rows.
    content_lines = [v for v in values[1:] if v]
    if not content_lines and values:
        content_lines = [values[0]]
    if not content_lines:
        raise RuntimeError("No content found in the first column of the content sheet.")
    return "\n".join(content_lines)


def get_prompts_from_sheet() -> Dict[str, str]:
    """
    Load prompts from prompt_history worksheet (single source of truth).

    Reads all records with status="active" and returns a mapping of
    prompt_name to prompt_text.

    Returns:
        Dict mapping prompt names to their text content.
        e.g., {"match_prompt": "You are...", "reply_prompt": "..."}
    """
    prompts_sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_X_PROMPTS_SHEET_ID")
    if not prompts_sheet_id:
        return {}

    try:
        client = GoogleSheetsClient(spreadsheet_name="prompts_sheet", spreadsheet_id=prompts_sheet_id)
        ws = client.get_sheet("prompt_history")
        records = ws.get_all_records()

        prompt_map: Dict[str, str] = {}
        for record in records:
            if record.get("status") == "active":
                name = str(record.get("prompt_name") or "").strip()
                text = str(record.get("prompt_text") or "").strip()
                if name and text:
                    prompt_map[name] = text

        return prompt_map
    except Exception:
        return {}


def get_active_prompt_version(sheet_client: GoogleSheetsClient, prompt_name: str = "match_prompt") -> str:
    """
    Get the active prompt version from prompt_history worksheet.

    Args:
        sheet_client: Authenticated GoogleSheetsClient instance.
        prompt_name: Name of the prompt to get version for.

    Returns:
        Version ID (e.g., "v1.0") or "v1.0" as fallback.
    """
    try:
        ws = sheet_client.get_sheet("prompt_history")
        records = ws.get_all_records()
        for record in records:
            if (record.get("prompt_name") == prompt_name and
                record.get("status") == "active"):
                return record.get("version_id", "v1.0")
    except Exception:
        pass
    return "v1.0"  # fallback


def format_timestamp(ts: Any, created_at: Optional[str] = None) -> str:
    """
    Convert a timestamp to a human-readable string.
    Supports both millisecond timestamps and createdAt string format.
    
    Args:
        ts: Millisecond timestamp (int or string).
        created_at: Optional createdAt string (e.g., "Sat Jan 03 12:55:35 +0000 2026").
    
    Returns:
        Formatted string: "YYYY-MM-DD HH:MM AM/PM" or empty string if parsing fails.
    """
    dt = None
    
    # Try millisecond timestamp first
    if ts is not None:
        try:
            dt = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc)
        except Exception:
            pass
    
    # Fallback to createdAt string format
    if dt is None and created_at:
        try:
            # Parse format: "Sat Jan 03 12:55:35 +0000 2026"
            dt = datetime.strptime(created_at, "%a %b %d %H:%M:%S %z %Y")
            dt = dt.astimezone(timezone.utc)
        except Exception:
            pass
    
    if dt:
        return dt.strftime("%Y-%m-%d %I:%M %p")
    return ""


def write_all_posts_to_testing_sheet(all_posts_data: List[Dict[str, Any]]) -> int:
    """
    Write ALL scraped posts (including filtered out ones) to all_post worksheet for analysis.

    Args:
        all_posts_data: List of post dictionaries with LLM decisions

    Returns:
        Number of rows written
    """
    if not all_posts_data:
        return 0

    # New env var with fallback to legacy
    testing_sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_X_TESTING_SHEET_ID")
    testing_ws_name = os.getenv("GOOGLE_WS_ALL_POST") or os.getenv("GOOGLE_X_TESTING_WORKSHEET", "all_post")

    if not testing_sheet_id:
        print("GOOGLE_SHEET_ID not configured, skipping all_post sheet write")
        return 0

    try:
        testing_client = GoogleSheetsClient(
            spreadsheet_name="Testing Sheet",
            spreadsheet_id=testing_sheet_id,
        )

        # Try to get worksheet, create if doesn't exist
        try:
            ws = testing_client.get_sheet(testing_ws_name)
        except Exception:
            print(f"Worksheet '{testing_ws_name}' not found, creating it...")
            ws = testing_client.spreadsheet.add_worksheet(title=testing_ws_name, rows=1000, cols=25)
            print(f"Created worksheet '{testing_ws_name}'")

        existing = ws.get_all_values()

        # Add headers if sheet is empty
        if not any(cell for r in existing for cell in r):
            headers = [
                "scraped_at", "profile_url", "author", "post_content", "timestamp",
                "likes", "reposts", "replies", "bookmarks", "views",
                "llm_decision", "llm_reason", "prompt_used",
                "reply_recommendation", "post_link",
                "user_decision", "user_comment", "feedback_timestamp",
                "feedback_source", "feedback_status", "prompt_version"
            ]
            ws.append_row(headers, value_input_option="USER_ENTERED")
            existing = ws.get_all_values()

        # Build deduplication set
        existing_keys = set()
        for row in existing[1:]:
            if len(row) >= 4:  # profile_url, author, post_content, timestamp
                key = (row[1].strip(), row[2].strip(), row[3].strip())
                existing_keys.add(key)

        # Prepare rows
        rows = []
        scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %I:%M %p")

        for item in all_posts_data:
            post = item["post"]
            profile_url = (item.get("profile_url") or "").strip()
            text = (post.get("text") or post.get("postText") or "").replace("\n", " ").strip()
            author = post.get("author", {}).get("userName", "")

            # Check for duplicates
            key = (profile_url, author, text)
            if key in existing_keys:
                continue

            ts_raw = item.get("timestamp") or post.get("timestamp") or ""
            created_at = post.get("createdAt") or ""
            ts_human = format_timestamp(ts_raw, created_at)
            post_id = item.get("post_id", "") or post.get("id", "") or post.get("postId", "")
            post_link = (
                post.get("postUrl")
                or post.get("url")
                or (f"https://x.com/i/web/status/{post_id}" if post_id else "")
            )

            # Engagement metrics
            likes = post.get("likes", 0)
            reposts = post.get("retweetCount", 0)
            replies_count = post.get("replyCount", 0)
            bookmarks = post.get("bookmarkCount", 0)
            views = post.get("viewCount", 0)

            # LLM decision data
            llm_decision = item.get("llm_decision", "")
            llm_reason = item.get("llm_reason", "")
            prompt_used = item.get("prompt_used", "match_prompt")
            reply_reco = item.get("reply_reco", "")

            # Feedback columns (initially empty, to be filled by user)
            user_decision = ""  # Will be filled by user feedback (0/1)
            user_comment = ""   # Will be filled by user feedback
            feedback_timestamp = ""  # Will be set when user gives feedback
            feedback_source = ""     # Will be "telegram", "sheets", or "both"
            feedback_status = "pending"  # Default status for new posts
            prompt_version = item.get("prompt_version", "v1.0")  # Track prompt version

            rows.append([
                scraped_at, profile_url, author, text, ts_human,
                likes, reposts, replies_count, bookmarks, views,
                llm_decision, llm_reason, prompt_used,
                reply_reco, post_link,
                user_decision, user_comment, feedback_timestamp,
                feedback_source, feedback_status, prompt_version
            ])

        # Write rows
        if rows:
            ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A1")
            print(f"Wrote {len(rows)} rows to testing sheet '{testing_ws_name}'.")
            return len(rows)
        else:
            print(f"No new rows to write to testing sheet (all duplicates).")
            return 0

    except Exception as exc:
        print(f"Failed to write to testing sheet: {exc}")
        return 0


def run_scrape_and_filter() -> List[Dict[str, Any]]:
    """
    End-to-end scraper + filter:
        - Loads env and Sheets client
        - Reads profile URLs (column 6)
        - Reads decision prompt
        - Scrapes posts via Apify
        - Filters via ChatGPT

    Returns:
        List of matched post dictionaries.
    """
    load_env()
    
    # Use unified GOOGLE_SHEET_ID with fallback to legacy env vars
    sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_X_ACCOUNT_ID")
    sheet_client = GoogleSheetsClient(
        spreadsheet_name=os.getenv("GOOGLE_SPREADSHEET_NAME", "Automation Config"),
        spreadsheet_id=sheet_id,
    )
    profile_urls = get_profile_urls(sheet_client)
    max_profiles = int(os.getenv("MAX_PROFILE_URLS", "0") or 0)
    batch_start = int(os.getenv("PROFILE_BATCH_START", "0") or 0)
    batch_size = int(os.getenv("PROFILE_BATCH_SIZE", "0") or 0)
    total_profiles = len(profile_urls)

    # Apply batch slicing first if batch_size is set.
    if batch_size > 0:
        profile_urls = profile_urls[batch_start : batch_start + batch_size]
    # Then apply max_profiles cap if set.
    if max_profiles > 0:
        profile_urls = profile_urls[:max_profiles]

    print(
        f"Collected {total_profiles} unique profile URLs; "
        f"processing {len(profile_urls)} (batch_start={batch_start}, batch_size={batch_size or 'all'}, "
        f"limit={max_profiles or 'all'})."
    )

    # Build LLM prompts from the prompts sheet (or defaults).
    prompt_map = get_prompts_from_sheet()

    # Get active prompt version from prompt_history
    active_version = get_active_prompt_version(sheet_client, "match_prompt")
    print(f"Using prompt version: {active_version}")

    base_prompt = prompt_map.get(
        "match_prompt",
        'You are a professional liquid fund investor, please see if this content has the similar information as the '
        '"content provided" or is related to an industry, token analysis that would help investment. '
        'Respond with "yes" or "no".',
    )
    reply_prompt = prompt_map.get(
        "reply_prompt",
        "You craft concise, human replies for a professional liquid fund account. "
        "Read the user's post and propose a short, friendly reply that adds value, "
        "acknowledges the topic, and avoids hype. Use relevant domain knowledge if helpful. "
        "Keep it under 100 words (aim for brevity). "
        "Do not include placeholders or ask for more info. Return only the reply text.",
    )
    summary_prompt = prompt_map.get(
        "summary_prompt",
        "You are a professional financial analyst creating concise crypto/blockchain post summaries. "
        "Read the post and generate a single headline (10-15 words max) capturing the key insight. "
        'Focus on: specific token names, price levels/predictions, technical analysis findings, industry developments, '
        'or market sentiment shifts. Be specific and actionable. '
        'Examples: "BTC breaks $45K resistance with strong volume confirmation" or '
        '"Ethereum staking yields drop to 3.2% amid validator surge". '
        "Return ONLY the headline, no quotes or extra text.",
    )
    category_prompt = prompt_map.get(
        "category_prompt",
        'Classify this crypto/blockchain post into ONE category based on PRIMARY focus: '
        '1) "token_analysis" - specific token price analysis, charts, technical indicators, price predictions, support/resistance levels '
        '2) "industry_analysis" - broader blockchain industry trends, regulations, institutional adoption, protocol developments, sector-wide movements '
        '3) "market_comment" - general market sentiment, macro trends, market psychology, fear/greed indicators, overall market conditions '
        '4) "tokenomic_comment" - tokenomics analysis, token utility, emission schedules, staking mechanisms, token supply dynamics '
        '5) "others" - news announcements, educational content, or posts that don\'t fit above categories. '
        "Respond with ONLY the category name exactly as shown in quotes.",
    )
    question_prompt = prompt_map.get(
        "question_prompt",
        "You craft engaging questions as replies for a professional liquid fund account. "
        "Read the user's post and propose a thoughtful question that invites further discussion. "
        "The question should demonstrate understanding of the topic while encouraging the author "
        "to share more insights. Keep it under 100 words (aim for brevity). "
        "Do not include placeholders. Return only the question text.",
    )

    matched: List[Dict[str, Any]] = []
    matched_with_profile: List[Dict[str, Any]] = []
    all_posts_with_decisions: List[Dict[str, Any]] = []  # NEW: Track ALL posts with LLM decisions
    total_posts = 0
    recent_posts = 0
    reply_posts = 0
    post_limit = int(os.getenv("POST_RESULTS_LIMIT", "5") or 5)
    lookback_days = int(os.getenv("LOOKBACK_DAYS", "30") or 30)

    # Calculate date range for filtering
    from datetime import datetime, timedelta, timezone
    end_date = datetime.now(tz=timezone.utc)
    start_date = end_date - timedelta(days=lookback_days)
    start_date_str = start_date.strftime("%Y-%m-%d")
    end_date_str = end_date.strftime("%Y-%m-%d")

    # Extract handles from profile URLs for batch fetching
    handles = []
    url_to_handle = {}
    for url in profile_urls:
        # Extract handle from URL like https://x.com/username
        handle = url.rstrip('/').split('/')[-1]
        handles.append(handle)
        url_to_handle[handle] = url

    # Batch fetch all posts at once with date filter (much faster and more efficient!)
    print(f"\nBatch fetching posts for {len(handles)} profiles...")
    print(f"Date range: {start_date_str} to {end_date_str} ({lookback_days} day(s))")
    print(f"Handles: {', '.join(handles[:5])}{'...' if len(handles) > 5 else ''}")

    all_posts = fetch_posts(
        handles,
        max_items=post_limit * len(handles),
        start_date=start_date_str,
        end_date=end_date_str
    )
    print(f"Fetched {len(all_posts)} posts within date range from batch query")

    # Group posts by author for processing
    posts_by_handle: Dict[str, List[Dict[str, Any]]] = {}
    for post in all_posts:
        author_handle = post.get("author", {}).get("userName", "")
        if author_handle:
            posts_by_handle.setdefault(author_handle, []).append(post)

    # Process each profile's posts
    # Note: Apify API date filters may not work as expected, so we filter again here
    for idx, handle in enumerate(handles, start=1):
        url = url_to_handle[handle]
        posts = posts_by_handle.get(handle, [])

        print(f"[{idx}/{len(handles)}] Fetched {len(posts)} posts for {url}")
        total_posts += len(posts)

        # Filter by date (in case API didn't filter correctly)
        recent = [p for p in posts if is_recent_post(p, days=lookback_days)]
        print(f"   → {len(recent)} posts within last {lookback_days} day(s)")
        recent_posts += len(recent)

        if not recent:
            continue  # Skip if no recent posts

        # Filter out replies and simple retweets (safety net for API-level filtering)
        replies = [p for p in recent if is_reply(p)]
        reply_posts += len(replies)
        retweets = [p for p in recent if is_retweet(p)]

        # Combine filters - exclude both replies and retweets
        filtered_posts = [p for p in recent if not is_reply(p) and not is_retweet(p)]
        print(f"   → {len(filtered_posts)} posts after filtering out replies and retweets")

        # Merge by conversation id and 2-minute window
        to_merge = filtered_posts if filtered_posts else recent
        merged_recent = merge_threaded_posts(to_merge)
        for post in merged_recent:
            text = post.get("text") or post.get("postText") or ""
            if not text:
                continue

            # Check if post contains an X Article link (auto-pass if so)
            is_article, article_url = is_article_post(post)
            if is_article:
                # Article posts auto-pass LLM judgment
                is_match = True
                llm_result = {
                    "decision": True,
                    "decision_text": "yes",
                    "reason": f"Auto-pass: X Article detected ({article_url})"
                }
                print(f"   → Auto-pass: X Article detected ({article_url})")
            else:
                # Regular posts go through LLM judgment
                llm_result = get_llm_decision_with_reason(base_prompt, text)
                is_match = llm_result["decision"]

            # Generate reply recommendation, summary, category, and question only for matched posts
            recommendation = ""
            question_reco = ""
            summary = ""
            category = "others"
            if is_match:
                recommendation = generate_reply_recommendation(text, prompt=reply_prompt)
                question_reco = generate_reply_recommendation(text, prompt=question_prompt)
                summary = generate_post_summary(text, prompt=summary_prompt)
                category = categorize_post(text, prompt=category_prompt)

            # Add to all_posts_with_decisions (for testing sheet)
            all_posts_with_decisions.append({
                "profile_url": url,
                "post": post,
                "llm_decision": llm_result["decision_text"],
                "llm_reason": llm_result["reason"],
                "prompt_used": "match_prompt",
                "reply_reco": recommendation,
                "post_id": post.get("id") or post.get("postId") or "",
                "timestamp": post.get("timestamp"),
                "prompt_version": active_version,
            })

            # Add to matched lists only if LLM says yes (for output sheet)
            if is_match:
                matched.append(post)
                matched_with_profile.append(
                    {
                        "profile_url": url,
                        "post": post,
                        "reply_reco": recommendation,
                        "question_reco": question_reco,
                        "summary": summary,
                        "category": category,
                        "post_id": post.get("id") or post.get("postId") or "",
                        "timestamp": post.get("timestamp"),
                    }
                )

    # For now, print a simple summary and return the matches for caller use.
    print(f"Total posts fetched: {total_posts}")
    print(f"Posts within last {lookback_days} day(s): {recent_posts}")
    print(f"Replies considered (<=2 min merge per author): {reply_posts}")
    print(f"Matched (LLM yes) posts: {len(matched)}")
    for idx, post in enumerate(matched, 1):
        pid = post.get("id") or post.get("postId")
        preview = (post.get("text") or post.get("postText") or "")[:140].replace("\n", " ")
        print(f"{idx}. {pid}: {preview!r}")

    # Write ALL posts (including rejected ones) to testing sheet for analysis
    if all_posts_with_decisions:
        print(f"\nWriting {len(all_posts_with_decisions)} posts to testing sheet (all_post)...")
        testing_count = write_all_posts_to_testing_sheet(all_posts_with_decisions)
        print(f"Testing sheet write complete: {testing_count} rows")

    # Persist matches to scraped_output worksheet (llm_decision=yes posts)
    # New env var with fallback to legacy
    output_sheet_id = os.getenv("GOOGLE_SHEET_ID") or os.getenv("GOOGLE_X_SCRAPE_OUTPUT")
    output_ws_name = os.getenv("GOOGLE_WS_SCRAPED_OUTPUT") or os.getenv("GOOGLE_X_SCRAPE_OUTPUT_WORKSHEET", "scraped_output")
    if output_sheet_id and matched_with_profile:
        try:
            out_client = GoogleSheetsClient(
                spreadsheet_name="scrape_output",
                spreadsheet_id=output_sheet_id,
            )
            ws = out_client.get_sheet(output_ws_name)
            existing = ws.get_all_values()

            def normalize_row(row: List[str]) -> List[str]:
                # Shift left if leading blanks exist.
                normalized = list(row)
                while normalized and normalized[0] == "":
                    normalized = normalized[1:]
                return normalized

            # Define expected headers for scraped_output sheet
            expected_headers = [
                "profile_url", "post_content", "timestamp", "likes", "reposts", "replies", "bookmarks", "views",
                "author", "reply_recommendation", "question_recommendation", "post_link", "summary", "category", "telegram_sent_at"
            ]

            if not any(cell for r in existing for cell in r):
                ws.append_row(expected_headers, value_input_option="USER_ENTERED")
                existing = ws.get_all_values()
            else:
                # Auto-migrate: check for missing columns and insert them
                current_headers = existing[0] if existing else []
                for idx, expected_header in enumerate(expected_headers):
                    if expected_header not in current_headers:
                        col_position = idx + 1
                        print(f"Migrating scraped_output: adding column '{expected_header}' at position {col_position}")
                        ws.insert_cols([expected_header], col=col_position)
                        current_headers.insert(idx, expected_header)
                existing = ws.get_all_values()

            existing_pairs = set()
            for row in existing[1:]:
                norm = normalize_row(row)
                if len(norm) >= 3:
                    existing_pairs.add((norm[0].strip(), norm[1].strip(), norm[2].strip()))
            rows = []
            for item in matched_with_profile:
                post = item["post"]
                profile_url = (item["profile_url"] or "").strip()
                text = (post.get("text") or post.get("postText") or "").replace("\n", " ").strip()
                reply_reco = item.get("reply_reco", "")
                question_reco = item.get("question_reco", "")
                summary = item.get("summary", "")
                category = item.get("category", "others")
                ts_raw = item.get("timestamp") or post.get("timestamp") or ""
                created_at = post.get("createdAt") or ""
                ts_str = str(ts_raw) if ts_raw is not None else ""
                ts_human = format_timestamp(ts_raw, created_at)
                post_id = item.get("post_id", "")
                author = post.get("author", {}).get("userName", "")
                # Build post link - use standard format for better mobile app deep linking
                post_link = post.get("postUrl") or post.get("url")
                if not post_link and post_id:
                    if author:
                        # Standard format triggers iOS/Android Universal Links for X app
                        post_link = f"https://x.com/{author}/status/{post_id}"
                    else:
                        post_link = f"https://x.com/i/web/status/{post_id}"

                # Extract engagement metrics and author
                likes = post.get("likes", 0)
                reposts = post.get("retweetCount", 0)
                replies = post.get("replyCount", 0)
                bookmarks = post.get("bookmarkCount", 0)
                views = post.get("viewCount", 0)
                author = post.get("author", {}).get("userName", "")

                key = (profile_url, text, ts_str)
                if key in existing_pairs:
                    continue
                rows.append([profile_url, text, ts_human, likes, reposts, replies, bookmarks, views,
                            author, reply_reco, question_reco, post_link, summary, category, ""])
            if rows:
                ws.append_rows(rows, value_input_option="USER_ENTERED", table_range="A1")
            print(f"Wrote {len(rows)} rows to output sheet '{output_ws_name}'.")
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to write scrape output: {exc}")

    # Add matched posts with reply recommendations to the review queue
    if matched_with_profile:
        try:
            from x_auto.review.queue_manager import add_to_queue

            queue_items = []
            for item in matched_with_profile:
                post = item["post"]
                text = (post.get("text") or post.get("postText") or "").replace("\n", " ").strip()
                author = post.get("author", {}).get("userName", "")
                post_id = item.get("post_id", "")
                post_link = post.get("postUrl") or post.get("url") or ""
                if not post_link and post_id:
                    if author:
                        post_link = f"https://x.com/{author}/status/{post_id}"
                    else:
                        post_link = f"https://x.com/i/web/status/{post_id}"

                reply_reco = item.get("reply_reco", "")
                question_reco = item.get("question_reco", "")
                if reply_reco:
                    queue_items.append({
                        "post_link": post_link,
                        "author": author,
                        "post_content": text,
                        "reply_recommendation": reply_reco,
                        "question_recommendation": question_reco,
                        "post_id": post_id,
                    })

            if queue_items:
                added = add_to_queue(queue_items)
                print(f"[Reply Queue] Added {added} items to review queue")
        except Exception as exc:
            print(f"[Reply Queue] Failed to add items: {exc}")
            # Don't fail the entire job if reply queue fails

    # Send Telegram notification with categorized summaries
    if os.getenv("ENABLE_TELEGRAM_NOTIFICATIONS", "true").lower() == "true":
        try:
            from x_auto.notifications.telegram_bot import send_daily_summary
            print(f"\n[Telegram] Sending daily summary with {len(matched_with_profile)} posts...")
            success = send_daily_summary(matched_with_profile)
            if success:
                print("[Telegram] Notification sent successfully")
            else:
                print("[Telegram] Failed to send notification (see logs above)")
        except Exception as e:
            import logging
            logging.error(f"Telegram notification failed: {e}", exc_info=True)
            print(f"[Telegram] Error: {e}")
            # Don't fail the entire job if Telegram fails

    return matched


if __name__ == "__main__":
    run_scrape_and_filter()

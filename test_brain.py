"""Standalone test for brain API + LLM context generation."""
import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

import requests
from x_auto.brain.client import BrainClient

SAMPLE_POST = """\
Just published a deep dive on how DeFi protocols are evolving beyond simple AMMs.
The composability of liquidity layers is creating new primitives we haven't seen before.
Yield optimization is becoming more about capital efficiency than raw APY chasing.
Thread below 👇
"""


def check_connectivity(client: BrainClient) -> None:
    """Only check brain API connectivity (no OpenAI key needed)."""
    print(f"Brain API URL : {client.base_url}")
    print(f"Brain enabled : {client.enabled}")
    print(f"API key       : {'SET' if client.api_key else 'MISSING'}")
    print("-" * 60)

    if not client.enabled:
        print("[CHECK] FAIL - Brain is disabled (BRAIN_ENABLED != true)")
        sys.exit(1)
    if not client.base_url or not client.api_key:
        print("[CHECK] FAIL - BRAIN_API_URL or BRAIN_API_KEY not set")
        sys.exit(1)

    try:
        resp = requests.post(
            f"{client.base_url}/search",
            json={"query": "test", "mode": "hybrid", "limit": 1},
            headers={"X-API-Key": client.api_key, "Content-Type": "application/json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        total = data.get("total", 0)
        results = data.get("results", [])
        print(f"[CHECK] OK - API responded, total={total}, results={len(results)}")
    except requests.exceptions.ConnectionError as e:
        print(f"[CHECK] FAIL - Connection error: {e}")
        sys.exit(1)
    except requests.exceptions.HTTPError as e:
        print(f"[CHECK] FAIL - HTTP {e.response.status_code}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"[CHECK] FAIL - {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Test brain API + LLM context generation")
    parser.add_argument("--check", action="store_true", help="Only check brain API connectivity (no OpenAI key needed)")
    args = parser.parse_args()

    client = BrainClient()

    if args.check:
        check_connectivity(client)
        return

    from x_auto.workflow.scrape_filter import call_chatgpt

    print(f"Brain API URL: {client.base_url}")
    print(f"Brain enabled: {client.enabled}")
    print(f"Limit: {client.limit}")
    print("-" * 60)
    print("Sample post:")
    print(SAMPLE_POST)
    print("-" * 60)

    result = client.get_note_context(SAMPLE_POST, call_chatgpt)

    if result is None:
        print("[RESULT] No result returned (brain disabled, no URL, or no matching notes)")
    else:
        print(f"[RESULT] Related notes found: {result['total']}")
        print()
        print(result["brain_context"])

if __name__ == "__main__":
    main()

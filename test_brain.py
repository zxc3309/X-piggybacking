"""Standalone test for brain API + LLM context generation."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from x_auto.workflow.scrape_filter import call_chatgpt
from x_auto.brain.client import BrainClient

SAMPLE_POST = """\
Just published a deep dive on how DeFi protocols are evolving beyond simple AMMs.
The composability of liquidity layers is creating new primitives we haven't seen before.
Yield optimization is becoming more about capital efficiency than raw APY chasing.
Thread below 👇
"""

def main():
    client = BrainClient()
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

#!/usr/bin/env python3
"""
測試 X Article 偵測功能

測試案例：
1. t.co URL 展開功能
2. Article URL 偵測
3. 非 Article 貼文正確回傳 False
"""
from x_auto.scrapers.article_detector import (
    expand_tco_url,
    contains_tco_link,
    extract_tco_urls,
    is_article_url,
    is_article_post,
)

print("=" * 70)
print("測試 X Article 偵測功能")
print("=" * 70)
print()

# ===== Test 1: URL pattern detection =====
print("【測試 1】URL 模式偵測")
print("-" * 70)

test_texts = [
    ("包含 t.co 連結: https://t.co/14zSYHXGZv", True, ["https://t.co/14zSYHXGZv"]),
    ("沒有連結的純文字", False, []),
    ("多個連結: https://t.co/abc123 和 https://t.co/xyz789", True, ["https://t.co/abc123", "https://t.co/xyz789"]),
    ("http 版本: http://t.co/testurl", True, ["http://t.co/testurl"]),
    ("其他連結 https://example.com", False, []),
]

for text, expected_contains, expected_urls in test_texts:
    contains = contains_tco_link(text)
    urls = extract_tco_urls(text)
    status = "✓" if contains == expected_contains and urls == expected_urls else "✗"
    print(f"{status} 文字: \"{text[:50]}...\"")
    print(f"  → 包含 t.co: {contains} (預期: {expected_contains})")
    print(f"  → 提取 URLs: {urls}")
    print()

# ===== Test 2: Article URL detection =====
print("【測試 2】Article URL 偵測")
print("-" * 70)

article_urls = [
    ("https://x.com/i/article/2012144868475170816", True),
    ("https://x.com/i/article/123456789", True),
    ("https://x.com/username/status/123456789", False),
    ("https://twitter.com/i/article/123456789", False),  # twitter.com not x.com
    ("https://x.com/i/spaces/123456789", False),
    ("https://example.com/article/123", False),
]

for url, expected in article_urls:
    result = is_article_url(url)
    status = "✓" if result == expected else "✗"
    print(f"{status} URL: {url}")
    print(f"  → is_article_url: {result} (預期: {expected})")
    print()

# ===== Test 3: t.co URL expansion (live test) =====
print("【測試 3】t.co URL 展開 (需要網路)")
print("-" * 70)

# Known test URLs - these may change over time
test_tco_urls = [
    # This is a known Article URL from the plan
    "https://t.co/14zSYHXGZv",
]

for tco_url in test_tco_urls:
    print(f"展開: {tco_url}")
    expanded = expand_tco_url(tco_url, timeout=10)
    if expanded:
        print(f"  → 展開結果: {expanded}")
        is_article = is_article_url(expanded)
        print(f"  → 是否為 Article: {is_article}")
    else:
        print(f"  → 展開失敗（可能是網路問題或 URL 已失效）")
    print()

# ===== Test 4: is_article_post function =====
print("【測試 4】is_article_post 整合測試")
print("-" * 70)

test_posts = [
    # Post with known Article link (from plan)
    {
        "text": "Check out my new article: https://t.co/14zSYHXGZv",
        "postId": "test1"
    },
    # Post with no links
    {
        "text": "Just a regular post without any links",
        "postId": "test2"
    },
    # Post with non-Article link (generic t.co)
    {
        "text": "Visit this site: https://t.co/aBcDeFgHiJ",
        "postId": "test3"
    },
    # Empty post
    {
        "text": "",
        "postId": "test4"
    },
    # Post using postText field instead of text
    {
        "postText": "Another article: https://t.co/14zSYHXGZv",
        "postId": "test5"
    },
]

for post in test_posts:
    text = post.get("text") or post.get("postText") or "(empty)"
    print(f"貼文: \"{text[:60]}...\"")
    is_article, article_url = is_article_post(post)
    print(f"  → is_article: {is_article}")
    print(f"  → article_url: {article_url}")
    print()

# ===== Summary =====
print("=" * 70)
print("測試完成！")
print()
print("注意事項：")
print("1. t.co 展開測試需要網路連線")
print("2. t.co 連結可能會過期或失效")
print("3. 如果 Article 偵測失敗，會降級為一般 LLM 判斷")
print("=" * 70)

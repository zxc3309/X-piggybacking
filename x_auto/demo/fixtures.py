"""
Mock data for the single-post demo deep dive.

The demo centers on ONE real X post — Andrej Karpathy's "LLM Knowledge Bases"
thread (https://x.com/karpathy/status/2039805659525644595) — and shows the
full pipeline output for it: LLM filter reasoning, category, Second Brain
retrieval, editable reply draft + alternative question, and a "Reply on X"
button that links to x.com/intent/tweet with the REAL post ID so clicking
actually opens X's reply composer.

The post body is real, quoted exactly. The LLM reasoning, Second Brain notes,
and drafted replies are all hand-written fiction crafted to be plausible for
Bill Hsu (VC at AppWorks, builds a personal Second Brain with cesecondbrain-api).
"""

from __future__ import annotations


# The real X post we're targeting
REAL_POST_ID = "2039805659525644595"
REAL_POST_URL = f"https://x.com/karpathy/status/{REAL_POST_ID}"


DEMO_ITEM: dict = {
    "queue_id": "demo-karpathy-kb",
    "post_id": REAL_POST_ID,
    "post_link": REAL_POST_URL,
    "author": "karpathy",
    "author_display": "Andrej Karpathy",
    "author_verified": True,
    "author_bio": "Previously Director of AI @ Tesla, founding team @ OpenAI, PhD @ Stanford.",
    "post_content": (
        "LLM Knowledge Bases\n\n"
        "Something I'm finding very useful recently: using LLMs to build "
        "personal knowledge bases for various topics of research interest. "
        "In this way, a large fraction of my recent token throughput is "
        "going less into manipulating code, and more into manipulating "
        "knowledge (stored as markdown and images). The latest LLMs are "
        "quite good at it. So:\n\n"
        "Data ingest:\n"
        "I index source documents (articles, papers, repos, datasets, "
        "images, etc.) into a raw/ directory, then I use an LLM to "
        "incrementally \"compile\" a wiki, which is just a collection of "
        ".md files in a directory structure. The wiki includes summaries "
        "of all the data in raw/, backlinks, and then it categorizes data "
        "into concepts, writes articles for them, and links them all. To "
        "convert web articles into .md files I like to use the Obsidian "
        "Web Clipper extension, and then I also use a hotkey to download "
        "all the related images to local so that my LLM can easily "
        "reference them.\n\n"
        "IDE:\n"
        "I use Obsidian as the IDE \"frontend\" where I can view the raw "
        "data, the compiled wiki, and the derived visualizations. "
        "Important to note that the LLM writes and maintains all of the "
        "data of the wiki, I rarely touch it directly. I've played with a "
        "few Obsidian plugins to render and view data in other ways "
        "(e.g. Marp for slides).\n\n"
        "Q&A:\n"
        "Where things get interesting is that once your wiki is big "
        "enough (e.g. mine on some recent research is ~100 articles and "
        "~400K words), you can ask your LLM agent all kinds of complex "
        "questions against the wiki, and it will go off, research the "
        "answers, etc. I thought I had to reach for fancy RAG, but the "
        "LLM has been pretty good about auto-maintaining index files and "
        "brief summaries of all the documents and it reads all the "
        "important related data fairly easily at this ~small scale.\n\n"
        "Output:\n"
        "Instead of getting answers in text/terminal, I like to have it "
        "render markdown files for me, or slide shows (Marp format), or "
        "matplotlib images, all of which I then view again in Obsidian. "
        "You can imagine many other visual output formats depending on "
        "the query. Often, I end up \"filing\" the outputs back into the "
        "wiki to enhance it for further queries. So my own explorations "
        "and queries always \"add up\" in the knowledge base.\n\n"
        "Linting:\n"
        "I've run some LLM \"health checks\" over the wiki to e.g. find "
        "inconsistent data, impute missing data (with web searchers), "
        "find interesting connections for new article candidates, etc., "
        "to incrementally clean up the wiki and enhance its overall data "
        "integrity. The LLMs are quite good at suggesting further "
        "questions to ask and look into.\n\n"
        "Extra tools:\n"
        "I find myself developing additional tools to process the data, "
        "e.g. I vibe coded a small and naive search engine over the wiki, "
        "which I both use directly (in a web ui), but more often I want "
        "to hand it off to an LLM via CLI as a tool for larger queries.\n\n"
        "Further explorations:\n"
        "As the repo grows, the natural desire is to also think about "
        "synthetic data generation + finetuning to have your LLM \"know\" "
        "the data in its weights instead of just context windows.\n\n"
        "TLDR: raw data from a given number of sources is collected, then "
        "compiled by an LLM into a .md wiki, then operated on by various "
        "CLIs by the LLM to do Q&A and to incrementally enhance the wiki, "
        "and all of it viewable in Obsidian. You rarely ever write or "
        "edit the wiki manually, it's the domain of the LLM. I think "
        "there is room here for an incredible new product instead of a "
        "hacky collection of scripts."
    ),
    "created_at": "Apr 3, 2026 · 4:42 AM UTC",
    "views": "19.2M",
    "likes": "54K",
    "reposts": "8.3K",
    "bookmarks": "99K",
    "replies_count": "2.6K",

    # ── Pipeline output ──
    "category": "product_vision",
    "llm_filter_reasoning": (
        "Karpathy is describing almost exactly the Second Brain workflow "
        "this user has been building (cesecondbrain-api — LLM-compiled "
        "markdown wiki queried via CLI). Extremely high overlap with 3 "
        "active notes in the user's vault and the user's own open-source "
        "project. The 'room for an incredible new product' closing line "
        "is an open invitation for thoughtful builder replies. 19.2M views "
        "means visibility is high — replying early is worth the effort."
    ),
    "llm_filter_confidence": 0.97,

    "brain_notes": [
        {
            "title": "cesecondbrain-api — architecture notes",
            "source": "Obsidian · projects/secondbrain/2026-03-14.md",
            "snippet": (
                "My Second Brain API is ~exactly the shape Karpathy is "
                "describing: raw/ directory of source docs, LLM-compiled "
                "wiki of .md files with backlinks, CLI tools for Q&A. "
                "The one thing I added that he hasn't mentioned: a FastAPI "
                "layer so other tools (like the X auto-reply bot) can "
                "query the wiki programmatically. That's the missing "
                "piece for turning this from a personal workflow into a "
                "product — you need the knowledge base to be callable by "
                "OTHER agents, not just the one who wrote it."
            ),
            "relevance": 0.94,
        },
        {
            "title": "Why Obsidian-as-IDE is the right frontend for agents",
            "source": "Obsidian · thinking/tools/2026-02-08.md",
            "snippet": (
                "The reason Obsidian wins here isn't the editor — it's "
                "that the storage format IS the data model. Plain .md "
                "files in a directory, no proprietary DB, no vendor "
                "lock-in. An LLM agent can read, write, and reason about "
                "your knowledge using the same primitives as you. Every "
                "'AI note-taking app' I've tried builds a walled garden "
                "on top of a DB — they all feel wrong because the agent "
                "can't see the full shape of the data."
            ),
            "relevance": 0.88,
        },
        {
            "title": "The synthetic-data-then-finetune endgame",
            "source": "Obsidian · thinking/llm/2026-01-22.md",
            "snippet": (
                "The natural progression for personal knowledge bases: "
                "(1) raw docs → (2) LLM-compiled wiki → (3) synthetic "
                "Q&A pairs generated from the wiki → (4) finetune a "
                "small local model on the pairs. Stage 4 is where the "
                "knowledge stops being context and starts being "
                "capability. The hard part is not the finetune — it's "
                "the quality filter on the synthetic data. That's where "
                "most 'finetune on your notes' projects die."
            ),
            "relevance": 0.81,
        },
    ],

    # ── The generated reply (this is what gets sent to X) ──
    "reply_variants": [
        (
            "This is ~exactly what I've been building for the last 6 "
            "months (cesecondbrain-api). One thing I'd add: the unlock "
            "isn't the wiki itself — it's making the wiki callable by "
            "OTHER agents via an API. Once a different tool (a research "
            "bot, an X auto-reply, a writing assistant) can query your "
            "knowledge base, it stops being a personal workflow and "
            "starts being infrastructure. The 'incredible new product' "
            "you're hinting at is probably the protocol layer, not the "
            "editor."
        ),
        (
            "Agree the Obsidian-as-IDE choice is load-bearing — the "
            "reason it works is that the storage format IS the data "
            "model. Plain .md in a directory, no walled garden. Every "
            "'AI note-taking app' I've tried fails here because the "
            "agent can't see the full shape of the data. The next step "
            "I'm chasing: making the wiki callable by other agents over "
            "an API, so the knowledge base becomes infrastructure "
            "instead of a personal workflow."
        ),
        (
            "The 'hacky collection of scripts → incredible new product' "
            "gap is real. I've been building this exact thing as an "
            "open-source API (cesecondbrain-api) and the lesson so far: "
            "the product isn't the wiki compiler, it's the query "
            "interface that lets OTHER agents plug in. Karpathy-style "
            "personal use → research agents / writing assistants / "
            "reply bots hitting the same brain. That's where it stops "
            "being a hack."
        ),
    ],

    "question_variant": (
        "Curious where you land on the synthetic-data → finetune step. "
        "Is the plan to keep it all in context, or to eventually bake "
        "the wiki into model weights? Feels like the quality filter on "
        "the synthetic Q&A is where most 'finetune on your notes' "
        "projects die."
    ),
}


DEMO_CATEGORIES: dict[str, dict] = {
    "product_vision": {
        "label": "Product vision",
        "color": "#b97bd4",
        "short_description": "Founder/builder sharing a vision or workflow others might adopt.",
    },
}


# Pipeline steps — kept for a small info panel, not a full visualization
PIPELINE_STEPS: list[dict] = [
    {"id": "scrape",    "label": "Scrape",    "sublabel": "Apify"},
    {"id": "filter",    "label": "Filter",    "sublabel": "LLM"},
    {"id": "categorize","label": "Categorize","sublabel": "LLM"},
    {"id": "enrich",    "label": "Enrich",    "sublabel": "Second Brain"},
    {"id": "generate",  "label": "Generate",  "sublabel": "LLM"},
    {"id": "review",    "label": "Review",    "sublabel": "You (now)"},
]

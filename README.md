# X Automation Starter

This project automates X (Twitter) monitoring: scrapes posts from target profiles, evaluates them with AI, categorizes content, generates reply recommendations, and sends daily summaries via Telegram.

## Features
- **Profile monitoring** - Track X handles from Google Sheets
- **Apify scraping** - Fetch recent posts via `scraper_one/x-profile-posts-scraper`
- **AI-powered filtering** - LLM evaluates each post for relevance (decision recorded as 0/1)
- **Post categorization** - Auto-categorize posts (token_analysis, industry_analysis, market_comment, etc.)
- **Smart summaries** - Generate concise headlines for quick review
- **Reply generation** - AI-powered reply recommendations
- **Telegram notifications** - Daily summaries organized by category with emoji indicators
- **Google Sheets logging** - Track all posts and decisions
- **Scheduled execution** - Run on Railway, cron, or GitHub Actions

## Setup

### Requirements
- Python 3.10+
- Virtual environment recommended

### Credentials Needed
| Service | Env Variable | How to Get |
|---------|--------------|------------|
| Apify | `APIFY_TOKEN` | [console.apify.com](https://console.apify.com/) > Settings > Integrations |
| Google | `GOOGLE_SERVICE_ACCOUNT_PATH` | [Google Cloud Console](https://console.cloud.google.com/) > Service Account > JSON key |
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) > API keys |
| X API | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | [developer.twitter.com](https://developer.twitter.com/) (only needed for posting) |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | [@BotFather](https://t.me/botfather) for token, [@userinfobot](https://t.me/userinfobot) for chat ID |

### Quick Start
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Share Google Sheets with service account email (from JSON file)

# 4. Run
python main.py
```

## Usage

```bash
# Run main workflow (scrape + filter + notify)
python main.py

# Scrape and store posts only
python scrape_and_store.py

# Update LLM prompts from Google Sheets
python scripts/update_prompt.py
```

## Architecture

```
Google Sheets (profiles)
        │
        ▼
   Apify Scraper ──────► Raw Posts
        │
        ▼
   LLM Filter (OpenAI) ──► Scored Posts
        │
        ▼
   Categorizer ──────────► Categorized Posts
        │
        ├──► Google Sheets (logs)
        └──► Telegram (daily summary)
```

## Structure
- `x_auto/config` - Environment loading and credential helpers
- `x_auto/sheets` - Google Sheets read/write utilities
- `x_auto/scrapers` - Apify integration for fetching posts
- `x_auto/matcher` - Keyword detection, scoring, template selection
- `x_auto/reply_engine` - Reply message construction
- `x_auto/x_api` - X API client for posting replies
- `x_auto/notifications` - Telegram bot integration for daily summaries
- `x_auto/workflow` - End-to-end pipeline orchestration (scraping, filtering, LLM evaluation)
- `x_auto/utils` - Shared helpers (logging, rate limiting, ID tracking)
- `scripts/` - Utility scripts for prompt updates and maintenance

## Google Sheets Structure

**Single unified sheet** with these worksheets:
- `profiles` (or `Researcher`) - Input: X handles to monitor
- `prompts` (or `prompt_inuse`) - Input: LLM prompts for filtering/replies/categorization
- `all_post` - Output: All scraped posts with llm_decision (0/1), reasons, engagement metrics
- `scraped_output` - Output: Matched posts (llm_decision=1) with reply recommendations, summaries, categories

## Telegram Notifications

Posts grouped by category (Token Analysis, Industry Analysis, Market Comment, etc.) with direct links to X posts.

**Enable:** Set `ENABLE_TELEGRAM_NOTIFICATIONS=true` in `.env`

## Prompt Iteration Guide

The system uses `prompt_history` as the **single source of truth** for all prompts. The scraper reads directly from `prompt_history` where `status="active"`, eliminating sync issues.

### View Current Prompt
```bash
python scripts/update_prompt.py --show-current
```

### Update Prompt Workflow
1. Run the interactive update tool:
   ```bash
   python scripts/update_prompt.py match_prompt
   ```

2. The tool displays:
   - Current prompt content
   - Recent accuracy metrics
   - False positive/negative examples

3. After editing, the tool automatically:
   - Creates a new version (status: testing)
   - Tests on historical data
   - Shows comparison results

4. Choose whether to activate the new version

### Manual Version Activation
```bash
python scripts/update_prompt.py --activate v1.2
```

### Compare Versions
```bash
python scripts/update_prompt.py --compare v1.0 v1.1
```

### Analyze Feedback
```bash
# See accuracy, FP/FN rates
python scripts/analyze_feedback.py

# Show only false positives (LLM accepted, you rejected)
python scripts/analyze_feedback.py --fp

# Show only false negatives (LLM rejected, you accepted)
python scripts/analyze_feedback.py --fn
```

### Prompt Types
- `match_prompt` - Determines if a post is relevant
- `reply_prompt` - Generates reply suggestions
- `summary_prompt` - Generates summaries
- `category_prompt` - Categorizes posts

### Prompt History Structure
Each `prompt_name` has independent version management in `prompt_history`:
- `version_id` - Version identifier (e.g., v1.0, v1.1)
- `status` - One of: `active`, `testing`, `archived`
- `accuracy`, `false_positive_rate`, `false_negative_rate` - Performance metrics

Only one version per `prompt_name` can have `status="active"` at a time.

## Next Steps
- Review and adjust LLM prompts in the `prompts` worksheet for optimal filtering
- Monitor API costs and performance (Apify, OpenAI usage)
- Set `ENABLE_X_POSTING=true` when ready to post live replies to X

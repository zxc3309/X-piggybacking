# X Automation Starter

This project automates X (Twitter) monitoring: scrapes posts from target profiles, evaluates them with AI, categorizes content, generates reply recommendations, queues them for human review, and auto-posts approved replies.

## Features

- **Profile monitoring** - Track X handles from Google Sheets
- **Apify scraping** - Fetch recent posts via `scraper_one/x-profile-posts-scraper`
- **Multi-AI provider support** - Switch between OpenAI, Anthropic Claude, Google Gemini via Google Sheet or env var
- **AI-powered filtering** - LLM evaluates each post for relevance (decision recorded as 0/1)
- **Post categorization** - Auto-categorize posts (token_analysis, industry_analysis, market_comment, etc.)
- **Smart summaries** - Generate concise headlines for quick review
- **Reply generation** - AI-powered reply recommendations
- **Question recommendations** - Suggested follow-up questions for engagement
- **Review Dashboard** - Web UI for approve/reject/edit reply candidates
- **Auto-sender** - Posts approved replies to X with daily limits (17/day for X Free tier)
- **Second Brain integration** - Query personal knowledge base (cesecondbrain-api) for related notes, enrich replies with your own perspective
- **Telegram notifications** - Daily summaries organized by category with emoji indicators
- **Google Sheets logging** - Track all posts, decisions, and reply queue
- **Scheduled execution** - Run on Railway with APScheduler (daily scrape + 5-min reply checks)

## Setup

### Requirements
- Python 3.10+
- Virtual environment recommended

### Credentials Needed
| Service | Env Variable | How to Get |
|---------|--------------|------------|
| Apify | `APIFY_TOKEN` | [console.apify.com](https://console.apify.com/) > Settings > Integrations |
| Google Sheets | `GOOGLE_SERVICE_ACCOUNT_PATH` or `GOOGLE_SHEETS_CREDENTIALS_BASE64` | [Google Cloud Console](https://console.cloud.google.com/) > Service Account > JSON key |
| OpenAI | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) > API keys |
| Anthropic | `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) > API keys |
| Google Gemini | `GOOGLE_API_KEY` | [aistudio.google.com](https://aistudio.google.com/) > API keys |
| X API | `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` | [developer.twitter.com](https://developer.twitter.com/) (only needed for posting) |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | [@BotFather](https://t.me/botfather) for token, [@userinfobot](https://t.me/userinfobot) for chat ID |
| Second Brain | `BRAIN_API_URL`, `BRAIN_API_KEY` | Your cesecondbrain-api instance |

### Quick Start
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 3. Share Google Sheets with service account email (from JSON file)

# 4. Run the web server (includes scheduler + dashboard)
python app.py
```

## Usage

```bash
# Start web server with scheduler and review dashboard
python app.py
# Dashboard available at: http://localhost:8080/dashboard

# Run scrape workflow only (no server)
python main.py

# Scrape and store posts only
python scrape_and_store.py

# Manual scrape trigger via scheduler
python scheduler.py --run-now

# Update LLM prompts from Google Sheets
python scripts/update_prompt.py
```

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check for Railway |
| `/trigger` | POST | Manually trigger scrape job |
| `/status` | GET | Scheduler status and config |
| `/dashboard/` | GET | Review dashboard (mounted app) |

## Architecture

```
Google Sheets (Researcher)
        │
        ▼
   Apify Scraper ──────► Raw Posts
        │
        ▼
   LLM Filter (OpenAI/Claude/Gemini) ──► Scored Posts
        │
        ▼
   Categorizer + Reply Generator ◄── Second Brain (cesecondbrain-api)
        │
        ├──► all_post (all decisions)
        ├──► scraped_output (matched only)
        ├──► reply_queue (pending approval)
        └──► Telegram (daily summary)
                │
        ┌───────┴───────┐
        ▼               ▼
   Review Dashboard    Auto-Sender (5min)
   (human approval)    (posts to X API)
```

## Structure
- `app.py` - FastAPI web server with scheduler and mounted dashboard
- `scheduler.py` - APScheduler for daily scrape and reply auto-sender jobs
- `x_auto/config` - Environment loading and credential helpers
- `x_auto/sheets` - Google Sheets read/write utilities
- `x_auto/scrapers` - Apify integration for fetching posts
- `x_auto/matcher` - Keyword detection, scoring, template selection
- `x_auto/reply_engine` - Reply message construction
- `x_auto/x_api` - X API client for posting replies
- `x_auto/llm` - Multi-provider LLM abstraction (OpenAI, Anthropic, Google)
- `x_auto/notifications` - Telegram bot integration for daily summaries
- `x_auto/workflow` - End-to-end pipeline orchestration (scraping, filtering, LLM evaluation)
- `x_auto/review` - Review dashboard and queue management
- `x_auto/brain` - Second Brain (cesecondbrain-api) client for knowledge base search
- `x_auto/feedback` - Prompt version management and feedback analysis
- `x_auto/utils` - Shared helpers (logging, rate limiting, ID tracking)
- `scripts/` - Utility scripts for prompt updates and maintenance

## Google Sheets Structure

**Single unified sheet** with these worksheets:

| Worksheet | Env Variable | Purpose |
|-----------|--------------|---------|
| `Researcher` | `GOOGLE_WS_PROFILES` | Input: X handles to monitor |
| `prompt_inuse` | `GOOGLE_WS_PROMPTS` | Input: Active LLM prompts (legacy) |
| `prompt_history` | (hardcoded) | Prompt version management (single source of truth) |
| `all_post` | `GOOGLE_WS_ALL_POST` | Output: All posts with LLM decisions (0/1) |
| `scraped_output` | `GOOGLE_WS_SCRAPED_OUTPUT` | Output: Matched posts only (llm_decision=1) |
| `reply_queue` | `GOOGLE_WS_REPLY_QUEUE` | Review queue for human approval |
| `llm_config` | `GOOGLE_WS_LLM_CONFIG` | Runtime LLM provider/model switching |

### Worksheet Columns

**Researcher** (profiles to monitor):
- `handle` - X username (without @)
- `name` - Display name
- `category` - Profile category

**all_post** (all scraped posts):
- `post_id`, `author`, `text`, `created_at`
- `llm_decision` (0/1), `llm_reason`
- `engagement_score`, `likes`, `retweets`, `replies`
- `brain_context`, `related_notes_count` - Second Brain analysis and match count

**scraped_output** (matched posts):
- Same as all_post, plus:
- `category`, `summary`, `reply_recommendation`, `question_recommendation`
- `brain_context`, `related_notes_count` - Second Brain analysis and match count

**reply_queue** (pending approvals):
- `queue_id`, `post_id`, `post_link`, `author`
- `original_reply`, `edited_reply`
- `status` (pending/approved/rejected/sent/failed/conversation_blocked)
- `approved_at`, `sent_at`, `error_message`
- `brain_context`, `related_notes_count` - Second Brain analysis and match count
- `bookmarks`, `views` - Post engagement metrics from X

## Environment Variables

### Required - Google Sheets
```bash
GOOGLE_SHEET_ID=your_google_sheet_id
GOOGLE_SERVICE_ACCOUNT_PATH=/path/to/service_account.json        # Local development
# GOOGLE_SHEETS_CREDENTIALS_BASE64=base64_encoded_json           # Railway/cloud deployment (alternative)
```

### Required - AI/LLM
```bash
LLM_PROVIDER=openai                      # Options: openai, anthropic, google
OPENAI_API_KEY=your_openai_api_key        # Required if LLM_PROVIDER=openai
ANTHROPIC_API_KEY=your_anthropic_api_key  # Required if LLM_PROVIDER=anthropic
GOOGLE_API_KEY=your_google_api_key        # Required if LLM_PROVIDER=google
```

> **Tip:** Set all three API keys in Railway so you can switch providers at any time via the `llm_config` Google Sheet worksheet without redeploying.

#### Supported Models

| Provider | Default Model | Other Options |
|----------|--------------|---------------|
| OpenAI | `gpt-5.4-mini` | `gpt-5.4`, `gpt-5.4-nano`, `gpt-5.2`, `o3`, `o4-mini`, `gpt-4.1`, `gpt-4o` |
| Anthropic | `claude-sonnet-4-6` | `claude-opus-4-6`, `claude-haiku-4-5`, `claude-sonnet-4-20250514` |
| Google | `gemini-2.5-pro` | `gemini-2.5-flash`, `gemini-2.0-flash` |

#### Runtime Switching via Google Sheet

Add a `llm_config` worksheet to your Google Sheet to switch provider/model without redeploying:

| setting | value |
|---------|-------|
| provider | anthropic |
| model | claude-sonnet-4-6 |

The pipeline reads this at the start of each run. If the worksheet doesn't exist, it falls back to env vars.

### Required - Apify
```bash
APIFY_TOKEN=your_apify_token
APIFY_ACTOR_ID=scraper_one/x-profile-posts-scraper
```

### Required - Telegram
```bash
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Optional - AI/LLM
```bash
LLM_MODEL=                                # Override default model (leave empty for provider default)
GOOGLE_WS_LLM_CONFIG=llm_config           # LLM config worksheet name (default: llm_config)
```

### Optional - Google Sheets Worksheets
```bash
GOOGLE_WS_PROFILES=Researcher
GOOGLE_WS_PROMPTS=prompt_inuse
GOOGLE_WS_ALL_POST=all_post
GOOGLE_WS_SCRAPED_OUTPUT=scraped_output
GOOGLE_WS_REPLY_QUEUE=reply_queue
```

### Optional - Scraping
```bash
MAX_PROFILE_URLS=0              # Max profiles to process (0 = all)
POST_RESULTS_LIMIT=5            # Posts per profile
LOOKBACK_DAYS=30                # Only fetch posts from last N days
PROFILE_BATCH_START=0           # Batch start index
PROFILE_BATCH_SIZE=0            # Batch size (0 = all)
```

### Optional - Scheduler
```bash
COLLECTION_SCHEDULE_HOUR=8      # Daily scrape time (Asia/Taipei)
COLLECTION_SCHEDULE_MINUTE=0
```

### Optional - Telegram
```bash
ENABLE_TELEGRAM_NOTIFICATIONS=true
REVIEW_DASHBOARD_URL=https://your-app.railway.app/dashboard  # For notification links
```

### Optional - Second Brain (cesecondbrain-api)
```bash
BRAIN_API_URL=https://brain.example.com   # Your cesecondbrain-api URL
BRAIN_API_KEY=your_brain_api_key
BRAIN_SEARCH_LIMIT=5                      # Max related notes to retrieve (default: 5)
BRAIN_ENABLED=true                        # Set to "false" to disable
```

### Optional - X API (for posting)
```bash
ENABLE_X_POSTING=false          # Set to "true" to enable live posting
X_API_KEY=your_x_api_key
X_API_SECRET=your_x_api_secret
X_ACCESS_TOKEN=your_x_access_token
X_ACCESS_TOKEN_SECRET=your_x_access_token_secret
X_DAILY_REPLY_LIMIT=17          # X Free tier limit (default: 17)
REPLY_CHECK_INTERVAL_MIN=5      # Check approved replies every N minutes
```

## Review Dashboard

The review dashboard provides a web UI for managing AI-generated reply candidates.

### Accessing the Dashboard

- **Local**: http://localhost:8080/dashboard
- **Railway**: https://your-app.railway.app/dashboard

### Workflow

1. **Daily scrape** generates reply candidates → stored in `reply_queue` with status `pending`
2. **Review** each candidate in the dashboard:
   - View original post and generated reply
   - Edit the reply text
   - **Approve** - marks status as `approved`, queued for auto-sender
   - **Reject** - marks status as `rejected`
   - **Save** - saves edits without changing status
3. **Auto-sender** runs every 5 minutes:
   - Fetches `approved` items (FIFO by `approved_at`)
   - Posts to X via API (if `ENABLE_X_POSTING=true`)
   - Marks as `sent` on success, `failed` on error
   - Respects `X_DAILY_REPLY_LIMIT` (default 17/day for X Free tier)

### Dashboard Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/review` | GET | List all pending replies |
| `/review?status=approved` | GET | Filter by status |
| `/review/{queue_id}` | GET | Detail view for editing |
| `/review/{id}/approve` | POST | Approve with optional edit |
| `/review/{id}/reject` | POST | Reject a reply |
| `/review/{id}/save` | POST | Save edits without approving |
| `/api/stats` | GET | JSON stats (quota, counts) |
| `/api/approve/{id}` | POST | AJAX approve |
| `/api/reject/{id}` | POST | AJAX reject |
| `/api/save/{id}` | POST | AJAX save draft |

## Telegram Notifications

Posts grouped by category (Token Analysis, Industry Analysis, Market Comment, etc.) with direct links to X posts. Each message part includes a link to the review dashboard.

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

## Deployment on Railway

1. Connect your GitHub repo to Railway
2. Set environment variables in Railway dashboard
3. Railway auto-detects Python and runs `python app.py`
4. Health checks via `/health` endpoint
5. Scheduler runs automatically (daily scrape + 5-min reply checks)

## Next Steps
- Review and adjust LLM prompts in the `prompt_history` worksheet for optimal filtering
- Set all three AI provider API keys to enable runtime switching via Google Sheet
- Monitor API costs and performance (Apify, LLM usage)
- Set `ENABLE_X_POSTING=true` when ready to post live replies to X
- Configure `REVIEW_DASHBOARD_URL` for Telegram notification links

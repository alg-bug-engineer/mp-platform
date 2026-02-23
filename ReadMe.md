# Content Studio (Commercial WeChat Content Platform)

Content Studio is an end-to-end platform for WeChat official account operations, covering subscription monitoring, article ingestion, AI analysis, AI writing, and rewriting workflows.

## Features

- Phone + password registration and login
- Per-user data isolation (subscriptions, articles, tags, tasks, AI profiles)
- OpenAI-compatible model configuration (`base_url`, `api_key`, `model`)
- One-click `Analyze` / `Create` / `Rewrite` per article
- Creator workbench overview (assets, draft count, plan quota)
- Tiered plans for `Free` / `Pro` / `Premium` users
- Local draftbox + optional one-click sync to WeChat draftbox
- Draft publish queue (auto enqueue on failure + retry)
- Admin plan console (tier/quota adjustments)
- Unified web UI for subscriptions, tasks, tags, and system settings
- Containerized deployment with PostgreSQL support

## Quick Start

### Option A: Local

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml
python init_sys.py
python main.py -job True -init False
```

Open: `http://127.0.0.1:8001`

### Option B: Docker + PostgreSQL (recommended)

```bash
cd compose
docker compose -f docker-compose-postgresql.yaml up -d --build
```

Open: `http://127.0.0.1:8001`

Default admin account:
- Username: `admin`
- Password: `admin@123`

## Important Config

In `config.yaml`:

- `db`: database DSN (PostgreSQL recommended)
- `secret`: JWT signing secret
- `server.web_name`: web app title
- `token_expire_minutes`: auth token lifetime
- `rss.*`: RSS output behavior

PostgreSQL example:

```text
postgresql://rss_user:pass123456@postgres:5432/we_mp_rss
```

## AI Studio

Go to `AI Studio` after login and configure:

- `Base URL`
- `Model`
- `API Key`

Then run one-click actions on each article:
- Analyze
- Create
- Rewrite

After generation:
- Save to local draftbox
- Optionally sync to WeChat draftbox (requires QR authorization and proper plan tier)
- Optional Jimeng image generation (falls back to prompts when AK/SK are missing)


## Usage Docs

- Startup and usage guide: `docs/启动与使用指南.md`
- History cleanup script: `script/clean_history.sh`

## Delivery Scope

This delivery includes:

- unified product UI and layout
- phone-based user registration/login
- tenant-level data isolation
- AI content studio for article-level generation
- PostgreSQL containerized deployment
- Playwright E2E flow verification

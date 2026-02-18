# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

AI-powered sales agent for Amida AI that identifies, researches, and conducts outreach to PE firm AI/data leaders in Northern Europe. Local-first: SQLite DB, FastAPI dashboard at localhost:8000, Claude API for AI composition.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run dashboard (with hot reload)
python -m amida_agent.main

# Or directly with uvicorn
uvicorn amida_agent.web.app:app --reload --port 8000

# Seed PE firms
python scripts/seed_pe_firms.py
```

## Architecture

**Pipeline flow:** Scout (find leads) → Research (enrich) → Compose (AI drafts) → Approve (dashboard) → Outreach (send)

**Key modules:**
- `config.py` — Pydantic Settings, reads `.env` for all API keys
- `models.py` — All SQLModel tables: PEFirm, Prospect, OutreachDraft, ActivityLog, SearchQuery
- `database.py` — SQLite engine + session factory (uses `get_session()` context manager)
- `web/app.py` — FastAPI app, mounts routes at `/`, `/prospects`, `/approve`, `/pipeline`
- `web/deps.py` — Shared Jinja2 `templates` instance
- `web/routes/` — Dashboard, prospects, approve, pipeline routes
- `ai/composer.py` — Claude API email composition; `ai/prompts.py` — system prompts
- `scout/` — Lead identification (job_monitor, people_search, news_monitor, scorer)
- `research/` — Enrichment (enricher, email_finder, company_research, dossier_builder)
- `outreach/` — Sending (email_sender via Smartlead, linkedin_queue, sequence_manager)
- `notifications/notifier.py` — macOS native notifications via osascript

**Frontend:** HTMX + Jinja2 templates, dark theme. Partials in `templates/partials/` return HTML fragments for HTMX swaps. Dashboard auto-refreshes stats every 30s.

**Prospect status flow:** `new` → `researching` → `ready` → `drafted` → `approved` → `sent` → `replied` → `meeting`

**Database:** SQLite at `data/amida.db`, auto-created on startup via `init_db()`.

## Conventions

- Routes return full pages (extending `base.html`) for GET, HTMX partials for POST/interactive endpoints
- Use `get_session()` as context manager for all DB access
- Enum values used as CSS class names for status badges (e.g., `class="status-badge sent"`)
- Activity is logged to `ActivityLog` for all state transitions
- External API keys configured via `.env` file (see `.env.example`)

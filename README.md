# Side Quest Finder

Local prototype that searches community listings and provides a daily summary.

## Discovery agent

The backend stores interests, focus/purpose signals, source choices, and agent settings. `POST /discovery/run` builds source-specific searches from that profile, scrapes public pages, scores candidate activities, stores structured leads, and returns the daily summary.

Users can shortlist recommendations and mark each suggestion as good, neutral, or bad. The next discovery runs read that history as a lightweight preference profile, boosting or penalising similar sources and terms over time.

When `OPENAI_API_KEY` is set, the agent uses an LLM as its planning and judgement layer:
- it turns the user's interests, focus, location, settings, and feedback history into personalised search queries;
- it chooses source/query tool calls step by step during the run instead of blindly searching every source;
- it can open promising result pages during the run and feed inspected page text into extraction;
- it can explicitly accept or reject candidates during the run before the final safety ranking pass;
- it extracts clean activity cards from raw scraped candidates;
- it ranks the whole candidate set comparatively and records why each item was accepted or rejected.

Without an API key, the same pipeline falls back to deterministic query templates and local scoring so the prototype remains runnable offline.

Current source support includes per-source adapters for Meetup, Eventbrite, Reddit, Peatix, and Time Out. Login-gated apps such as Facebook and Instagram are tracked as planned connectors through `GET /connectors`; they should be integrated through official APIs, exports, OAuth, or user-authorised browser automation rather than brittle unauthenticated scraping.

Every run creates a trace available from:
- `GET /discovery/runs`
- `GET /discovery/runs/{run_id}/events`

The frontend exposes that trace on the `history` page so you can inspect what was searched, which candidates were accepted, and why other candidates were rejected.

Optional environment variables:
- `OPENAI_API_KEY` enables the LLM extraction/ranking pass that turns raw scraped candidates into cleaner activity cards.
- `OPENAI_MODEL` overrides the extraction model. The default is `gpt-4o-mini`.
- `EVENTBRITE_TOKEN` switches Eventbrite discovery from public page extraction to the official Eventbrite search API.
- `XC_NOTIFY_EMAIL`, `SMTP_HOST`, `SMTP_USERNAME`, and `SMTP_PASSWORD` enable daily email delivery after a successful scheduled or manual run.
- `SMTP_FROM` and `SMTP_PORT` customise email sender and SMTP port.

Folders:
- `backend` - FastAPI app (Python)
- `frontend` - minimal React (Vite) UI

Quick run (backend):

1. Create a Python venv and install requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
```

2. Run the API:

```powershell
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Quick run (frontend):

```bash
cd frontend
npm install
npm run dev
```

Run backend tests:

```powershell
python -m unittest discover -s backend\tests -v
```

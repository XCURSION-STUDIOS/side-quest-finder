# Side Quest Finder

Local prototype that scrapes community listings and provides a daily summary.

## Discovery agent

The backend stores interests, focus/purpose signals, and agent settings. `POST /discovery/run` builds source-specific searches from that profile, scrapes public pages, scores candidate activities, stores structured leads, and returns the daily summary.

Users can shortlist recommendations and mark each suggestion as good, neutral, or bad. The next discovery runs read that history as a lightweight preference profile, boosting or penalising similar sources and terms over time.

Current source support is public-web compatible. Login-gated apps such as Facebook and Instagram should be integrated later through official APIs, exports, or user-authorised connectors rather than brittle scraping.

Folders:
- `backend` — FastAPI app (Python)
- `frontend` — minimal React (Vite) UI

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

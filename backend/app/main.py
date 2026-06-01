import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from .db import create_db_and_tables, engine
from .models import DiscoveryRun, DiscoveryRunEvent, Preference, Item
from .utils import generate_daily_summary, get_demo_items
from .scheduler import start_scheduler, run_scrape_job
from .agent import DEFAULT_SETTINGS
from .connectors import connector_status

app = FastAPI(title="Side Quest Finder Agent")

allowed_origins = [
    origin.strip()
    for origin in os.getenv("XC_CORS_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    # ensure a preference row exists
    with Session(engine) as session:
        stmt = select(Preference).where(Preference.id == 1)
        pref = session.exec(stmt).first()
        if not pref:
            p = Preference(id=1, interests='[]', focus='[]')
            p.set_settings(DEFAULT_SETTINGS)
            session.add(p)
            session.commit()
    if str(os.getenv("XC_ENABLE_SCHEDULER", "1")).lower() in {"1", "true", "yes", "on"}:
        start_scheduler()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/preferences")
def get_preferences():
    with Session(engine) as session:
        pref = session.get(Preference, 1)
        settings = {**DEFAULT_SETTINGS, **pref.get_settings()}
        return {
            "interests": pref.get_interests(),
            "focus": pref.get_focus(),
            "settings": settings,
        }


@app.post("/preferences")
def set_preferences(payload: dict):
    interests = payload.get("interests") or []
    focus = payload.get("focus")
    settings = payload.get("settings")
    if not isinstance(interests, list):
        raise HTTPException(status_code=400, detail="interests must be a list")
    if focus is not None and not isinstance(focus, list):
        raise HTTPException(status_code=400, detail="focus must be a list")
    if settings is not None and not isinstance(settings, dict):
        raise HTTPException(status_code=400, detail="settings must be an object")
    with Session(engine) as session:
        pref = session.get(Preference, 1)
        pref.set_interests(interests)
        if focus is not None:
            pref.set_focus(focus)
        if settings is not None:
            pref.set_settings({**DEFAULT_SETTINGS, **settings})
        session.add(pref)
        session.commit()
    return {"ok": True}


@app.get("/profile")
def get_profile():
    return get_preferences()


@app.get("/summary")
def daily_summary():
    with Session(engine) as session:
        pref = session.get(Preference, 1)
        interests = pref.get_interests()
        settings = {**DEFAULT_SETTINGS, **pref.get_settings()}
    limit = int(settings.get("maxFinds") or 10)
    if settings.get("testingMode"):
        return {"items": get_demo_items(limit)}
    items = generate_daily_summary(interests=interests, limit=limit)
    if not items:
        return {"message": "No new updates", "items": []}
    return {"items": items}


@app.get("/shortlist")
def get_shortlist():
    with Session(engine) as session:
        items = session.exec(select(Item).where(Item.shortlisted == True)).all()
    items = sorted(items, key=lambda item: item.found_at, reverse=True)
    return {
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "link": item.link,
                "source": item.source,
                "summary": item.summary,
                "activity_when": item.activity_when,
                "venue": item.venue,
                "location": item.location,
                "contact": item.contact,
                "score": item.score,
                "shortlisted": item.shortlisted,
                "feedback": item.feedback,
                "found_at": item.found_at.isoformat(),
            }
            for item in items
        ]
    }


@app.patch("/items/{item_id}")
def update_item(item_id: int, payload: dict):
    allowed_feedback = {None, "good", "neutral", "bad"}
    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            raise HTTPException(status_code=404, detail="item not found")

        if "shortlisted" in payload:
            item.shortlisted = bool(payload["shortlisted"])
        if "feedback" in payload:
            feedback = payload["feedback"]
            if feedback not in allowed_feedback:
                raise HTTPException(status_code=400, detail="feedback must be good, neutral, bad, or null")
            item.feedback = feedback

        session.add(item)
        session.commit()
        session.refresh(item)

    return {
        "id": item.id,
        "shortlisted": item.shortlisted,
        "feedback": item.feedback,
    }


@app.post("/run-scrape")
def run_scrape():
    result = run_scrape_job(force=True)
    return result or {"ok": True}


@app.post("/discovery/run")
def run_discovery():
    result = run_scrape_job(force=True) or {}
    return {
        "items": result.get("items", []),
        "run_id": result.get("run_id"),
        "status": result.get("status"),
        "summary": result.get("summary"),
        "accepted_count": result.get("accepted_count", 0),
        "new_count": result.get("new_count", 0),
    }


@app.get("/discovery/runs")
def get_discovery_runs():
    with Session(engine) as session:
        runs = session.exec(select(DiscoveryRun)).all()
    runs = sorted(runs, key=lambda run: run.started_at, reverse=True)[:20]
    return {
        "runs": [
            {
                "id": run.id,
                "started_at": run.started_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "status": run.status,
                "query_count": run.query_count,
                "source_count": run.source_count,
                "candidate_count": run.candidate_count,
                "accepted_count": run.accepted_count,
                "rejected_count": run.rejected_count,
                "summary": run.summary,
            }
            for run in runs
        ]
    }


@app.get("/discovery/runs/{run_id}/events")
def get_discovery_run_events(run_id: int):
    with Session(engine) as session:
        run = session.get(DiscoveryRun, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        events = session.exec(select(DiscoveryRunEvent).where(DiscoveryRunEvent.run_id == run_id)).all()
    events = sorted(events, key=lambda event: event.created_at)
    return {
        "events": [
            {
                "id": event.id,
                "created_at": event.created_at.isoformat(),
                "source": event.source,
                "query": event.query,
                "url": event.url,
                "status": event.status,
                "reason": event.reason,
                "item_title": event.item_title,
                "item_link": event.item_link,
                "score": event.score,
            }
            for event in events
        ]
    }


@app.get("/connectors")
def get_connectors():
    return connector_status()

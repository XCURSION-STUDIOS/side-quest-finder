from sqlmodel import Session, select
from .models import Item, Preference
from .db import engine
from datetime import datetime, timedelta
from typing import List

DEMO_ITEMS = [
    {
        "id": -1,
        "title": "Beginner bouldering social at Boulder Movement",
        "link": "https://example.com/bouldering-social",
        "source": "demo",
        "summary": "A low-pressure climbing social for beginners and recent arrivals.",
        "activity_when": "Thursday evening",
        "venue": "Boulder Movement",
        "location": "Singapore",
        "contact": "organiser@example.com",
        "score": 8.7,
        "shortlisted": False,
        "feedback": None,
        "found_at": datetime.utcnow().isoformat(),
    },
    {
        "id": -2,
        "title": "Weekend volunteer beach cleanup and coffee",
        "link": "https://example.com/beach-cleanup",
        "source": "demo",
        "summary": "A volunteer morning with an optional coffee hangout afterwards.",
        "activity_when": "Saturday morning",
        "venue": "East Coast Park",
        "location": "Singapore",
        "contact": "hello@example.com",
        "score": 8.1,
        "shortlisted": False,
        "feedback": None,
        "found_at": datetime.utcnow().isoformat(),
    },
]

def generate_daily_summary(interests: List[str] = None, limit: int = 10):
    interests = interests or []
    today = datetime.utcnow()
    since = today - timedelta(days=1)
    with Session(engine) as session:
        stmt = select(Item).where(Item.found_at >= since)
        items = session.exec(stmt).all()

    if interests:
        lowered = [s.lower() for s in interests]
        def matches(it: Item):
            txt = " ".join(filter(None, [it.title, it.summary, it.tags or ""]))
            txt = txt.lower()
            return any(k in txt for k in lowered)
        items = [i for i in items if matches(i)]

    items = sorted(items, key=lambda i: i.found_at, reverse=True)[:limit]
    return [
        {
            "id": i.id,
            "title": i.title,
            "link": i.link,
            "source": i.source,
            "summary": i.summary,
            "activity_when": i.activity_when,
            "venue": i.venue,
            "location": i.location,
            "contact": i.contact,
            "score": i.score,
            "shortlisted": i.shortlisted,
            "feedback": i.feedback,
            "found_at": i.found_at.isoformat(),
        }
        for i in items
    ]

def get_demo_items(limit: int = 10):
    return DEMO_ITEMS[:limit]

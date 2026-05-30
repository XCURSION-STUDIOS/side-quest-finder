from apscheduler.schedulers.background import BackgroundScheduler
from .agent import DEFAULT_SETTINGS, DiscoveryAgent, DiscoveryContext
from .db import engine
from .models import Item, Preference
from sqlmodel import Session, select
from datetime import datetime

def run_scrape_job():
    import asyncio

    async def _run():
        with Session(engine) as session:
            pref = session.get(Preference, 1)
            interests = pref.get_interests() if pref else []
            focus = pref.get_focus() if pref else []
            settings = {**DEFAULT_SETTINGS, **(pref.get_settings() if pref else {})}

        if not settings.get("dailySummary", True):
            return

        feedback_profile = build_feedback_profile()
        agent = DiscoveryAgent(DiscoveryContext(
            interests=interests,
            focus=focus,
            settings=settings,
            feedback_profile=feedback_profile,
        ))
        items = await agent.run()
        with Session(engine) as session:
            for it in items:
                stmt = select(Item).where(Item.title == it.get("title"), Item.link == it.get("link"))
                found = session.exec(stmt).first()
                if found:
                    continue
                obj = Item(
                    title=it.get("title"),
                    link=it.get("link"),
                    source=it.get("source"),
                    tags=it.get("tags"),
                    summary=it.get("summary"),
                    activity_when=it.get("activity_when"),
                    venue=it.get("venue"),
                    location=it.get("location"),
                    contact=it.get("contact"),
                    score=it.get("score", 0),
                )
                obj.set_metadata(it.get("metadata") or {})
                session.add(obj)
            session.commit()

    asyncio.run(_run())

def build_feedback_profile():
    profile = {"source_weights": {}, "term_weights": {}}
    with Session(engine) as session:
        rated_items = session.exec(
            select(Item).where((Item.feedback != None) | (Item.shortlisted == True))
        ).all()

    for item in rated_items:
        weight = 0
        if item.feedback == "good":
            weight += 1.2
        elif item.feedback == "neutral":
            weight += 0.2
        elif item.feedback == "bad":
            weight -= 1.4
        if item.shortlisted:
            weight += 0.8

        if item.source:
            profile["source_weights"][item.source] = profile["source_weights"].get(item.source, 0) + weight * 0.2

        terms = []
        if item.tags:
            terms.extend([term.strip().lower() for term in item.tags.split(",")])
        terms.extend((item.title or "").lower().split()[:8])
        for term in terms:
            if len(term) < 4:
                continue
            profile["term_weights"][term] = profile["term_weights"].get(term, 0) + weight * 0.12

    return profile

def start_scheduler():
    sched = BackgroundScheduler()
    # run once daily
    sched.add_job(run_scrape_job, "interval", hours=24, next_run_time=datetime.utcnow())
    sched.start()
    return sched

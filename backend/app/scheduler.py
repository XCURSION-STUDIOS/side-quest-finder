from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from .agent import DEFAULT_SETTINGS, DiscoveryAgent, DiscoveryContext
from .db import engine
from .models import DiscoveryRun, DiscoveryRunEvent, Item, Preference
from .notifications import send_daily_email
from sqlmodel import Session, select

def run_scrape_job(force: bool = False):
    import asyncio

    async def _run():
        with Session(engine) as session:
            pref = session.get(Preference, 1)
            interests = pref.get_interests() if pref else []
            focus = pref.get_focus() if pref else []
            settings = {**DEFAULT_SETTINGS, **(pref.get_settings() if pref else {})}

        if not force and not settings.get("dailySummary", True):
            return

        run = DiscoveryRun(status="running")
        run.set_settings(settings)
        with Session(engine) as session:
            session.add(run)
            session.commit()
            session.refresh(run)
            run_id = run.id

        feedback_profile = build_feedback_profile()
        agent = DiscoveryAgent(DiscoveryContext(
            interests=interests,
            focus=focus,
            settings=settings,
            feedback_profile=feedback_profile,
        ))
        try:
            items = await agent.run()
            status = "completed"
            summary = f"Accepted {len(items)} activity leads."
        except Exception as exc:
            items = []
            status = "failed"
            summary = str(exc)[:240]

        with Session(engine) as session:
            accepted_count = 0
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
                accepted_count += 1

            for event in agent.events:
                run_event = DiscoveryRunEvent(
                    run_id=run_id,
                    source=event.get("source"),
                    query=event.get("query"),
                    url=event.get("url"),
                    status=event.get("status"),
                    reason=event.get("reason"),
                    item_title=event.get("item_title"),
                    item_link=event.get("item_link"),
                    score=event.get("score", 0),
                )
                run_event.set_metadata(event.get("metadata") or {})
                session.add(run_event)

            run = session.get(DiscoveryRun, run_id)
            run.completed_at = datetime.utcnow()
            run.status = status
            run.query_count = len(agent.build_queries())
            run.source_count = len([event for event in agent.events if event.get("status") == "searched"])
            run.candidate_count = len([event for event in agent.events if event.get("status") in {"accepted", "rejected"}])
            run.accepted_count = len([event for event in agent.events if event.get("status") == "accepted"])
            run.rejected_count = len([event for event in agent.events if event.get("status") == "rejected"])
            run.summary = summary
            session.add(run)
            session.commit()

        if status == "completed":
            send_daily_email(items)

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

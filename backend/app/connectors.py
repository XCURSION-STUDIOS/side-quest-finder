HARD_SOURCE_CONNECTORS = [
    {
        "id": "facebook",
        "name": "Facebook Groups",
        "status": "planned",
        "method": "official_api_or_browser",
        "note": "Needs authenticated access or a browser automation worker for group/event discovery.",
    },
    {
        "id": "instagram",
        "name": "Instagram",
        "status": "planned",
        "method": "official_api_or_browser",
        "note": "Best handled through official APIs or explicit user-authenticated browsing.",
    },
    {
        "id": "telegram",
        "name": "Telegram",
        "status": "planned",
        "method": "official_api",
        "note": "Can use Telegram APIs once the user opts into channels/groups to monitor.",
    },
    {
        "id": "strava",
        "name": "Strava",
        "status": "planned",
        "method": "official_api",
        "note": "Club discovery should use OAuth-backed Strava APIs.",
    },
]


def connector_status():
    return {"connectors": HARD_SOURCE_CONNECTORS}

import os
import smtplib
from email.message import EmailMessage
from typing import List, Dict, Any


def send_daily_email(items: List[Dict[str, Any]]) -> bool:
    recipient = os.getenv("XC_NOTIFY_EMAIL")
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("SMTP_FROM", username or "xcursion@localhost")
    port = int(os.getenv("SMTP_PORT", "587"))

    if not all([recipient, host, username, password]):
        return False

    message = EmailMessage()
    message["Subject"] = "Your XCursion daily side quests"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(render_email(items))

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)
    return True


def render_email(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "No new updates today."
    lines = ["Today's XCursion discoveries:", ""]
    for index, item in enumerate(items, start=1):
        lines.append(f"{index}. {item.get('title')}")
        if item.get("activity_when"):
            lines.append(f"   When: {item.get('activity_when')}")
        if item.get("location"):
            lines.append(f"   Where: {item.get('location')}")
        if item.get("link"):
            lines.append(f"   Link: {item.get('link')}")
        lines.append("")
    return "\n".join(lines)

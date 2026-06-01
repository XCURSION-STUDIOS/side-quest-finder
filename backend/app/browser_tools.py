import os
from typing import Dict


def browser_open_enabled() -> bool:
    return str(os.getenv("XC_BROWSER_OPEN") or "").lower() in {"1", "true", "yes", "on"}


def should_try_browser_open(text: str) -> bool:
    clean_text = " ".join((text or "").split()).lower()
    if len(clean_text) < 900:
        return True
    weak_markers = [
        "enable javascript",
        "please enable javascript",
        "unsupported browser",
        "sign in to continue",
        "log in to continue",
        "something went wrong",
    ]
    return any(marker in clean_text for marker in weak_markers)


async def browser_open_text(url: str, timeout_ms: int = 12000) -> Dict[str, str]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is not installed. Install it and run `python -m playwright install chromium`.") from exc

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        except Exception:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        text = await page.locator("body").inner_text(timeout=timeout_ms)
        final_url = page.url
        await browser.close()

    return {
        "url": final_url,
        "text": " ".join((text or "").split())[:12000],
    }

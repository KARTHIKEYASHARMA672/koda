"""Playwright browser navigation, search, and YouTube automation."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus, urlparse


class BrowserController:
    """Safe async Chromium controller backed by Playwright."""

    @staticmethod
    def _validate_http_url(url: str) -> str | None:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None
        return url.strip()

    async def browser_open(self, url: str, *, headless: bool = True) -> dict[str, Any]:
        clean_url = self._validate_http_url(url)
        if clean_url is None:
            return {"ok": False, "error": "Only http:// and https:// URLs are permitted."}

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=headless)
                try:
                    page = await browser.new_page()
                    await page.goto(clean_url, wait_until="domcontentloaded", timeout=20_000)
                    title = await page.title()
                    body_text = await page.inner_text("body")
                    return {
                        "ok": True,
                        "url": page.url,
                        "title": title.strip(),
                        "text_preview": " ".join(body_text.split())[:2500],
                    }
                finally:
                    await browser.close()
        except Exception as exc:
            return {"ok": False, "error": f"Browser navigation failed: {exc}"}

    async def browser_search(self, query: str) -> dict[str, Any]:
        encoded = quote_plus(query.strip())
        return await self.browser_open(f"https://html.duckduckgo.com/html/?q={encoded}", headless=True)

    async def browser_youtube(self, query: str) -> dict[str, Any]:
        encoded = quote_plus(query.strip())
        return await self.browser_open(f"https://www.youtube.com/results?search_query={encoded}", headless=False)

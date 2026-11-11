from __future__ import annotations

import asyncio
import http.server
import threading

import httpx

from koda.tools.browser import BrowserController
from koda.tools.integrations import WebAndIoTTools


class _QuietHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        html = (
            b"<html><head><title>Koda Local Test</title></head>"
            b"<body><h1>Hello Koda</h1><p>Browser &amp; web extract verified.</p></body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format: str, *args) -> None:
        return


def test_web_fetch_extracts_clean_text_and_rejects_bad_schemes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="<html><head><script>evil()</script><title>Docs</title></head><body><h2>Guide</h2><p>FastAPI &amp; Koda</p></body></html>",
            headers={"content-type": "text/html"},
        )

    web = WebAndIoTTools(transport=httpx.MockTransport(handler))

    async def run() -> None:
        bad = await web.web_fetch("file:///C:/Windows/win.ini")
        assert bad["ok"] is False

        ok = await web.web_fetch("https://example.com/guide", allow_local=True)
        assert ok["ok"] is True
        assert "FastAPI & Koda" in ok["text"]
        assert "evil()" not in ok["text"]

        ha = await web.ha_call_service("light", "turn_on", "light.desk")
        assert ha["ok"] is False
        assert "not configured" in ha["error"].lower()

    asyncio.run(run())


def test_browser_controller_navigates_real_headless_chromium() -> None:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    browser = BrowserController()
    try:
        async def run() -> None:
            bad = await browser.browser_open("javascript:alert(1)")
            assert bad["ok"] is False

            res = await browser.browser_open(f"http://127.0.0.1:{port}/", headless=True)
            assert res["ok"] is True
            assert res["title"] == "Koda Local Test"
            assert "Hello Koda" in res["text_preview"]

        asyncio.run(run())
    finally:
        server.shutdown()
        server.server_close()

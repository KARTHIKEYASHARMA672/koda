"""Web research digest and Home Assistant / Webhook bridge tools."""

from __future__ import annotations

import ipaddress
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip == 0 and data.strip():
            self._chunks.append(data.strip())

    def get_text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self._chunks)).strip()


def _is_private_or_loopback(host: str) -> bool:
    if host.lower() in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        return False


class WebAndIoTTools:
    """Fetches concise web text and triggers optional configured Home Assistant / webhook endpoints."""

    def __init__(
        self,
        *,
        home_assistant_url: str = "",
        home_assistant_token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.home_assistant_url = home_assistant_url.rstrip("/")
        self.home_assistant_token = home_assistant_token
        self.transport = transport

    async def web_fetch(self, url: str, *, allow_local: bool = False) -> dict[str, Any]:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return {"ok": False, "error": "Only valid http:// and https:// URLs are permitted."}
        if not allow_local and _is_private_or_loopback(parsed.hostname):
            return {"ok": False, "error": "Blocked local/private network fetch."}

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, transport=self.transport) as client:
                resp = await client.get(url.strip(), headers={"User-Agent": "Koda-AI-OS/0.1"})
                resp.raise_for_status()
                extractor = _TextExtractor()
                extractor.feed(resp.text)
                return {
                    "ok": True,
                    "url": str(resp.url),
                    "status_code": resp.status_code,
                    "text": extractor.get_text()[:6000],
                }
        except Exception as exc:
            return {"ok": False, "error": f"Web fetch failed: {exc}"}

    async def ha_call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.home_assistant_url or not self.home_assistant_token:
            return {"ok": False, "error": "Home Assistant is not configured in .env."}
        payload = {"entity_id": entity_id, **(data or {})}
        url = f"{self.home_assistant_url}/api/services/{domain}/{service}"
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self.transport) as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {self.home_assistant_token}"},
                )
                resp.raise_for_status()
                return {"ok": True, "domain": domain, "service": service, "entity_id": entity_id}
        except Exception as exc:
            return {"ok": False, "error": f"Home Assistant call failed: {exc}"}

    async def trigger_webhook(self, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return {"ok": False, "error": "Invalid webhook URL"}
        try:
            async with httpx.AsyncClient(timeout=10.0, transport=self.transport) as client:
                resp = await client.post(url.strip(), json=payload or {})
                return {"ok": resp.is_success, "status_code": resp.status_code}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

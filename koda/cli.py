"""Command-line entrypoint for Koda (`doctor`, `serve`, `ask`, `island`)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence

import uvicorn

from koda.config import KodaSettings
from koda.gateway.app import KodaService, create_app


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="koda", description="Koda — Zero-Cost Jarvis AI OS")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check local workstation configuration and OpenCode binary")

    serve_p = sub.add_parser("serve", help="Start Koda FastAPI gateway + managed OpenCode serve")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8765)

    ask_p = sub.add_parser("ask", help="Send a single routed $0 query via OpenCode")
    ask_p.add_argument("prompt", nargs="+", help="Prompt text")

    sub.add_parser("island", help="Launch PySide6 Dynamic Island HUD overlay")
    return parser


async def _run_ask(prompt_text: str) -> int:
    svc = KodaService()
    await svc.startup()
    try:
        from koda.gateway.app import ChatRequest

        res = await svc.chat(ChatRequest(prompt=prompt_text, conversation_id="cli"))
        print(f"[{res['model_id']} | ${res['cost']:.2f} | {res['latency_ms']}ms]")
        print(res["reply"])
        return 0
    finally:
        await svc.shutdown()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = KodaSettings()

    if args.command == "doctor":
        print(json.dumps(settings.safe_public_summary(), indent=2))
        return 0 if settings.opencode_exe.exists() else 1

    if args.command == "serve":
        app = create_app(KodaService(settings=settings))
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    if args.command == "ask":
        return asyncio.run(_run_ask(" ".join(args.prompt)))

    if args.command == "island":
        from koda.ui.island import launch_island_app

        return launch_island_app(gateway_url=f"http://{settings.host}:{settings.port}")

    return 1


if __name__ == "__main__":
    sys.exit(main())

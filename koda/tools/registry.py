"""Unified tool specification, OpenCode catalog builder, and safety-checked dispatch."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from koda.safety.gate import SafetyGate

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    args_schema: dict[str, str]
    handler: ToolHandler
    keywords: tuple[str, ...] = field(default_factory=tuple)


class ToolRegistry:
    """Registry connecting OpenCode tool requests with SafetyGate enforcement."""

    def __init__(self, *, safety_gate: SafetyGate) -> None:
        self.safety_gate = safety_gate
        self._tools: dict[str, ToolSpec] = {}

    def register(
        self,
        *,
        name: str,
        description: str,
        args_schema: dict[str, str],
        handler: ToolHandler,
        keywords: tuple[str, ...] = (),
    ) -> None:
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            args_schema=args_schema,
            handler=handler,
            keywords=keywords,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "args": spec.args_schema,
                "tier": self.safety_gate.default_tier(spec.name).value,
            }
            for spec in self._tools.values()
        ]

    def catalog_prompt(self) -> str:
        lines = ["Available Koda Tools (use ONLY when user request needs live local/web actions):"]
        for spec in self._tools.values():
            args_desc = ", ".join(f"{k}: {v}" for k, v in spec.args_schema.items()) or "none"
            lines.append(f"- {spec.name}({args_desc}): {spec.description}")
        return "\n".join(lines)

    async def dispatch(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        *,
        approved: bool = False,
    ) -> dict[str, Any]:
        spec = self._tools.get(name)
        if spec is None:
            return {"ok": False, "error": f"Unknown tool `{name}`"}

        safe_args = dict(args or {})
        decision = self.safety_gate.evaluate(name, safe_args)
        if decision.blocked:
            return {"ok": False, "blocked": True, "reason": decision.reason, "tier": decision.tier.value}
        if decision.requires_confirmation and not approved:
            return {
                "ok": False,
                "requires_confirmation": True,
                "reason": decision.reason,
                "tier": decision.tier.value,
            }

        try:
            return await spec.handler(**safe_args)
        except TypeError as exc:
            return {"ok": False, "error": f"Invalid arguments for `{name}`: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

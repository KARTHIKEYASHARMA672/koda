"""Default assembly of all Koda tools into one safety-checked ToolRegistry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from koda.config import KodaSettings
from koda.memory.store import MemoryStore
from koda.safety.gate import SafetyGate
from koda.tools.browser import BrowserController
from koda.tools.filesystem import WorkspaceFileTools
from koda.tools.integrations import WebAndIoTTools
from koda.tools.productivity import ProductivityTools
from koda.tools.registry import ToolRegistry
from koda.tools.system_os import SystemOSController


def build_default_tool_registry(
    *,
    settings: KodaSettings,
    memory: MemoryStore,
    safety_gate: SafetyGate,
) -> ToolRegistry:
    reg = ToolRegistry(safety_gate=safety_gate)
    sys_os = SystemOSController(screenshot_dir=settings.data_dir / "screenshots")
    fs = WorkspaceFileTools(allowed_roots=settings.parsed_allowed_roots, safety_gate=safety_gate)
    browser = BrowserController()

    vault_dir = Path(settings.obsidian_vault_path) if settings.obsidian_vault_path.strip() else (settings.data_dir / "notes")
    prod = ProductivityTools(
        memory=memory,
        notes_dir=vault_dir,
        routine_step_runner=lambda tool, args: reg.dispatch(tool, args),
    )
    web_iot = WebAndIoTTools(
        home_assistant_url=settings.home_assistant_url,
        home_assistant_token=settings.home_assistant_token.get_secret_value(),
    )

    reg.register(
        name="system_metrics",
        description="Get CPU, RAM, disk, battery, and RTX GPU telemetry",
        args_schema={},
        handler=sys_os.system_metrics,
    )
    reg.register(
        name="active_window",
        description="Get title and handle of currently focused Windows app",
        args_schema={},
        handler=sys_os.active_window,
    )
    reg.register(
        name="list_windows",
        description="List open top-level desktop windows",
        args_schema={},
        handler=sys_os.list_windows,
    )
    reg.register(
        name="focus_window",
        description="Bring an open window matching title_query to focus",
        args_schema={"title_query": "str"},
        handler=sys_os.focus_window,
    )
    reg.register(
        name="open_app",
        description="Open an allowlisted desktop application (notepad, calc, code, chrome, terminal, etc.)",
        args_schema={"name": "str"},
        handler=sys_os.open_app,
    )
    reg.register(
        name="capture_screen",
        description="Capture a screenshot image into data/screenshots for inspection",
        args_schema={},
        handler=sys_os.capture_screen,
    )
    reg.register(
        name="media_control",
        description="Control media/volume (play_pause, next, prev, volume_up, volume_down, mute)",
        args_schema={"action": "str"},
        handler=sys_os.media_control,
    )
    reg.register(
        name="read_file",
        description="Read text lines of a file inside allowed workspace",
        args_schema={"path": "str", "start_line": "int?", "max_lines": "int?"},
        handler=fs.read_file,
    )
    reg.register(
        name="write_file",
        description="Write or update a file inside allowed workspace",
        args_schema={"path": "str", "content": "str"},
        handler=fs.write_file,
    )
    reg.register(
        name="delete_file",
        description="Delete a file inside allowed workspace (requires confirmation)",
        args_schema={"path": "str"},
        handler=fs.delete_file,
    )
    reg.register(
        name="list_dir",
        description="List files and folders inside an allowed directory",
        args_schema={"path": "str?"},
        handler=fs.list_dir,
    )
    reg.register(
        name="search_files",
        description="Search text across workspace files",
        args_schema={"query": "str", "path": "str?"},
        handler=fs.search_files,
    )
    reg.register(
        name="git_status",
        description="Show git status inside workspace",
        args_schema={"path": "str?"},
        handler=fs.git_status,
    )
    reg.register(
        name="run_shell",
        description="Run a shell command inside workspace (requires user confirmation)",
        args_schema={"command": "str", "cwd": "str?"},
        handler=fs.run_shell,
    )
    reg.register(
        name="browser_open",
        description="Open an http(s) webpage in headless Chromium and summarize its content",
        args_schema={"url": "str"},
        handler=browser.browser_open,
    )
    reg.register(
        name="browser_search",
        description="Search the web via DuckDuckGo and return extracted snippets",
        args_schema={"query": "str"},
        handler=browser.browser_search,
    )
    reg.register(
        name="browser_youtube",
        description="Search YouTube in desktop Chromium",
        args_schema={"query": "str"},
        handler=browser.browser_youtube,
    )
    reg.register(
        name="save_note",
        description="Save a Notion-style Markdown note in Koda notes / Obsidian vault",
        args_schema={"title": "str", "body": "str", "tags": "list[str]?"},
        handler=prod.save_note,
    )
    reg.register(
        name="read_note",
        description="Read a saved Markdown note by title",
        args_schema={"title": "str"},
        handler=prod.read_note,
    )
    reg.register(
        name="clipboard_list",
        description="Search recent privacy-filtered clipboard snippets",
        args_schema={"query": "str?"},
        handler=prod.clipboard_list,
    )
    reg.register(
        name="memory_search",
        description="Search stored user facts, conversation episodes, and recall snippets",
        args_schema={"query": "str"},
        handler=prod.memory_search,
    )
    reg.register(
        name="run_routine",
        description="Run a saved multi-step workflow routine by name",
        args_schema={"name": "str"},
        handler=prod.run_routine,
    )
    reg.register(
        name="web_fetch",
        description="Fetch and clean readable text from an http(s) documentation or article URL",
        args_schema={"url": "str"},
        handler=web_iot.web_fetch,
    )
    reg.register(
        name="ha_call_service",
        description="Trigger a configured Home Assistant entity service (requires confirmation)",
        args_schema={"domain": "str", "service": "str", "entity_id": "str", "data": "dict?"},
        handler=web_iot.ha_call_service,
    )
    reg.register(
        name="trigger_webhook",
        description="POST JSON payload to an automation webhook (requires confirmation)",
        args_schema={"url": "str", "payload": "dict?"},
        handler=web_iot.trigger_webhook,
    )
    return reg


def execute_tool_with_registry(registry: ToolRegistry) -> Any:
    async def _exec(name: str, args: dict[str, Any]) -> dict[str, Any]:
        # KodaService already ran SafetyGate & HITL approval for CONFIRM tier tools.
        return await registry.dispatch(name, args, approved=True)

    return _exec

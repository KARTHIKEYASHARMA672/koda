"""Windows system telemetry, UIA window control, screen capture, and allowlisted app launcher."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

APP_ALLOWLIST: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calc": ["calc.exe"],
    "calculator": ["calc.exe"],
    "explorer": ["explorer.exe"],
    "cmd": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "terminal": ["wt.exe"],
    "code": ["code"],
    "vscode": ["code"],
    "chrome": ["chrome"],
    "edge": ["msedge"],
    "msedge": ["msedge"],
    "spotify": ["spotify"],
    "vlc": ["vlc"],
}


class SystemOSController:
    """Provides non-blocking OS telemetry and safe reversible Windows controls."""

    def __init__(self, *, screenshot_dir: Path | None = None) -> None:
        self.screenshot_dir = screenshot_dir or Path("data/screenshots")

    async def system_metrics(self) -> dict[str, Any]:
        def _collect() -> dict[str, Any]:
            vm = psutil.virtual_memory()
            disk = psutil.disk_usage(Path.cwd().anchor or "C:\\")
            battery = psutil.sensors_battery()
            gpu_info: dict[str, Any] | None = None
            if shutil.which("nvidia-smi"):
                try:
                    out = subprocess.check_output(
                        [
                            "nvidia-smi",
                            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                            "--format=csv,noheader,nounits",
                        ],
                        text=True,
                        timeout=1.5,
                    ).strip()
                    if out:
                        parts = [p.strip() for p in out.splitlines()[0].split(",")]
                        if len(parts) >= 5:
                            gpu_info = {
                                "name": parts[0],
                                "util_percent": float(parts[1]),
                                "vram_used_mb": float(parts[2]),
                                "vram_total_mb": float(parts[3]),
                                "temp_c": float(parts[4]),
                            }
                except Exception:
                    gpu_info = None

            return {
                "ok": True,
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "ram_percent": vm.percent,
                "ram_used_gb": round(vm.used / (1024**3), 2),
                "ram_total_gb": round(vm.total / (1024**3), 2),
                "disk_free_gb": round(disk.free / (1024**3), 2),
                "disk_percent": disk.percent,
                "battery_percent": round(battery.percent, 1) if battery else None,
                "power_plugged": bool(battery.power_plugged) if battery else None,
                "gpu": gpu_info,
            }

        return await asyncio.to_thread(_collect)

    async def list_windows(self, *, limit: int = 25) -> dict[str, Any]:
        def _enum() -> list[dict[str, Any]]:
            try:
                from pywinauto import Desktop

                wins = Desktop(backend="uia").windows()
                results: list[dict[str, Any]] = []
                for w in wins:
                    title = str(w.window_text() or "").strip()
                    if not title:
                        continue
                    results.append({"title": title[:120], "handle": int(w.handle)})
                    if len(results) >= limit:
                        break
                return results
            except Exception:
                return []

        windows = await asyncio.to_thread(_enum)
        return {"ok": True, "windows": windows}

    async def active_window(self) -> dict[str, Any]:
        def _active() -> dict[str, Any]:
            try:
                import ctypes

                hwnd = ctypes.windll.user32.GetForegroundWindow()
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return {"ok": True, "title": buf.value, "handle": int(hwnd)}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        return await asyncio.to_thread(_active)

    async def focus_window(self, title_query: str) -> dict[str, Any]:
        def _focus() -> dict[str, Any]:
            try:
                from pywinauto import Desktop

                needle = title_query.lower().strip()
                for w in Desktop(backend="uia").windows():
                    title = str(w.window_text() or "").strip()
                    if needle and needle in title.lower():
                        w.set_focus()
                        return {"ok": True, "focused_title": title}
                return {"ok": False, "error": f"No visible window matching `{title_query}`"}
            except Exception as exc:
                return {"ok": False, "error": str(exc)}

        return await asyncio.to_thread(_focus)

    async def open_app(self, name: str) -> dict[str, Any]:
        key = name.strip().lower()
        cmd = APP_ALLOWLIST.get(key)
        if cmd is None:
            return {
                "ok": False,
                "error": f"App `{name}` is not in Koda's safe allowlist ({', '.join(sorted(APP_ALLOWLIST))}).",
            }

        def _launch() -> dict[str, Any]:
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
            return {"ok": True, "launched": key}

        try:
            return await asyncio.to_thread(_launch)
        except OSError as exc:
            return {"ok": False, "error": f"Failed to launch `{key}`: {exc}"}

    async def capture_screen(self) -> dict[str, Any]:
        def _grab() -> dict[str, Any]:
            from PIL import ImageGrab

            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            out_path = self.screenshot_dir / f"screen_{int(time.time() * 1000)}.png"
            img = ImageGrab.grab()
            img.save(out_path, format="PNG")
            return {"ok": True, "path": str(out_path.resolve()), "width": img.width, "height": img.height}

        try:
            return await asyncio.to_thread(_grab)
        except Exception as exc:
            return {"ok": False, "error": f"Screen capture failed: {exc}"}

    async def media_control(self, action: str) -> dict[str, Any]:
        key_map = {
            "play_pause": "playpause",
            "next": "nexttrack",
            "prev": "prevtrack",
            "previous": "prevtrack",
            "volume_up": "volumeup",
            "volume_down": "volumedown",
            "mute": "volumemute",
        }
        key_name = key_map.get(action.strip().lower())
        if not key_name:
            return {"ok": False, "error": f"Unsupported media action `{action}`"}

        def _press() -> dict[str, Any]:
            import pyautogui

            pyautogui.press(key_name)
            return {"ok": True, "action": action}

        try:
            return await asyncio.to_thread(_press)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

"""Always-on-top PySide6 Dynamic Island Pill & System Tray linked to Koda Gateway WS."""

from __future__ import annotations

import json
import sys
import webbrowser
from dataclasses import dataclass

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QAbstractSocket
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QWidget,
)


@dataclass(frozen=True, slots=True)
class IslandVisualSpec:
    label: str
    accent_hex: str
    width: int


ISLAND_STATES: dict[str, IslandVisualSpec] = {
    "idle": IslandVisualSpec("KODA · $0 READY", "#3B82F6", 200),
    "listening": IslandVisualSpec("LISTENING", "#22D3EE", 250),
    "thinking": IslandVisualSpec("ROUTING...", "#D9A441", 260),
    "shifting": IslandVisualSpec("MODEL SHIFTED", "#D9A441", 340),
    "speaking": IslandVisualSpec("SPEAKING", "#10B981", 260),
    "confirm_needed": IslandVisualSpec("CONFIRM ACTION", "#EF4444", 350),
}


def _make_tray_icon(hex_color: str = "#3B82F6") -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#0A0D14"))
    painter.setPen(QColor(hex_color))
    painter.drawEllipse(2, 2, 28, 28)
    painter.setBrush(QColor(hex_color))
    painter.drawEllipse(10, 10, 12, 12)
    painter.end()
    return QIcon(pix)


class DynamicIslandPill(QWidget):
    """Frameless top-center Obsidian status pill showing live voice/router/HITL state."""

    def __init__(self, *, gateway_url: str = "http://127.0.0.1:8765", connect_ws: bool = True) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.gateway_url = gateway_url.rstrip("/")
        self.current_state = "idle"
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedHeight(44)

        self._container = QWidget(self)
        self._container.setObjectName("KodaIslandContainer")
        layout = QHBoxLayout(self._container)
        layout.setContentsMargins(14, 6, 12, 6)
        layout.setSpacing(8)

        self.dot_label = QLabel("●")
        self.status_label = QLabel("KODA · $0 READY")
        self.detail_label = QLabel("")
        self.open_btn = QPushButton("HUD")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.clicked.connect(self.open_command_deck)

        layout.addWidget(self.dot_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.detail_label, 1)
        layout.addWidget(self.open_btn)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._container)

        self.set_state("idle", "")
        self._position_top_center()

        self._ws: QWebSocket | None = None
        self._reconnect_timer: QTimer | None = None
        if connect_ws:
            self._init_websocket()

    def _position_top_center(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        y = geo.y() + 12
        self.move(x, y)

    def set_state(self, state: str, detail: str = "") -> None:
        key = state if state in ISLAND_STATES else "idle"
        self.current_state = key
        spec = ISLAND_STATES[key]
        self.setFixedWidth(spec.width)
        self.status_label.setText(spec.label)
        short_detail = detail[:28] + ("…" if len(detail) > 28 else "") if detail else ""
        self.detail_label.setText(short_detail)
        self.detail_label.setVisible(bool(short_detail))

        self._container.setStyleSheet(
            f"""
            QWidget#KodaIslandContainer {{
                background-color: rgba(17, 22, 34, 236);
                border: 1px solid {spec.accent_hex};
                border-radius: 22px;
            }}
            QLabel {{
                color: #F5F0E6;
                font-family: 'Plus Jakarta Sans', 'Segoe UI', sans-serif;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton {{
                background-color: rgba(59, 130, 246, 45);
                color: #F5F0E6;
                border: 1px solid rgba(245, 240, 230, 40);
                border-radius: 12px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #3B82F6;
            }}
            """
        )
        self.dot_label.setStyleSheet(f"color: {spec.accent_hex}; font-size: 13px;")
        self._position_top_center()

    def open_command_deck(self) -> None:
        webbrowser.open(self.gateway_url)

    def _init_websocket(self) -> None:
        self._ws = QWebSocket()
        self._ws.textMessageReceived.connect(self._on_ws_message)
        self._ws.disconnected.connect(self._schedule_reconnect)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setInterval(4000)
        self._reconnect_timer.timeout.connect(self._ensure_ws_connected)
        self._reconnect_timer.start()
        self._ensure_ws_connected()

    def _ensure_ws_connected(self) -> None:
        if self._ws is None:
            return
        if self._ws.state() == QAbstractSocket.SocketState.UnconnectedState:
            ws_url = self.gateway_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/events"
            self._ws.open(QUrl(ws_url))

    def _schedule_reconnect(self) -> None:
        self.set_state("idle", "reconnecting")

    def _on_ws_message(self, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        ev_type = msg.get("type")
        payload = msg.get("payload", {}) or {}
        if ev_type == "koda_state":
            self.set_state(str(payload.get("state", "idle")), str(payload.get("detail", "")))
        elif ev_type == "router_shift":
            to_m = str(payload.get("to_model", ""))
            self.set_state("shifting", f"-> {to_m}")
        elif ev_type == "approval_required":
            self.set_state("confirm_needed", str(payload.get("summary", "")))


def launch_island_app(*, gateway_url: str = "http://127.0.0.1:8765") -> int:
    """Launch Koda Dynamic Island pill + Windows system tray + Ctrl+Space toggle."""
    app = QApplication.instance() or QApplication(sys.argv)
    pill = DynamicIslandPill(gateway_url=gateway_url, connect_ws=True)
    pill.show()

    tray = QSystemTrayIcon(_make_tray_icon("#3B82F6"), parent=pill)
    menu = QMenu()
    open_act = QAction("Open Spatial Command Deck", menu)
    open_act.triggered.connect(pill.open_command_deck)
    toggle_act = QAction("Toggle Dynamic Island", menu)
    toggle_act.triggered.connect(lambda: pill.setVisible(not pill.isVisible()))
    quit_act = QAction("Exit Island", menu)
    quit_act.triggered.connect(app.quit)

    menu.addAction(open_act)
    menu.addAction(toggle_act)
    menu.addSeparator()
    menu.addAction(quit_act)
    tray.setContextMenu(menu)
    tray.setToolTip("Koda Personal AI OS ($0 OpenCode Router)")
    tray.show()

    try:
        import keyboard

        keyboard.add_hotkey("ctrl+space", lambda: QTimer.singleShot(0, pill.open_command_deck))
    except Exception:
        pass

    return app.exec()

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from koda.ui.island import DynamicIslandPill, ISLAND_STATES


def test_dynamic_island_states_and_shift_toast() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None

    pill = DynamicIslandPill(gateway_url="http://127.0.0.1:8765", connect_ws=False)
    try:
        assert pill.current_state == "idle"

        for state_name in ("listening", "thinking", "shifting", "speaking", "confirm_needed", "idle"):
            pill.set_state(state_name, detail=f"Model test ({state_name})")
            assert pill.current_state == state_name
            assert state_name in ISLAND_STATES
            assert pill.status_label.text() != ""
    finally:
        pill.close()

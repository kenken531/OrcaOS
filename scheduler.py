"""
OrcaOS — OrcaScheduler
Runs on Textual's main thread via set_interval(0.05, ...).
Drains all ISR queues and updates panel reactives safely.
"""
from __future__ import annotations

import queue as _queue
from typing import TYPE_CHECKING

import state as _state
from tasks.gesture_actions import processor as _gesture_proc

if TYPE_CHECKING:
    from orcaos import OrcaOS


class OrcaScheduler:
    def __init__(self, app: "OrcaOS") -> None:
        self.app = app
        self._spin = 0

    def tick(self) -> None:
        """Called every 50 ms by Textual's set_interval."""
        self._drain_gesture()
        self._drain_audio()
        self._drain_sys()
        self._drain_llm()

    # ── gesture ───────────────────────────────────────────────────────────────
    def _drain_gesture(self) -> None:
        panel = self.app.gesture_panel
        panel.active   = _state.read_state("gesture_active", False)
        panel.error    = _state.read_state("gesture_error", "")
        panel.open_log = _state.read_state("gesture_open_log", [])
        panel.cam_idx  = _state.read_state("gesture_cam_idx", -1)
        panel.backend  = _state.read_state("gesture_backend", "")

        while True:
            try:
                d = _state.gesture_queue.get_nowait()
            except _queue.Empty:
                break
            panel.label = d["gesture_label"]
            panel.value = d["gesture_value"]
            panel.fps   = d["gesture_fps"]
            _gesture_proc.process(d)
            status = _gesture_proc.status()
            panel.volume      = status["volume"]
            panel.vol_avail   = status["vol_available"]
            panel.last_action = status["last_action"]

    # ── audio ─────────────────────────────────────────────────────────────────
    def _drain_audio(self) -> None:
        panel = self.app.audio_panel
        panel.active = _state.read_state("audio_active", False)

        while True:
            try:
                d = _state.audio_queue.get_nowait()
            except _queue.Empty:
                break
            panel.rms  = d["audio_rms"]
            panel.fft  = d["audio_fft"]
            panel.peak = d["audio_peak"]

    # ── system ────────────────────────────────────────────────────────────────
    def _drain_sys(self) -> None:
        panel = self.app.sys_panel

        while True:
            try:
                d = _state.sys_queue.get_nowait()
            except _queue.Empty:
                break
            panel.cpu    = d["cpu_percent"]
            panel.ram    = d["ram_percent"]
            panel.uptime = d["uptime_s"]

    # ── llm ───────────────────────────────────────────────────────────────────
    def _drain_llm(self) -> None:
        panel = self.app.llm_panel

        self._spin = (self._spin + 1) % 10
        panel.spin_idx = self._spin
        panel.thinking = _state.read_state("llm_thinking", False)
        panel.model    = _state.read_state("llm_model", "—")

        while True:
            try:
                d = _state.llm_queue.get_nowait()
            except _queue.Empty:
                break
            msg_type = d.get("type")
            if msg_type == "start":
                panel.clear()
            elif msg_type in ("token", "error"):
                panel.append_token(d["text"])
            # "done" is a no-op — tokens already streamed

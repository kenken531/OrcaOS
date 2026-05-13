"""
OrcaOS — OrcaScheduler
Runs on Textual's main thread via set_interval(0.05, ...).
Drains all ISR queues and updates panel reactives safely.
This is the kernel's task dispatcher — the RTOS scheduler equivalent.
"""
from __future__ import annotations
import queue as _queue
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orcaos import OrcaOS

# Import the action processor singleton
from tasks.gesture_actions import processor as _gesture_proc


class OrcaScheduler:
    def __init__(self, app: "OrcaOS"):
        self.app = app
        self._spin = 0

    def tick(self):
        """Called every 50 ms by Textual's set_interval. Drains all queues."""
        self._drain_gesture()
        self._drain_audio()
        self._drain_sys()
        self._drain_llm()

    # ── gesture ───────────────────────────────────────────────────────────────
    def _drain_gesture(self):
        from state import gesture_queue, read_state
        panel = self.app.gesture_panel
        panel.active   = read_state("gesture_active", False)
        panel.error    = read_state("gesture_error", "")
        panel.open_log = read_state("gesture_open_log", [])
        panel.cam_idx  = read_state("gesture_cam_idx", -1)
        panel.backend  = read_state("gesture_backend", "")

        while True:
            try:
                d = gesture_queue.get_nowait()
                panel.label = d["gesture_label"]
                panel.value = d["gesture_value"]
                panel.fps   = d["gesture_fps"]
                # ── fire actions (volume, lock) ────────────────────────────
                _gesture_proc.process(d)
                # ── push action feedback to panel ─────────────────────────
                status = _gesture_proc.status()
                panel.volume     = status["volume"]
                panel.vol_avail  = status["vol_available"]
                panel.last_action = status["last_action"]
            except Exception:
                break

    # ── audio ─────────────────────────────────────────────────────────────────
    def _drain_audio(self):
        from state import audio_queue, read_state
        panel = self.app.audio_panel
        panel.active = read_state("audio_active", False)

        while True:
            try:
                d = audio_queue.get_nowait()
                panel.rms  = d["audio_rms"]
                panel.fft  = d["audio_fft"]
                panel.peak = d["audio_peak"]
            except _queue.Empty:
                break

    # ── system ────────────────────────────────────────────────────────────────
    def _drain_sys(self):
        from state import sys_queue
        panel = self.app.sys_panel

        while True:
            try:
                d = sys_queue.get_nowait()
                panel.cpu    = d["cpu_percent"]
                panel.ram    = d["ram_percent"]
                panel.uptime = d["uptime_s"]
            except _queue.Empty:
                break

    # ── llm ───────────────────────────────────────────────────────────────────
    def _drain_llm(self):
        from state import llm_queue, read_state
        panel = self.app.llm_panel

        self._spin = (self._spin + 1) % 10
        panel.spin_idx  = self._spin
        panel.thinking  = read_state("llm_thinking", False)
        panel.model     = read_state("llm_model", "—")

        while True:
            try:
                d = llm_queue.get_nowait()
                if d["type"] == "start":
                    panel.clear()
                elif d["type"] == "token":
                    panel.append_token(d["text"])
                elif d["type"] == "error":
                    panel.append_token(d["text"])
                elif d["type"] == "done":
                    pass  # tokens already streamed; state updated by llm_task
            except _queue.Empty:
                break
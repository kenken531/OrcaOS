"""
OrcaOS — shared state
All ISRs write here. Scheduler reads here. No direct cross-thread widget access.
"""
import queue
import threading
from typing import Any

# ── Queues (ISR → Scheduler) ──────────────────────────────────────────────────
gesture_queue: queue.Queue = queue.Queue(maxsize=32)
audio_queue:   queue.Queue = queue.Queue(maxsize=64)
sys_queue:     queue.Queue = queue.Queue(maxsize=16)
llm_queue:     queue.Queue = queue.Queue(maxsize=128)

# ── Latest values ─────────────────────────────────────────────────────────────
_state: dict[str, Any] = {
    # gesture
    "gesture_label":    "—",
    "gesture_value":    0.0,
    "gesture_fps":      0.0,
    "gesture_error":    "",
    "gesture_open_log": [],
    "gesture_cam_idx":  -1,
    "gesture_backend":  "",

    # audio
    "audio_rms":  0.0,
    "audio_fft":  [],
    "audio_peak": 0.0,

    # system
    "cpu_percent": 0.0,
    "ram_percent": 0.0,
    "uptime_s":    0,

    # llm
    "llm_response": "",
    "llm_thinking": False,
    "llm_model":    "unknown",

    # runtime flags
    "gesture_active": False,
    "audio_active":   False,
}

_lock = threading.Lock()


def update_state(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def read_state(key: str, default: Any = None) -> Any:
    with _lock:
        return _state.get(key, default)

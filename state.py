"""
OrcaOS — shared state
All ISRs write here. Scheduler reads here. No direct cross-thread widget access.
"""
import queue
import threading

# ── Queues (ISR → Scheduler) ──────────────────────────────────────────────────
gesture_queue: queue.Queue = queue.Queue(maxsize=32)
audio_queue:   queue.Queue = queue.Queue(maxsize=64)
sys_queue:     queue.Queue = queue.Queue(maxsize=16)
llm_queue:     queue.Queue = queue.Queue(maxsize=128)

# ── Latest values (Scheduler writes, panels read) ─────────────────────────────
state: dict = {
    # gesture
    "gesture_label":   "—",
    "gesture_value":   0.0,   # normalised 0-1 (e.g. volume level)
    "gesture_fps":     0.0,
    "gesture_error":   "",    # last error string from GestureISR
    "gesture_open_log": [],   # camera open attempt log
    "gesture_cam_idx": -1,    # which camera index succeeded

    # audio
    "audio_rms":       0.0,   # 0-1
    "audio_fft":       [],    # list of 16 float bars
    "audio_peak":      0.0,

    # system
    "cpu_percent":     0.0,
    "ram_percent":     0.0,
    "uptime_s":        0,

    # llm
    "llm_response":    "",
    "llm_thinking":    False,
    "llm_model":       "unknown",

    # runtime flags
    "gesture_active":  False,
    "audio_active":    False,
}

state_lock = threading.Lock()

def update_state(**kwargs):
    with state_lock:
        state.update(kwargs)

def read_state(key, default=None):
    with state_lock:
        return state.get(key, default)
"""
OrcaOS — GestureActions
Processes gesture events + hand position → real system actions.

Actions:
  FIST + move UP/DOWN  → increase / decrease system volume
  PINCH (held)         → lock workstation (Windows) after 1.5s hold

Architecture:
  Called by the scheduler on every gesture queue drain.
  Maintains its own small state (position history, hold timers).
  Never blocks — all actions fire in a daemon thread.
"""
import threading
import time
import platform
from collections import deque

# ── Windows-only imports (graceful no-op on other platforms) ──────────────────
_IS_WIN    = platform.system() == "Windows"
_VOL_OK    = False
_LOCK_OK   = False
_volume    = None   # IAudioEndpointVolume COM object

def _init_volume():
    global _volume, _VOL_OK
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices    = AudioUtilities.GetSpeakers()
        interface  = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        _volume    = cast(interface, POINTER(IAudioEndpointVolume))
        _VOL_OK    = True
    except Exception as e:
        _VOL_OK = False

def _init_lock():
    global _LOCK_OK
    if _IS_WIN:
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation   # just probe it
            _LOCK_OK = True
        except Exception:
            _LOCK_OK = False

_init_volume()
_init_lock()


# ── Volume helpers ─────────────────────────────────────────────────────────────
def get_volume() -> float:
    """Returns current master volume 0.0–1.0, or -1 on error."""
    if not _VOL_OK or _volume is None:
        return -1.0
    try:
        return float(_volume.GetMasterVolumeLevelScalar())
    except Exception:
        return -1.0

def set_volume(level: float):
    """Set master volume 0.0–1.0."""
    if not _VOL_OK or _volume is None:
        return
    try:
        _volume.SetMasterVolumeLevelScalar(max(0.0, min(1.0, level)), None)
    except Exception:
        pass

def lock_screen():
    """Lock the Windows workstation."""
    if not _LOCK_OK:
        return
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  GestureActionProcessor
# ══════════════════════════════════════════════════════════════════════════════

# How many frames of Y position history to keep for velocity smoothing
_Y_HISTORY   = 8

# Minimum Y delta (normalised 0-1 frame coords) per frame to register movement
_MOVE_THRESH = 0.008

# Volume step per frame of movement (tunable)
_VOL_STEP    = 0.025

# How long PINCH must be held before locking (seconds)
_PINCH_LOCK_HOLD = 1.5

# Deadband: ignore tiny volume changes to avoid jitter
_VOL_DEADBAND = 0.005


class GestureActionProcessor:
    """
    Stateful processor: call .process(event_dict) on every gesture queue item.
    Fires volume / lock actions as side effects.
    Exposes .action_log (deque) for the TUI to display.
    """

    def __init__(self):
        self._y_history:   deque  = deque(maxlen=_Y_HISTORY)
        self._pinch_since: float  = 0.0
        self._pinch_armed: bool   = False
        self._last_label:  str    = "NONE"
        self._vol_accum:   float  = 0.0   # accumulate small deltas before applying
        self.action_log:   deque  = deque(maxlen=6)
        self._lock_fired:  bool   = False  # don't re-fire lock in same pinch hold

    # ── public ────────────────────────────────────────────────────────────────
    def process(self, event: dict):
        """
        event keys: gesture_label, gesture_value, gesture_fps,
                    hand_y (0=top, 1=bottom of frame — optional)
        """
        label   = event.get("gesture_label", "NONE")
        hand_y  = event.get("hand_y", None)   # None if using OpenCV fallback

        self._handle_fist_volume(label, hand_y)
        self._handle_pinch_lock(label)
        self._last_label = label

    def status(self) -> dict:
        """Returns dict for the TUI status bar."""
        vol = get_volume()
        return {
            "vol_available": _VOL_OK,
            "lock_available": _LOCK_OK,
            "volume": vol,
            "last_action": self.action_log[-1] if self.action_log else "",
        }

    # ── FIST + vertical movement → volume ─────────────────────────────────────
    def _handle_fist_volume(self, label: str, hand_y):
        if label != "FIST":
            self._y_history.clear()
            self._vol_accum = 0.0
            return

        if hand_y is None:
            return   # OpenCV fallback has no position — skip

        self._y_history.append(hand_y)

        if len(self._y_history) < 3:
            return

        # Velocity = mean delta over last N frames
        # hand_y increases downward (0=top, 1=bottom)
        # moving UP = decreasing y = negative delta → INCREASE volume
        # moving DOWN = increasing y = positive delta → DECREASE volume
        deltas = [
            self._y_history[i] - self._y_history[i-1]
            for i in range(1, len(self._y_history))
        ]
        velocity = sum(deltas) / len(deltas)   # negative = up, positive = down

        if abs(velocity) < _MOVE_THRESH:
            return   # hand stationary — no action

        # Accumulate then apply (avoids vol calls every single frame)
        direction = -1 if velocity < 0 else 1   # -1=up→louder, +1=down→quieter
        self._vol_accum += direction * _VOL_STEP * (abs(velocity) / _MOVE_THRESH)

        if abs(self._vol_accum) >= _VOL_DEADBAND:
            current = get_volume()
            if current >= 0:
                new_vol = max(0.0, min(1.0, current - self._vol_accum))
                set_volume(new_vol)
                arrow = "▲" if self._vol_accum < 0 else "▼"
                self._log(f"VOL {arrow}  {new_vol*100:.0f}%")
            self._vol_accum = 0.0

    # ── PINCH hold → lock screen ───────────────────────────────────────────────
    def _handle_pinch_lock(self, label: str):
        if label == "PINCH":
            if not self._pinch_armed:
                self._pinch_since = time.time()
                self._pinch_armed = True
                self._lock_fired  = False
                self._log("PINCH — hold to lock…")

            elif not self._lock_fired:
                held = time.time() - self._pinch_since
                if held >= _PINCH_LOCK_HOLD:
                    self._log(f"🔒 LOCKING…")
                    self._lock_fired = True
                    # fire in a thread so TUI doesn't freeze
                    threading.Thread(target=lock_screen, daemon=True).start()
        else:
            if self._pinch_armed and not self._lock_fired:
                # released before threshold — cancel
                self._log("PINCH released (no lock)")
            self._pinch_armed = False
            self._lock_fired  = False

    # ── logging ───────────────────────────────────────────────────────────────
    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.action_log.append(f"[{ts}] {msg}")


# ── Module-level singleton (scheduler imports this) ──────────────────────────
processor = GestureActionProcessor()
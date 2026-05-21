"""
OrcaOS — GestureActions
FIST position → system volume  |  PINCH hold → lock screen

Threading model (fixes UI freeze):
  - Scheduler calls processor.process(event) — returns INSTANTLY, no COM
  - A dedicated VolumeWorker thread owns all COM objects
  - Scheduler sends target volume into a queue; VolumeWorker applies it
  - COM never touches the Textual main thread
"""
import threading
import time
import platform
import queue
from collections import deque

_IS_WIN  = platform.system() == "Windows"
_LOCK_OK = False

def _init_lock():
    global _LOCK_OK
    if _IS_WIN:
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation  # probe
            _LOCK_OK = True
        except Exception:
            _LOCK_OK = False

_init_lock()


# ══════════════════════════════════════════════════════════════════════════════
#  VolumeWorker — owns COM, runs on its own thread
# ══════════════════════════════════════════════════════════════════════════════

class VolumeWorker:
    """
    Background thread that owns the COM volume interface.
    Accepts (level: float) via a queue and applies it.
    get_volume() returns the last known level (cached, no COM on caller thread).
    """

    def __init__(self):
        self._queue:      queue.Queue = queue.Queue(maxsize=4)
        self._last_vol:   float       = -1.0
        self._ok:         bool        = False
        self._thread:     threading.Thread = threading.Thread(
            target=self._run, daemon=True, name="VolumeWorker"
        )
        self._thread.start()

    def set(self, level: float):
        """Non-blocking. Drops oldest request if queue full."""
        level = max(0.0, min(1.0, level))
        if self._queue.full():
            try: self._queue.get_nowait()
            except queue.Empty: pass
        try: self._queue.put_nowait(level)
        except queue.Full: pass

    def get(self) -> float:
        """Returns cached last-known volume. Never blocks, no COM."""
        return self._last_vol

    @property
    def available(self) -> bool:
        return self._ok

    def _run(self):
        """Runs on VolumeWorker thread. Owns all COM objects here."""
        import os
        log_path = os.path.join(os.path.dirname(__file__), "..", "volume_worker.log")

        def log(msg):
            ts = time.strftime("%H:%M:%S")
            line = f"[{ts}] {msg}"
            try:
                with open(log_path, "a") as f:
                    f.write(line + "\n")
            except Exception:
                pass

        log("VolumeWorker thread started")
        vol_iface = self._init_com(log)
        log(f"COM init: ok={self._ok}  iface={vol_iface is not None}")

        while True:
            try:
                level = self._queue.get(timeout=1.0)
            except queue.Empty:
                # Refresh cached volume periodically
                if vol_iface:
                    try:
                        self._last_vol = float(vol_iface.GetMasterVolumeLevelScalar())
                    except Exception as e:
                        log(f"GetMasterVolume failed: {e} — reiniting")
                        vol_iface = self._init_com(log)
                continue

            if vol_iface is None:
                log("No iface — attempting reinit")
                vol_iface = self._init_com(log)
                if vol_iface is None:
                    log("Reinit failed — dropping set request")
                    continue

            try:
                log(f"SetMasterVolumeLevelScalar({level:.4f})")
                vol_iface.SetMasterVolumeLevelScalar(level, None)
                time.sleep(0.05)
                actual = float(vol_iface.GetMasterVolumeLevelScalar())
                log(f"Readback after set: {actual:.4f}  (target was {level:.4f})")
                self._last_vol = actual
            except Exception as e:
                log(f"SetMasterVolume EXCEPTION: {e}")
                vol_iface = None
                self._ok  = False

    def _init_com(self, log=None):
        """Initialise COM and return volume interface, or None on failure."""
        def _log(msg):
            if log: log(msg)
        try:
            import comtypes
            comtypes.CoInitialize()
            _log("CoInitialize OK")
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            speakers = AudioUtilities.GetSpeakers()
            _log(f"GetSpeakers OK: {speakers}")

            # pycaw 20230407+: GetSpeakers returns AudioDevice wrapper — need ._dev
            device = getattr(speakers, '_dev', speakers)
            _log(f"device: {device}")

            iface = device.Activate(
                IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None
            )
            _log(f"Activate OK: {iface}")
            vol = iface.QueryInterface(IAudioEndpointVolume)
            _log(f"QueryInterface OK: {vol}")
            self._last_vol = float(vol.GetMasterVolumeLevelScalar())
            _log(f"Current volume: {self._last_vol:.4f}")
            self._ok = True
            return vol
        except Exception as e:
            _log(f"_init_com FAILED: {e}")
            self._ok = False
            return None


# Module-level singleton — starts its thread immediately
_vol_worker = VolumeWorker()


def get_volume() -> float:
    return _vol_worker.get()

def set_volume(level: float):
    _vol_worker.set(level)

def lock_screen():
    if not _LOCK_OK:
        return
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  Constants
# ══════════════════════════════════════════════════════════════════════════════

_SMOOTH_FRAMES   = 6      # frames averaged for Y smoothing
_VOL_MIN_CHANGE  = 0.012  # minimum change before calling set_volume
_PINCH_LOCK_HOLD = 1.5    # seconds to hold pinch before locking

# How much volume changes per unit of Y movement
# Full frame height (Y=0 to Y=1) = 150% volume range
# So moving hand across half the frame = ±75% volume
_VOL_PER_Y = 1.5


# ══════════════════════════════════════════════════════════════════════════════
#  GestureActionProcessor — called from scheduler, NEVER blocks
# ══════════════════════════════════════════════════════════════════════════════

class GestureActionProcessor:

    def __init__(self):
        self._y_history:     deque = deque(maxlen=_SMOOTH_FRAMES)
        self._baseline_y:    float = -1.0   # hand Y when fist first closed
        self._baseline_vol:  float = -1.0   # system volume when fist first closed
        self._last_set_vol:  float = -1.0
        self._pinch_since:   float = 0.0
        self._pinch_armed:   bool  = False
        self._lock_fired:    bool  = False
        self._last_label:    str   = "NONE"
        self.action_log:     deque = deque(maxlen=8)

    def process(self, event: dict):
        """Called on Textual main thread — returns instantly, no COM."""
        label  = event.get("gesture_label", "NONE")
        hand_y = event.get("hand_y", None)
        self._handle_fist_volume(label, hand_y)
        self._handle_pinch_lock(label)
        self._last_label = label

    def status(self) -> dict:
        """Returns cached state — no COM, no blocking."""
        return {
            "vol_available":  _vol_worker.available,
            "lock_available": _LOCK_OK,
            "volume":         _vol_worker.get(),
            "last_action":    self.action_log[-1] if self.action_log else "",
        }

    # ── FIST → relative volume control ────────────────────────────────────────
    def _handle_fist_volume(self, label: str, hand_y):
        if label != "FIST":
            # Fist released — reset everything so next engage starts fresh
            self._y_history.clear()
            self._baseline_y   = -1.0
            self._baseline_vol = -1.0
            self._last_set_vol = -1.0
            return

        if hand_y is None:
            return

        self._y_history.append(hand_y)
        if len(self._y_history) < 2:
            return

        smoothed_y = sum(self._y_history) / len(self._y_history)

        # First stable frame of this fist — capture baseline
        if self._baseline_y < 0:
            current_vol = _vol_worker.get()
            if current_vol < 0:
                return   # VolumeWorker not ready yet
            self._baseline_y   = smoothed_y
            self._baseline_vol = current_vol
            self._last_set_vol = current_vol
            return

        # Delta from where the fist started (negative Y = moved up = louder)
        delta_y  = smoothed_y - self._baseline_y   # negative = hand moved up
        delta_vol = -delta_y * _VOL_PER_Y           # moving up → positive vol change

        target_vol = max(0.0, min(1.0, self._baseline_vol + delta_vol))

        if abs(target_vol - self._last_set_vol) < _VOL_MIN_CHANGE:
            return

        set_volume(target_vol)   # non-blocking queue put
        prev = self._last_set_vol
        self._last_set_vol = target_vol

        arrow = "▲" if target_vol > prev else "▼"
        self._log(f"VOL {arrow}  {target_vol*100:.0f}%  (base {self._baseline_vol*100:.0f}%)")

    # ── PINCH hold → lock screen ──────────────────────────────────────────────
    def _handle_pinch_lock(self, label: str):
        if label == "PINCH":
            if not self._pinch_armed:
                self._pinch_since = time.time()
                self._pinch_armed = True
                self._lock_fired  = False
                self._log("PINCH — hold to lock…")
            elif not self._lock_fired:
                if time.time() - self._pinch_since >= _PINCH_LOCK_HOLD:
                    self._lock_fired = True
                    self._log("🔒 LOCKING…")
                    threading.Thread(target=lock_screen, daemon=True).start()
        else:
            if self._pinch_armed and not self._lock_fired:
                self._log("PINCH released (no lock)")
            self._pinch_armed = False
            self._lock_fired  = False

    def _log(self, msg: str):
        self.action_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")


# Module-level singleton
processor = GestureActionProcessor()
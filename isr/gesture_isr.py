"""
OrcaOS — GestureISR
Two-tier gesture detection with decoupled capture + inference threads.

Architecture (fixes freeze-on-fist):
  capture thread  → reads frames from camera at full speed → frame_queue
  inference thread → drains frame_queue → MediaPipe/OpenCV → gesture_queue

Tier 1: MediaPipe Tasks API  (requires hand_landmarker.task)
Tier 2: Pure OpenCV skin mask (automatic fallback, no model needed)
"""
import math
import os
import platform
import queue
import threading
import time
import traceback

import state as _state

try:
    import cv2
    import numpy as np
    _CV2_OK = True
except ImportError:
    _CV2_OK = False

try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision as mp_vision
    from mediapipe.tasks.python.core import base_options as mp_base_options
    _MP_OK = True
except Exception:
    _MP_OK = False

MODEL_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "hand_landmarker.task")
)

# ── landmark indices ──────────────────────────────────────────────────────────
_WRIST      = 0
_THUMB_TIP  = 4;  _THUMB_MCP  = 2
_INDEX_TIP  = 8;  _INDEX_MCP  = 5
_MIDDLE_TIP = 12; _MIDDLE_MCP = 9
_RING_TIP   = 16; _RING_MCP   = 13
_PINKY_TIP  = 20; _PINKY_MCP  = 17

# Intermediate PIP joints used for finger curl detection
_INDEX_PIP  = 6
_MIDDLE_PIP = 10
_RING_PIP   = 14
_PINKY_PIP  = 18


# ══════════════════════════════════════════════════════════════════════════════
#  Gesture classifier (MediaPipe 21-point landmarks)
# ══════════════════════════════════════════════════════════════════════════════

def _dist(a, b) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2)


def _classify_landmarks(landmarks) -> tuple[str, float]:
    lm = landmarks

    # Use PIP joints (not hardcoded indices) for more accurate curl detection
    finger_extended = [
        lm[_INDEX_TIP].y  < lm[_INDEX_PIP].y,
        lm[_MIDDLE_TIP].y < lm[_MIDDLE_PIP].y,
        lm[_RING_TIP].y   < lm[_RING_PIP].y,
        lm[_PINKY_TIP].y  < lm[_PINKY_PIP].y,
    ]
    thumb_extended = (
        abs(lm[_THUMB_TIP].x - lm[_WRIST].x) >
        abs(lm[_THUMB_MCP].x - lm[_WRIST].x)
    )
    n_up = sum(finger_extended)

    hand_size  = _dist(lm[_WRIST], lm[_MIDDLE_MCP])
    pinch_dist = _dist(lm[_THUMB_TIP], lm[_INDEX_TIP])
    pinch_norm = pinch_dist / max(hand_size, 1e-6)

    if n_up == 0 and not thumb_extended:
        tightness = 1.0 - min(
            _dist(lm[_MIDDLE_TIP], lm[_WRIST]) / max(hand_size, 1e-6), 1.0
        )
        return "FIST", round(tightness, 3)
    if pinch_norm < 0.25 and n_up <= 1:
        return "PINCH", round(1.0 - pinch_norm / 0.25, 3)
    if n_up == 4:
        openness = min(
            _dist(lm[_INDEX_TIP], lm[_PINKY_TIP]) / max(hand_size * 1.5, 1e-6), 1.0
        )
        return "OPEN", round(openness, 3)
    if n_up == 1 and finger_extended[0]:
        return "POINT", 1.0
    if n_up == 2 and finger_extended[0] and finger_extended[1]:
        return "PEACE", 1.0
    if thumb_extended and n_up == 0:
        return "THUMBS_UP", 1.0
    return "HOLD", round(n_up / 4, 3)


# ══════════════════════════════════════════════════════════════════════════════
#  Shared capture thread
# ══════════════════════════════════════════════════════════════════════════════

def _capture_loop(
    cap,
    frame_queue: queue.Queue,
    stop_event: threading.Event,
    fail_cb,
) -> None:
    """
    Reads frames from cap as fast as possible.
    Drops old frames if inference can't keep up (maxsize=2).
    """
    consecutive_fail = 0
    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret or frame is None:
            consecutive_fail += 1
            fail_cb(consecutive_fail)
            if consecutive_fail > 60:
                break
            time.sleep(0.01)
            continue
        consecutive_fail = 0
        # Drop oldest frame if inference is backed up
        if frame_queue.full():
            try:
                frame_queue.get_nowait()
            except queue.Empty:
                pass
        try:
            frame_queue.put_nowait((time.monotonic(), frame))
        except queue.Full:
            pass


def _make_fail_cb(camera_failed: threading.Event) -> callable:
    """Returns a failure callback that sets camera_failed after 60 misses."""
    def _fail_cb(n: int) -> None:
        if n > 60:
            camera_failed.set()
            _state.update_state(
                gesture_active=False,
                gesture_error="Camera stopped sending frames",
            )
    return _fail_cb


# ══════════════════════════════════════════════════════════════════════════════
#  Tier 1 — MediaPipe inference loop
# ══════════════════════════════════════════════════════════════════════════════

def _run_mediapipe(stop_event: threading.Event, cap, camera_idx: int) -> None:
    from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode
    from mediapipe.tasks.python.vision.core.image import Image, ImageFormat

    BaseOptions           = mp_base_options.BaseOptions
    HandLandmarker        = mp_vision.HandLandmarker
    HandLandmarkerOptions = mp_vision.HandLandmarkerOptions

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=VisionTaskRunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    _state.update_state(
        gesture_active=True, gesture_error="",
        gesture_cam_idx=camera_idx, gesture_backend="MediaPipe Tasks",
    )

    frame_queue   = queue.Queue(maxsize=2)
    camera_failed = threading.Event()

    cap_thread = threading.Thread(
        target=_capture_loop,
        args=(cap, frame_queue, stop_event, _make_fail_cb(camera_failed)),
        daemon=True, name="GestureCapture",
    )
    cap_thread.start()

    prev_time = time.monotonic()

    with HandLandmarker.create_from_options(options) as landmarker:
        while not stop_event.is_set() and not camera_failed.is_set():
            try:
                ts, frame = frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                rgb      = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = Image(image_format=ImageFormat.SRGB, data=rgb)
                ts_ms    = int(ts * 1000)
                result   = landmarker.detect_for_video(mp_image, ts_ms)

                now       = time.monotonic()
                fps       = 1.0 / max(now - prev_time, 1e-6)
                prev_time = now

                if result.hand_landmarks:
                    label, value = _classify_landmarks(result.hand_landmarks[0])
                    hand_y = result.hand_landmarks[0][_WRIST].y
                else:
                    label, value, hand_y = "NONE", 0.0, None

                _state.gesture_queue.put_nowait({
                    "gesture_label": label,
                    "gesture_value": value,
                    "gesture_fps":   round(fps, 1),
                    "hand_y":        hand_y,
                })
            except Exception as e:
                _state.update_state(gesture_error=f"MP frame error: {e}")

    cap_thread.join(timeout=2.0)


# ══════════════════════════════════════════════════════════════════════════════
#  Tier 2 — OpenCV skin-mask inference loop
# ══════════════════════════════════════════════════════════════════════════════

_HSV_LOWER = (0,  20,  70)
_HSV_UPPER = (20, 255, 255)
_MIN_AREA  = 8000


def _count_fingers_cv(contour) -> int:
    hull = cv2.convexHull(contour, returnPoints=False)
    if hull is None or len(hull) < 3:
        return 0
    try:
        defects = cv2.convexityDefects(contour, hull)
    except cv2.error:
        return 0
    if defects is None:
        return 0
    count = 0
    for i in range(defects.shape[0]):
        s, e, f, d = defects[i, 0]
        start = tuple(contour[s][0])
        far   = tuple(contour[f][0])
        end   = tuple(contour[e][0])
        a = math.dist(start, end)
        b = math.dist(far, start)
        c = math.dist(far, end)
        if b * c == 0:
            continue
        cos_angle = (b ** 2 + c ** 2 - a ** 2) / (2 * b * c)
        angle = math.acos(max(-1.0, min(1.0, cos_angle)))
        if d > 10000 and angle < math.pi / 2:
            count += 1
    return min(count + 1, 5)


def _classify_cv(n_fingers: int, area: int, hull_area: float) -> tuple[str, float]:
    solidity = area / hull_area if hull_area > 0 else 0.0
    if n_fingers == 0:   return "FIST",  round(min(solidity * 1.2, 1.0), 3)
    if n_fingers == 1:   return "POINT", 1.0
    if n_fingers == 2:   return "PINCH", round(solidity, 3)
    if n_fingers >= 4:   return "OPEN",  1.0
    return "HOLD", round(n_fingers / 5, 3)


def _run_opencv(stop_event: threading.Event, cap, camera_idx: int) -> None:
    _state.update_state(
        gesture_active=True, gesture_error="",
        gesture_cam_idx=camera_idx, gesture_backend="OpenCV skin",
    )

    frame_queue   = queue.Queue(maxsize=2)
    camera_failed = threading.Event()

    cap_thread = threading.Thread(
        target=_capture_loop,
        args=(cap, frame_queue, stop_event, _make_fail_cb(camera_failed)),
        daemon=True, name="GestureCapture",
    )
    cap_thread.start()

    kernel    = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    hsv_lower = np.array(_HSV_LOWER)
    hsv_upper = np.array(_HSV_UPPER)
    prev_time = time.monotonic()

    while not stop_event.is_set() and not camera_failed.is_set():
        try:
            _ts, frame = frame_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        label, value, hand_y = "NONE", 0.0, None
        try:
            blurred = cv2.GaussianBlur(frame, (7, 7), 0)
            hsv     = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
            mask    = cv2.inRange(hsv, hsv_lower, hsv_upper)
            mask    = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            mask    = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel, iterations=1)
            mask    = cv2.dilate(mask, kernel, iterations=1)
            conts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if conts:
                hand = max(conts, key=cv2.contourArea)
                area = int(cv2.contourArea(hand))
                if area >= _MIN_AREA:
                    hull_area      = cv2.contourArea(cv2.convexHull(hand))
                    n_fin          = _count_fingers_cv(hand)
                    label, value   = _classify_cv(n_fin, area, hull_area)
                    M              = cv2.moments(hand)
                    if M["m00"] > 0:
                        hand_y = M["m01"] / M["m00"] / frame.shape[0]
        except Exception as e:
            _state.update_state(gesture_error=f"CV frame error: {e}")

        now       = time.monotonic()
        fps       = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        try:
            _state.gesture_queue.put_nowait({
                "gesture_label": label,
                "gesture_value": value,
                "gesture_fps":   round(fps, 1),
                "hand_y":        hand_y,
            })
        except queue.Full:
            pass

    cap_thread.join(timeout=2.0)


# ══════════════════════════════════════════════════════════════════════════════
#  Camera open
# ══════════════════════════════════════════════════════════════════════════════

def _try_open_camera(camera_index: int, log: list[str]):
    is_win = platform.system() == "Windows"

    if is_win:
        candidates = [
            (camera_index, cv2.CAP_DSHOW, "DSHOW"),
            (camera_index, cv2.CAP_MSMF,  "MSMF"),
            (camera_index, cv2.CAP_ANY,   "ANY"),
        ]
        for alt in range(4):
            if alt != camera_index:
                candidates += [
                    (alt, cv2.CAP_DSHOW, f"DSHOW@{alt}"),
                    (alt, cv2.CAP_ANY,   f"ANY@{alt}"),
                ]
    else:
        candidates = [(camera_index, cv2.CAP_ANY, "ANY")]
        for alt in range(4):
            if alt != camera_index:
                candidates.append((alt, cv2.CAP_ANY, f"ANY@{alt}"))

    for idx, backend, name in candidates:
        log.append(f"trying index={idx} backend={name}")
        cap = None
        try:
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened():
                log[-1] += " -> not opened"
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, frame = cap.read()
            if not ret or frame is None:
                log[-1] += " -> no frame"
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            log[-1] += f" -> OK {frame.shape}"
            return cap, idx
        except Exception as e:
            log[-1] += f" -> exception: {e}"
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    return None, -1


# ══════════════════════════════════════════════════════════════════════════════
#  Main ISR entry
# ══════════════════════════════════════════════════════════════════════════════

def _gesture_loop(stop_event: threading.Event, camera_index: int = 0) -> None:
    open_log: list[str] = []

    if not _CV2_OK:
        _state.update_state(
            gesture_active=False,
            gesture_error="opencv-python not installed",
        )
        return

    cap, used_idx = _try_open_camera(camera_index, open_log)
    _state.update_state(gesture_open_log=open_log)

    if cap is None:
        _state.update_state(
            gesture_active=False,
            gesture_error="No camera found. Run: python camera_check.py",
        )
        return

    model_exists = os.path.exists(MODEL_PATH)
    use_mp       = _MP_OK and model_exists

    if _MP_OK and not model_exists:
        _state.update_state(
            gesture_error="Model missing — run: python download_model.py (falling back to OpenCV)"
        )

    try:
        if use_mp:
            _run_mediapipe(stop_event, cap, used_idx)
        else:
            _run_opencv(stop_event, cap, used_idx)
    except Exception:
        _state.update_state(
            gesture_active=False,
            gesture_error=f"GestureISR crash:\n{traceback.format_exc()[:300]}",
        )
    finally:
        try:
            cap.release()
        except Exception:
            pass
        _state.update_state(gesture_active=False)


def start(stop_event: threading.Event, camera_index: int = 0) -> threading.Thread:
    t = threading.Thread(
        target=_gesture_loop,
        args=(stop_event, camera_index),
        daemon=True, name="GestureISR",
    )
    t.start()
    return t

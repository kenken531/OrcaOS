"""
OrcaOS — GestureISR
Two-tier gesture detection:

  Tier 1 (preferred): MediaPipe Tasks API HandLandmarker
    - Needs: pip install mediapipe==0.10.35  +  hand_landmarker.task model
    - Works on Python 3.13+ (pure ctypes wheel, no ABI dependency)
    - Full 21-point hand landmarks → accurate FIST/OPEN/POINT/PINCH/HOLD

  Tier 2 (fallback): Pure OpenCV skin-mask + contour hull
    - No extra deps, works everywhere, less accurate
    - Automatically used if mediapipe/model not available

Install:
    pip install mediapipe==0.10.35
    python download_model.py
"""
import os
import threading
import time
import traceback
import math

from state import gesture_queue, update_state

# ── optional deps ─────────────────────────────────────────────────────────────
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

MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "hand_landmarker.task")
MODEL_PATH = os.path.normpath(MODEL_PATH)


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 1 — MediaPipe Tasks API  (21 landmarks, accurate)
# ══════════════════════════════════════════════════════════════════════════════

# Landmark indices (same across old + new mediapipe)
_WRIST       = 0
_THUMB_TIP   = 4;  _THUMB_MCP  = 2
_INDEX_TIP   = 8;  _INDEX_MCP  = 5
_MIDDLE_TIP  = 12; _MIDDLE_MCP = 9
_RING_TIP    = 16; _RING_MCP   = 13
_PINKY_TIP   = 20; _PINKY_MCP  = 17


def _dist(a, b) -> float:
    return math.sqrt((a.x - b.x)**2 + (a.y - b.y)**2)


def _classify_landmarks(landmarks) -> tuple:
    """
    Classify hand gesture from 21 MediaPipe NormalizedLandmarks.
    Returns (label, value 0-1).
    """
    lm = landmarks

    # Is each finger extended? tip.y < pip.y (image coords: up = lower y)
    # PIP joints: index=6, middle=10, ring=14, pinky=18
    finger_extended = [
        lm[_INDEX_TIP].y  < lm[6].y,
        lm[_MIDDLE_TIP].y < lm[10].y,
        lm[_RING_TIP].y   < lm[14].y,
        lm[_PINKY_TIP].y  < lm[18].y,
    ]
    # Thumb: compare x instead (works for both hands)
    thumb_extended = abs(lm[_THUMB_TIP].x - lm[_WRIST].x) > \
                     abs(lm[_THUMB_MCP].x  - lm[_WRIST].x)

    n_up = sum(finger_extended)

    # Thumb-index pinch distance (normalised by hand size)
    hand_size  = _dist(lm[_WRIST], lm[_MIDDLE_MCP])
    pinch_dist = _dist(lm[_THUMB_TIP], lm[_INDEX_TIP])
    pinch_norm = pinch_dist / max(hand_size, 1e-6)

    # ── classify ──────────────────────────────────────────────────────────────
    if n_up == 0 and not thumb_extended:
        # all fingers + thumb down → FIST
        # value = tightness (how close fingertips are to palm)
        tightness = 1.0 - min(_dist(lm[_MIDDLE_TIP], lm[_WRIST]) / max(hand_size, 1e-6), 1.0)
        return "FIST", round(tightness, 3)

    if pinch_norm < 0.25 and n_up <= 1:
        # thumb + index close = PINCH
        return "PINCH", round(1.0 - pinch_norm / 0.25, 3)

    if n_up == 4:
        # all four fingers up = OPEN (thumb doesn't matter)
        openness = min(
            _dist(lm[_INDEX_TIP], lm[_PINKY_TIP]) / max(hand_size * 1.5, 1e-6),
            1.0
        )
        return "OPEN", round(openness, 3)

    if n_up == 1 and finger_extended[0]:
        # only index finger → POINT
        return "POINT", 1.0

    if n_up == 2 and finger_extended[0] and finger_extended[1]:
        # index + middle → PEACE / scissors
        return "PEACE", 1.0

    if thumb_extended and n_up == 0:
        return "THUMBS_UP", 1.0

    # partial → HOLD
    return "HOLD", round(n_up / 4, 3)


def _run_mediapipe(stop_event: threading.Event, cap, camera_idx: int):
    """Main loop using MediaPipe Tasks HandLandmarker (VIDEO mode)."""
    from mediapipe.tasks.python.vision.core.vision_task_running_mode import VisionTaskRunningMode
    from mediapipe.tasks.python.vision.core.image import Image, ImageFormat

    BaseOptions     = mp_base_options.BaseOptions
    HandLandmarker  = mp_vision.HandLandmarker
    HandLandmarkerOptions = mp_vision.HandLandmarkerOptions

    options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=VisionTaskRunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    update_state(gesture_active=True, gesture_error="",
                 gesture_cam_idx=camera_idx, gesture_backend="MediaPipe Tasks")

    prev_time        = time.time()
    consecutive_fail = 0

    with HandLandmarker.create_from_options(options) as landmarker:
        while not stop_event.is_set():
            ret, frame = cap.read()
            if not ret or frame is None:
                consecutive_fail += 1
                if consecutive_fail > 60:
                    update_state(gesture_active=False,
                                 gesture_error="Camera stopped sending frames")
                    break
                time.sleep(0.033)
                continue
            consecutive_fail = 0

            try:
                rgb        = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image   = Image(image_format=ImageFormat.SRGB, data=rgb)
                ts_ms      = int(time.time() * 1000)
                result     = landmarker.detect_for_video(mp_image, ts_ms)

                now        = time.time()
                fps        = 1.0 / max(now - prev_time, 1e-6)
                prev_time  = now

                if result.hand_landmarks:
                    label, value = _classify_landmarks(result.hand_landmarks[0])
                    # wrist Y position (normalised 0=top 1=bottom) for volume control
                    hand_y = result.hand_landmarks[0][_WRIST].y
                else:
                    label, value = "NONE", 0.0
                    hand_y = None

                gesture_queue.put_nowait({
                    "gesture_label": label,
                    "gesture_value": value,
                    "gesture_fps":   round(fps, 1),
                    "hand_y":        hand_y,
                })
            except Exception as e:
                update_state(gesture_error=f"MP frame error: {e}")
                continue


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 2 — Pure OpenCV fallback  (skin mask + convex hull)
# ══════════════════════════════════════════════════════════════════════════════

_HSV_LOWER = (0,  20, 70)
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
        angle = math.acos(max(-1.0, min(1.0, (b**2 + c**2 - a**2) / (2 * b * c))))
        if d > 10000 and angle < math.pi / 2:
            count += 1
    return min(count + 1, 5)


def _classify_cv(n_fingers: int, area: int, hull_area: float) -> tuple:
    solidity = area / hull_area if hull_area > 0 else 0
    if n_fingers == 0:
        return "FIST", round(min(solidity * 1.2, 1.0), 3)
    elif n_fingers == 1:
        return "POINT", 1.0
    elif n_fingers == 2:
        return "PINCH", round(solidity, 3)
    elif n_fingers >= 4:
        return "OPEN", 1.0
    else:
        return "HOLD", round(n_fingers / 5, 3)


def _run_opencv(stop_event: threading.Event, cap, camera_idx: int):
    """Fallback loop using pure OpenCV skin detection."""
    update_state(gesture_active=True, gesture_error="",
                 gesture_cam_idx=camera_idx, gesture_backend="OpenCV skin")

    kernel           = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    prev_time        = time.time()
    consecutive_fail = 0

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret or frame is None:
            consecutive_fail += 1
            if consecutive_fail > 60:
                update_state(gesture_active=False,
                             gesture_error="Camera stopped sending frames")
                break
            time.sleep(0.033)
            continue
        consecutive_fail = 0

        try:
            blurred  = cv2.GaussianBlur(frame, (7, 7), 0)
            hsv      = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
            mask     = cv2.inRange(hsv, np.array(_HSV_LOWER), np.array(_HSV_UPPER))
            mask     = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            mask     = cv2.morphologyEx(mask, cv2.MORPH_OPEN,  kernel, iterations=1)
            mask     = cv2.dilate(mask, kernel, iterations=1)
            conts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not conts:
                label, value, hand_y = "NONE", 0.0, None
            else:
                hand      = max(conts, key=cv2.contourArea)
                area      = int(cv2.contourArea(hand))
                if area < _MIN_AREA:
                    label, value, hand_y = "NONE", 0.0, None
                else:
                    hull_area  = cv2.contourArea(cv2.convexHull(hand))
                    n_fin      = _count_fingers_cv(hand)
                    label, value = _classify_cv(n_fin, area, hull_area)
                    # centroid Y normalised to frame height
                    M          = cv2.moments(hand)
                    hand_y     = (M["m01"] / M["m00"] / frame.shape[0]
                                  if M["m00"] > 0 else None)
        except Exception as e:
            label, value, hand_y = "NONE", 0.0, None
            update_state(gesture_error=f"CV frame error: {e}")

        now       = time.time()
        fps       = 1.0 / max(now - prev_time, 1e-6)
        prev_time = now

        try:
            gesture_queue.put_nowait({
                "gesture_label": label,
                "gesture_value": value,
                "gesture_fps":   round(fps, 1),
                "hand_y":        hand_y,
            })
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  Camera open
# ══════════════════════════════════════════════════════════════════════════════

def _try_open_camera(camera_index: int, log: list):
    import platform
    is_win = platform.system() == "Windows"

    candidates = []
    if is_win:
        candidates = [
            (camera_index, cv2.CAP_DSHOW, "DSHOW"),
            (camera_index, cv2.CAP_MSMF,  "MSMF"),
            (camera_index, cv2.CAP_ANY,   "ANY"),
        ]
        for alt in range(4):
            if alt != camera_index:
                candidates += [(alt, cv2.CAP_DSHOW, f"DSHOW@{alt}"),
                               (alt, cv2.CAP_ANY,   f"ANY@{alt}")]
    else:
        candidates = [(camera_index, cv2.CAP_ANY, "ANY")]
        for alt in range(4):
            if alt != camera_index:
                candidates.append((alt, cv2.CAP_ANY, f"ANY@{alt}"))

    for idx, backend, name in candidates:
        log.append(f"trying index={idx} backend={name}")
        try:
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened():
                cap.release(); log[-1] += " -> not opened"; continue
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, frame = cap.read()
            if not ret or frame is None:
                cap.release(); log[-1] += " -> no frame"; continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            log[-1] += f" -> OK {frame.shape}"
            return cap, idx
        except Exception as e:
            log[-1] += f" -> exception: {e}"
            try: cap.release()
            except Exception: pass

    return None, -1


# ══════════════════════════════════════════════════════════════════════════════
#  Main ISR entry
# ══════════════════════════════════════════════════════════════════════════════

def _gesture_loop(stop_event: threading.Event, camera_index: int = 0):
    open_log = []

    if not _CV2_OK:
        update_state(gesture_active=False,
                     gesture_error="opencv-python not installed")
        return

    cap, used_idx = _try_open_camera(camera_index, open_log)
    update_state(gesture_open_log=open_log)

    if cap is None:
        update_state(gesture_active=False,
                     gesture_error="No camera found. Run: python camera_check.py")
        return

    # ── pick backend ──────────────────────────────────────────────────────────
    model_exists = os.path.exists(MODEL_PATH)
    use_mp       = _MP_OK and model_exists

    if _MP_OK and not model_exists:
        update_state(gesture_error=f"Model missing — run: python download_model.py  (falling back to OpenCV)")

    try:
        if use_mp:
            _run_mediapipe(stop_event, cap, used_idx)
        else:
            _run_opencv(stop_event, cap, used_idx)
    except Exception:
        update_state(gesture_active=False,
                     gesture_error=f"GestureISR crash:\n{traceback.format_exc()[:300]}")
    finally:
        try: cap.release()
        except Exception: pass
        update_state(gesture_active=False)


def start(stop_event: threading.Event, camera_index: int = 0):
    t = threading.Thread(
        target=_gesture_loop,
        args=(stop_event, camera_index),
        daemon=True,
        name="GestureISR",
    )
    t.start()
    return t
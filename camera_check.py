"""
camera_check.py — OrcaOS camera diagnostic
Run this BEFORE orcaos.py to find which index/backend works on your machine.

Usage:
    python camera_check.py
"""
import sys
import platform

print("=" * 55)
print("  OrcaOS Camera Diagnostic")
print(f"  Platform: {platform.system()} {platform.release()}")
print("=" * 55)

try:
    import cv2
    print(f"  OpenCV version: {cv2.__version__}")
except ImportError:
    print("  ERROR: opencv-python not installed")
    print("  Run: pip install opencv-python")
    sys.exit(1)

is_win = platform.system() == "Windows"

# Map of backend id → name
BACKENDS = {}
if is_win:
    BACKENDS = {
        cv2.CAP_DSHOW: "CAP_DSHOW (DirectShow)",
        cv2.CAP_MSMF:  "CAP_MSMF  (Media Foundation)",
        cv2.CAP_ANY:   "CAP_ANY   (auto)",
    }
else:
    BACKENDS = {
        cv2.CAP_ANY:   "CAP_ANY   (auto)",
        cv2.CAP_V4L2:  "CAP_V4L2",
    }

print()
print("  Scanning camera indices 0-3 with all backends...")
print()

found = []

for idx in range(4):
    for backend_id, backend_name in BACKENDS.items():
        try:
            cap = cv2.VideoCapture(idx, backend_id)
            opened = cap.isOpened()
            if opened:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ret, frame = cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    print(f"  [OK]  index={idx}  backend={backend_name}")
                    print(f"         frame shape: {w}x{h}")
                    found.append((idx, backend_id, backend_name))
                else:
                    print(f"  [--]  index={idx}  backend={backend_name}  → isOpened=True but no frame")
            else:
                print(f"  [xx]  index={idx}  backend={backend_name}  → not opened")
            cap.release()
        except Exception as e:
            print(f"  [!!]  index={idx}  backend={backend_name}  → exception: {e}")

print()
print("=" * 55)
if found:
    idx, _, name = found[0]
    print(f"  RECOMMENDATION:")
    print(f"    python orcaos.py --camera {idx}")
    print()
    print(f"  All working combinations:")
    for i, _, n in found:
        print(f"    index={i}  {n}")
else:
    print("  NO WORKING CAMERA FOUND")
    print()
    print("  Things to check:")
    print("  1. Is the camera physically connected / enabled?")
    print("  2. Is 'Camera privacy' ON in Windows Settings > Privacy > Camera?")
    print("  3. Is another app (Teams, Zoom, OBS) holding the camera?")
    print("  4. Try unplugging and replugging the camera")
    print("  5. Install/update the camera driver")
print("=" * 55)
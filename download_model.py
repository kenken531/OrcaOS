"""
OrcaOS — download_model.py
Downloads the hand_landmarker.task model needed for MediaPipe gesture detection.
Run once before orcaos.py.

Usage:
    python download_model.py
"""
import urllib.request
import os
import sys

MODEL_URL  = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
MODEL_PATH = os.path.join(os.path.dirname(__file__), "hand_landmarker.task")
MODEL_SIZE_MB = 9


def download():
    if os.path.exists(MODEL_PATH):
        size_mb = os.path.getsize(MODEL_PATH) / 1024 / 1024
        print(f"Model already exists: {MODEL_PATH}  ({size_mb:.1f} MB)")
        return

    print(f"Downloading hand_landmarker.task (~{MODEL_SIZE_MB} MB)...")
    print(f"  From: {MODEL_URL}")
    print(f"  To:   {MODEL_PATH}")
    print()

    def _progress(count, block_size, total):
        if total > 0:
            pct = min(count * block_size / total * 100, 100)
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"\r  [{bar}] {pct:5.1f}%", end="", flush=True)

    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH, reporthook=_progress)
        print()
        size_mb = os.path.getsize(MODEL_PATH) / 1024 / 1024
        print(f"\nDone — {size_mb:.1f} MB saved to {MODEL_PATH}")
    except Exception as e:
        print(f"\nDownload failed: {e}")
        print()
        print("Manual download:")
        print(f"  1. Open this URL in your browser:")
        print(f"     {MODEL_URL}")
        print(f"  2. Save the file as: hand_landmarker.task")
        print(f"  3. Place it in the orcaos/ folder next to orcaos.py")
        sys.exit(1)


if __name__ == "__main__":
    download()
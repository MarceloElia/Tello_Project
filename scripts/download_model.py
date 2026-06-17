#!/usr/bin/env python3
"""
download_model.py

Downloads the MediaPipe hand-landmarker model used by the gesture pipeline.
The model (~7.5 MB) is not committed to git; run this once after cloning:

    python scripts/download_model.py

It is saved to  src/tello_control/gesture/models/hand_landmarker.task,
exactly where tello_control.gesture.detector expects it.
"""

import os
import sys
import urllib.request

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)


def model_dir() -> str:
    """Locate the gesture/models directory (works installed or from a clone)."""
    try:
        import tello_control.gesture as g  # installed package
        return os.path.join(os.path.dirname(g.__file__), "models")
    except ImportError:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(repo_root, "src", "tello_control", "gesture", "models")


def main() -> int:
    target_dir = model_dir()
    os.makedirs(target_dir, exist_ok=True)
    target = os.path.join(target_dir, "hand_landmarker.task")

    if os.path.exists(target) and os.path.getsize(target) > 0:
        print(f"Model already present: {target}")
        return 0

    print(f"Downloading hand-landmarker model ...\n  from {MODEL_URL}\n  to   {target}")
    try:
        urllib.request.urlretrieve(MODEL_URL, target)
    except Exception as e:  # noqa: BLE001 - report any network/IO failure plainly
        print(f"Download failed: {e}", file=sys.stderr)
        return 1

    size_mb = os.path.getsize(target) / 1e6
    print(f"Done. Saved {size_mb:.1f} MB.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

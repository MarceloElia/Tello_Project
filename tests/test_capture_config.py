"""_apply_capture_config — webcam property pinning (latency optimization).

Tests the pure helper directly with a fake VideoCapture, so no real camera and no
MediaPipe model load are needed. VideoCapture properties are backend-dependent
*requests*; the helper reads them back, which is exactly what we assert on here.
"""

import cv2

from tello_control.gesture.detector import CaptureConfig, _apply_capture_config


class FakeCapture:
    """Records every .set(prop, value); .get() echoes the last set value."""

    def __init__(self):
        self.set_calls = []          # ordered list of (prop, value)
        self._store = {}

    def set(self, prop, value):
        self.set_calls.append((prop, value))
        self._store[prop] = value
        return True

    def get(self, prop):
        return self._store.get(prop, 0)


def test_all_props_issued():
    cap = FakeCapture()
    _apply_capture_config(cap, CaptureConfig())
    props = [p for p, _ in cap.set_calls]
    assert cv2.CAP_PROP_FOURCC in props
    assert cv2.CAP_PROP_FRAME_WIDTH in props
    assert cv2.CAP_PROP_FRAME_HEIGHT in props
    assert cv2.CAP_PROP_FPS in props
    assert cv2.CAP_PROP_BUFFERSIZE in props


def test_fourcc_set_before_resolution():
    """FOURCC must come first — many backends fix the allowed sizes after it."""
    cap = FakeCapture()
    _apply_capture_config(cap, CaptureConfig())
    props = [p for p, _ in cap.set_calls]
    assert props.index(cv2.CAP_PROP_FOURCC) < props.index(cv2.CAP_PROP_FRAME_WIDTH)
    assert props.index(cv2.CAP_PROP_FOURCC) < props.index(cv2.CAP_PROP_FRAME_HEIGHT)


def test_returns_effective_readback_values():
    cap = FakeCapture()
    info = _apply_capture_config(cap, CaptureConfig(width=640, height=480, fps=30))
    assert info["width"] == 640
    assert info["height"] == 480
    assert info["fps"] == 30
    assert info["buffersize"] == 1


def test_none_fields_skipped():
    """A field set to None must not be issued to the capture device."""
    cap = FakeCapture()
    _apply_capture_config(cap, CaptureConfig(fourcc=None, buffersize=None))
    props = [p for p, _ in cap.set_calls]
    assert cv2.CAP_PROP_FOURCC not in props
    assert cv2.CAP_PROP_BUFFERSIZE not in props
    assert cv2.CAP_PROP_FRAME_WIDTH in props

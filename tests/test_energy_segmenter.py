"""EnergySegmenter — pure energy-VAD state machine, fed with synthetic frames.

No microphone needed (per its own docstring). Verifies the reduced
silence_ms=500 default still closes segments correctly and doesn't
false-trigger on brief pauses shorter than the silence window.
"""

import numpy as np

from tello_control.voice.listener import EnergySegmenter, FRAME_LEN, FRAME_MS

THRESHOLD = 0.05


def _speech_frame():
    return np.full(FRAME_LEN, 0.5, dtype="float32")


def _silence_frame():
    return np.zeros(FRAME_LEN, dtype="float32")


def _feed_n(seg, frame_fn, n):
    result = None
    for _ in range(n):
        result = seg.feed(frame_fn())
    return result


def test_segment_closes_after_silence_ms():
    seg = EnergySegmenter(threshold=THRESHOLD, silence_ms=500, start_ms=200, preroll_ms=150)
    # onset: enough speech frames to start recording
    _feed_n(seg, _speech_frame, 200 // FRAME_MS + 1)
    # speak a bit more
    _feed_n(seg, _speech_frame, 5)
    silence_frames_needed = 500 // FRAME_MS
    # one frame short of the silence window -> no segment yet
    result = _feed_n(seg, _silence_frame, silence_frames_needed - 1)
    assert result is None
    # the final silence frame closes the segment
    result = seg.feed(_silence_frame())
    assert isinstance(result, np.ndarray)
    assert result.size > 0


def test_brief_pause_shorter_than_silence_window_does_not_close_segment():
    seg = EnergySegmenter(threshold=THRESHOLD, silence_ms=500, start_ms=200, preroll_ms=150)
    _feed_n(seg, _speech_frame, 200 // FRAME_MS + 1)
    # short pause well under the 500ms silence window
    short_pause = (500 // FRAME_MS) - 3
    result = _feed_n(seg, _silence_frame, short_pause)
    assert result is None
    # speech resumes -> segment must still be open (no premature close)
    result = seg.feed(_speech_frame())
    assert result is None


def test_no_speech_never_starts_a_segment():
    seg = EnergySegmenter(threshold=THRESHOLD, silence_ms=500, start_ms=200, preroll_ms=150)
    result = _feed_n(seg, _silence_frame, 50)
    assert result is None

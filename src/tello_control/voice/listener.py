"""
listener.py

Dauerhören mit Wake-Word für die Sprachsteuerung.

Statt ENTER-zum-Aufnehmen hört der Listener kontinuierlich über das Mikrofon,
erkennt Sprach-Segmente per einfacher Energie-VAD (RMS-Schwelle, reines numpy –
keine externe VAD-Bibliothek, läuft überall) und transkribiert jedes Segment.

Sicherheit: Ein Befehl wird nur weitergereicht, wenn das Transkript mit dem
Wake-Word ("Drohne") beginnt. Das Wort wird vor dem LLM entfernt.

Ablauf:
    Mikrofon → Frames (30 ms) → EnergySegmenter → fertiges Segment
             → Whisper → Text → strip_wake_word → Befehlstext (oder None)
"""

import queue
import re
import numpy as np
import sounddevice as sd

SAMPLERATE = 16000
FRAME_MS   = 30
FRAME_LEN  = SAMPLERATE * FRAME_MS // 1000   # 480 Samples
MIN_THRESHOLD = 0.01                          # untere Grenze der RMS-Schwelle


def _rms(frame: np.ndarray) -> float:
    """Lautstärke eines Frames als RMS (Root Mean Square)."""
    if frame.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))


def strip_wake_word(text: str, wake: str = "drohne") -> str | None:
    """
    Gibt den Befehlstext ohne führendes Wake-Word zurück, oder None wenn das
    Wake-Word fehlt. Tolerant gegenüber Groß/Klein, Satzzeichen und Whisper-
    Varianten (z.B. 'Drohne,', 'drone', 'die Drohne').
    """
    if not text:
        return None
    lowered = text.strip().lower()
    # Erlaubte Schreibweisen des Wake-Words
    variants = [wake, "drone", "drohnen"]
    # optionales führendes Füllwort ("hey", "die", "ok", "okay")
    pattern = r"^\s*(?:hey|ok|okay|die|der)?\s*(" + "|".join(map(re.escape, variants)) + r")\b[\s,.:!]*"
    m = re.match(pattern, lowered)
    if not m:
        return None
    rest = text.strip()[m.end():].strip()
    return rest


class EnergySegmenter:
    """
    Zustandsautomat, der aus einem Frame-Strom Sprach-Segmente schneidet.
    Reine Logik, ohne Mikrofon – dadurch mit synthetischen Frames testbar.

    feed(frame) gibt das fertige Segment (np.ndarray) zurück, sobald nach Sprache
    genug Stille kam; sonst None.
    """

    def __init__(self, threshold: float, frame_ms: int = FRAME_MS,
                 silence_ms: int = 800, start_ms: int = 200,
                 preroll_ms: int = 150):
        self.threshold = threshold
        self._silence_frames = max(1, silence_ms // frame_ms)
        self._start_frames   = max(1, start_ms // frame_ms)
        self._preroll        = max(1, preroll_ms // frame_ms)

        self._recording = False
        self._buffer: list[np.ndarray] = []
        self._preroll_buf: list[np.ndarray] = []
        self._silence_count = 0
        self._start_count = 0

    def feed(self, frame: np.ndarray) -> np.ndarray | None:
        speech = _rms(frame) > self.threshold

        if not self._recording:
            # Vorlauf-Puffer pflegen, damit der Sprechanfang nicht abgeschnitten wird
            self._preroll_buf.append(frame)
            if len(self._preroll_buf) > self._preroll:
                self._preroll_buf.pop(0)

            if speech:
                self._start_count += 1
                if self._start_count >= self._start_frames:
                    # Aufnahme starten – Vorlauf voranstellen
                    self._recording = True
                    self._buffer = list(self._preroll_buf)
                    self._preroll_buf = []
                    self._silence_count = 0
            else:
                self._start_count = 0
            return None

        # im Aufnahmezustand
        self._buffer.append(frame)
        if speech:
            self._silence_count = 0
        else:
            self._silence_count += 1
            if self._silence_count >= self._silence_frames:
                segment = np.concatenate(self._buffer)
                self._reset()
                return segment
        return None

    def _reset(self):
        self._recording = False
        self._buffer = []
        self._preroll_buf = []
        self._silence_count = 0
        self._start_count = 0


class ContinuousListener:
    """
    Hört dauerhaft über das Mikrofon und liefert transkribierte Sprach-Segmente.

    Nutzung:
        listener = ContinuousListener(transcriber)
        for text in listener.utterances():
            ...
        listener.close()
    """

    def __init__(self, transcriber, samplerate: int = SAMPLERATE,
                 silence_ms: int = 800, start_ms: int = 200,
                 calibrate_s: float = 1.0, energy_factor: float = 3.0):
        self._transcriber = transcriber
        self._samplerate = samplerate
        self._calibrate_s = calibrate_s
        self._energy_factor = energy_factor
        self._silence_ms = silence_ms
        self._start_ms = start_ms

        self._q: "queue.Queue[np.ndarray]" = queue.Queue()
        self._stream = None
        self._segmenter: EnergySegmenter | None = None

    def _callback(self, indata, frames, time_info, status):
        self._q.put(indata.copy().flatten())

    def _open_stream(self):
        self._stream = sd.InputStream(
            samplerate=self._samplerate, channels=1, dtype="float32",
            blocksize=FRAME_LEN, callback=self._callback,
        )
        self._stream.start()

    def _calibrate(self) -> float:
        """Misst den Grundpegel und leitet die Sprach-Schwelle ab."""
        print(f"Kalibriere Umgebungsgeräusch ({self._calibrate_s:.0f}s, bitte still sein) ...",
              flush=True)
        n_frames = int(self._calibrate_s * self._samplerate / FRAME_LEN)
        levels = []
        for _ in range(max(1, n_frames)):
            frame = self._q.get()
            levels.append(_rms(frame))
        noise_floor = float(np.median(levels)) if levels else 0.0
        threshold = max(noise_floor * self._energy_factor, MIN_THRESHOLD)
        print(f"Grundpegel: {noise_floor:.4f}  →  Sprach-Schwelle: {threshold:.4f}",
              flush=True)
        return threshold

    def utterances(self):
        """Generator: liefert pro erkanntem Sprach-Segment den transkribierten Text."""
        if self._stream is None:
            self._open_stream()
        threshold = self._calibrate()
        self._segmenter = EnergySegmenter(
            threshold=threshold, silence_ms=self._silence_ms, start_ms=self._start_ms,
        )
        print("🟢 Höre zu ...\n", flush=True)

        while True:
            frame = self._q.get()
            segment = self._segmenter.feed(frame)
            if segment is not None:
                text = self._transcriber.transcribe(segment)
                yield text

    def close(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

"""
stt.py

Speech-to-Text: Mikrofon-Aufnahme (sounddevice) → Text (faster-whisper).
Alles lokal, kein Cloud-Dienst.

Whisper erwartet 16 kHz Mono. Das Modell wird einmal geladen und wiederverwendet
(Laden dauert ein paar Sekunden, Transkription danach schnell).
"""

import sys
import queue
import numpy as np
import sounddevice as sd

SAMPLERATE = 16000   # Hz, von Whisper erwartet
CHANNELS   = 1


def record_audio(seconds: float = 4.0, samplerate: int = SAMPLERATE) -> np.ndarray:
    """Nimmt 'seconds' Sekunden Mono-Audio auf und gibt float32-Array [-1, 1] zurück."""
    print(f"🎙️  Aufnahme läuft ({seconds:.0f}s) – jetzt sprechen ...")
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate,
                   channels=CHANNELS, dtype="float32")
    sd.wait()
    print("⏹️  Aufnahme beendet.")
    return audio.flatten()


def record_until_silence(samplerate: int = SAMPLERATE, silence_ms: int = 500,
                         start_ms: int = 200, preroll_ms: int = 150,
                         max_seconds: float = 15.0, calibrate_s: float = 1.0,
                         energy_factor: float = 3.0) -> np.ndarray:
    """
    Nimmt so lange auf, bis nach Sprache genug Stille kam (statt eines festen
    Zeitfensters). Nutzt dieselbe Energie-VAD wie der Dauerhör-Modus. Bricht
    spätestens nach 'max_seconds' ab (Sicherheits-Cap bei Dauergeräusch).
    """
    from tello_control.voice.listener import EnergySegmenter, calibrate_threshold, FRAME_LEN

    q: "queue.Queue[np.ndarray]" = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata.copy().flatten())

    with sd.InputStream(samplerate=samplerate, channels=CHANNELS, dtype="float32",
                        blocksize=FRAME_LEN, callback=callback):
        threshold = calibrate_threshold(lambda: q.get(), samplerate,
                                        calibrate_s=calibrate_s, energy_factor=energy_factor)
        segmenter = EnergySegmenter(threshold=threshold, silence_ms=silence_ms,
                                    start_ms=start_ms, preroll_ms=preroll_ms)
        print("🎙️  Aufnahme läuft – jetzt sprechen (endet automatisch nach Sprechpause) ...")
        max_frames = int(max_seconds * samplerate / FRAME_LEN)
        for _ in range(max(1, max_frames)):
            frame = q.get()
            segment = segmenter.feed(frame)
            if segment is not None:
                print("⏹️  Aufnahme beendet.")
                return segment
        print("⏹️  Aufnahme beendet (max_seconds erreicht).")
        return segmenter.pending()


class Transcriber:
    """Lädt das Whisper-Modell einmal und transkribiert Audio zu deutschem Text."""

    def __init__(self, model_size: str = "small", compute_type: str = "int8",
                 language: str = "de"):
        # Import hier, damit das Modul auch ohne installiertes faster-whisper
        # importierbar bleibt (z.B. für reine Validierungs-Tests).
        from faster_whisper import WhisperModel
        print(f"Lade Whisper-Modell '{model_size}' (einmalig) ...", flush=True)
        self._model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        self._language = language
        print("Whisper bereit.")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transkribiert ein float32-Audioarray zu Text."""
        segments, _ = self._model.transcribe(
            audio, language=self._language, beam_size=5,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text

    def listen(self, seconds: float = 4.0) -> str:
        """Aufnehmen + transkribieren in einem Schritt."""
        audio = record_audio(seconds)
        return self.transcribe(audio)


import multiprocessing as mp


def _whisper_worker(model_size: str, compute_type: str, language: str,
                    in_q: "mp.Queue[np.ndarray | None]",
                    out_q: "mp.Queue[str]") -> None:
    from faster_whisper import WhisperModel
    model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
    out_q.put("ready")
    while True:
        audio = in_q.get()
        if audio is None:
            break
        segments, _ = model.transcribe(audio, language=language, beam_size=5)
        out_q.put(" ".join(seg.text.strip() for seg in segments).strip())


class ProcessTranscriber:
    """Whisper in a subprocess — listener loop stays live during transcription."""

    def __init__(self, model_size: str = "small", compute_type: str = "int8",
                 language: str = "de"):
        self._in_q: mp.Queue = mp.Queue(maxsize=1)
        self._out_q: mp.Queue = mp.Queue()
        self._proc = mp.Process(
            target=_whisper_worker,
            args=(model_size, compute_type, language, self._in_q, self._out_q),
            daemon=True,
        )
        print("Starte Whisper-Prozess ...", flush=True)
        self._proc.start()
        self._out_q.get()   # block until model is loaded
        print("Whisper bereit.")
        self._busy = False

    def submit(self, audio: np.ndarray) -> bool:
        """Send segment to worker. Returns False if already transcribing."""
        if self._busy:
            return False
        try:
            self._in_q.put_nowait(audio)
            self._busy = True
            return True
        except Exception:
            return False

    def poll(self) -> "str | None":
        """Non-blocking result check."""
        if not self._busy:
            return None
        try:
            text = self._out_q.get_nowait()
            self._busy = False
            return text
        except Exception:
            return None

    def transcribe(self, audio: np.ndarray) -> str:
        """Blocking — keeps drop-in compat with Transcriber."""
        self._in_q.put(audio)
        self._busy = True
        text = self._out_q.get()
        self._busy = False
        return text

    def close(self):
        try:
            self._in_q.put_nowait(None)
        except Exception:
            pass
        self._proc.join(timeout=3)
        if self._proc.is_alive():
            self._proc.kill()


if __name__ == "__main__":
    # Mini-Test: einmal aufnehmen und ausgeben
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
    t = Transcriber()
    text = t.listen(secs)
    print(f"\nErkannt: {text!r}")

"""
stt.py

Speech-to-Text: Mikrofon-Aufnahme (sounddevice) → Text (faster-whisper).
Alles lokal, kein Cloud-Dienst.

Whisper erwartet 16 kHz Mono. Das Modell wird einmal geladen und wiederverwendet
(Laden dauert ein paar Sekunden, Transkription danach schnell).
"""

import sys
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


if __name__ == "__main__":
    # Mini-Test: einmal aufnehmen und ausgeben
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 4.0
    t = Transcriber()
    text = t.listen(secs)
    print(f"\nErkannt: {text!r}")

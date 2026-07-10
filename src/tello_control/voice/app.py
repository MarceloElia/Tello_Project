"""
tello_control.voice.app

Haupt-Loop der Sprachsteuerung.

ENTER-Modus (Standard):
    python -m tello_control.voice.app             # Mock
    python -m tello_control.voice.app --real      # echte Drohne

Dauerhör-Modus (Wake-Word "Drohne"):
    python -m tello_control.voice.app --continuous
    python -m tello_control.voice.app --real --continuous

Ablauf ENTER-Modus:
    ENTER  → aufnehmen (endet automatisch nach Sprechpause) → transkribieren
           → Fastpath (einfache Befehle) oder LLM parst → validieren → Plan zeigen
           → automatisch ausführen (kein zweites ENTER nötig)
    q+ENTER→ beenden (landet vorher, falls in der Luft)

Ablauf Dauerhör-Modus:
    Dauerhaft hören → bei "Drohne ..." → LLM parst → validieren → ausführen
    Ctrl-C → beenden (landet vorher, falls in der Luft)

Sicherheit: Die komplette Befehlsliste wird validiert, BEVOR etwas ausgeführt wird.
Im ENTER-Modus ist das einmalige ENTER + das Aufnahmefenster das Sicherheits-Gate;
im Dauerhör-Modus ist es das Wake-Word (Auto-Ausführen nach "Drohne").
"""

import sys
import argparse

from tello_control.core.controller import DroneController
from tello_control.voice.stt import Transcriber, ProcessTranscriber
from tello_control.voice import llm_parser
from tello_control.voice.fastpath import try_fastpath
from tello_control.voice.commands import Command, ValidationError


def execute(ctrl: DroneController, commands: list[Command]):
    """Führt eine validierte Befehlsliste auf dem Controller aus."""
    for cmd in commands:
        try:
            if cmd.action == "takeoff":
                ctrl.takeoff()
            elif cmd.action == "land":
                ctrl.land()
            elif cmd.action == "emergency":
                ctrl.emergency()
            else:
                # forward/back/left/right/up/down/rotate_cw/rotate_ccw
                getattr(ctrl, cmd.action)(cmd.value)
        except Exception as e:
            print(f"  ⚠️  '{cmd}' fehlgeschlagen: {e}")
            print("  → Abbruch der restlichen Befehle.")
            break


def _handle_text(ctrl, text, model, real_mode, confirm):
    """Gemeinsamer Weg: Text → parsen → (optional bestätigen) → ausführen."""
    print(f"📝  Erkannt: {text!r}")
    if not text:
        print("  (nichts verstanden)\n")
        return

    commands = try_fastpath(text)
    if commands is not None:
        print("  [fastpath] Ollama übersprungen.")
    else:
        try:
            commands = llm_parser.parse(text, model=model)
        except (llm_parser.LLMError, ValidationError) as e:
            print(f"  ❌  {e}\n")
            return

    print("  Plan:")
    for c in commands:
        print(f"    • {c}")

    if confirm:
        ok = input("  Ausführen? [ENTER = ja, sonst abbrechen] ").strip()
        if ok != "":
            print("  Abgebrochen.\n")
            return

    execute(ctrl, commands)
    print()


def run_enter_mode(ctrl, transcriber, args, real_mode):
    from tello_control.voice.stt import record_until_silence

    print(f"\nENTER = aufnehmen (endet automatisch nach Sprechpause, max. {args.seconds:.0f}s),"
          " dann führt die Drohne automatisch aus.  q + ENTER = beenden.\n")
    while True:
        user = input("[ENTER zum Aufnehmen] ").strip().lower()
        if user == "q":
            break
        audio = record_until_silence(max_seconds=args.seconds)
        text = transcriber.transcribe(audio)
        # Sprechpause ist das Gate: sobald erkannt, sofort ausführen,
        # kein zweites ENTER zum Bestätigen.
        _handle_text(ctrl, text, args.model, real_mode, confirm=False)


def run_continuous_mode(ctrl, transcriber, args, real_mode):
    from tello_control.voice.listener import ContinuousListener, strip_wake_word

    listener = ContinuousListener(transcriber)
    wake = args.wake_word.lower()
    print(f"\nDauerhör-Modus aktiv. Sag: \"{args.wake_word}, <befehl>\"  –  Ctrl-C zum Beenden.")
    if real_mode:
        print("⚠️  ECHTE DROHNE: Befehle werden nach dem Wake-Word SOFORT ausgeführt.")
    try:
        for text in listener.utterances():
            if not text:
                continue
            command_text = strip_wake_word(text, wake)
            if command_text is None:
                print(f"   (kein Wake-Word: {text!r})")
                continue
            print(f"\n🔔  Wake-Word erkannt → {command_text!r}")
            # Dauerhör-Modus: Auto-Ausführen (Wake-Word ist das Gate)
            _handle_text(ctrl, command_text, args.model, real_mode, confirm=False)
    finally:
        listener.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="Echte Drohne statt Mock")
    parser.add_argument("--sim", action="store_true", help="Physik-Sim (PyBullet) statt Mock")
    parser.add_argument("--model", default=llm_parser.DEFAULT_MODEL, help="Ollama-Modell")
    parser.add_argument("--seconds", type=float, default=15.0,
                        help="Max. Aufnahmedauer (ENTER-Modus, endet sonst automatisch nach Sprechpause)")
    parser.add_argument("--whisper", default="small", help="Whisper-Modellgröße")
    parser.add_argument("--continuous", action="store_true", help="Dauerhören mit Wake-Word")
    parser.add_argument("--wake-word", default="drohne", help="Wake-Word für Dauerhören")
    args = parser.parse_args()

    backend = "real" if args.real else ("sim" if args.sim else "mock")
    mode = {"real": "ECHTE DROHNE", "sim": "SIM (PyBullet)", "mock": "Mock"}[backend]
    real_mode = backend == "real"
    print(f"\n=== Tello Sprachsteuerung ({mode}) ===")

    # Ollama sicherstellen (startet Server bei Bedarf selbst)
    try:
        llm_parser.ensure_ollama(args.model)
    except llm_parser.LLMError as e:
        print(f"\n❌  {e}\n")
        sys.exit(1)

    kw = {"gui": True, "speed": 1.5, "camera_follow": True} if backend == "sim" else None
    ctrl = DroneController(backend=backend, verbose=True, backend_kwargs=kw)
    ctrl.connect()

    transcriber = (ProcessTranscriber(model_size=args.whisper)
                   if args.continuous else Transcriber(model_size=args.whisper))

    try:
        if args.continuous:
            run_continuous_mode(ctrl, transcriber, args, real_mode)
        else:
            run_enter_mode(ctrl, transcriber, args, real_mode)
    except KeyboardInterrupt:
        print("\n[Ctrl-C] Beende ...")

    # Aufräumen
    if real_mode and getattr(ctrl.drone, "is_flying", False):
        ctrl.land()
    print("\n=== Session beendet ===")
    if backend in ("mock", "sim"):
        ctrl.report()
    ctrl.disconnect()


if __name__ == "__main__":
    main()

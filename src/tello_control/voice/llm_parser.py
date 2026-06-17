"""
llm_parser.py

Wandelt natürliche Sprache (deutscher Text) in eine validierte Befehlsliste um,
mithilfe eines lokalen LLM über Ollama. Alles offline, keine Cloud.

Pipeline:
    Text  →  Ollama (JSON-Modus)  →  parse_response()  →  validate_list()  →  [Command]

Die Ollama-Anbindung (_query_ollama) ist von der Parse-/Validierungslogik getrennt,
damit Letztere ohne laufenden Server testbar ist (parse_response mit Roh-JSON).
"""

import json
import shutil
import subprocess
import time
import urllib.request
import urllib.error

from tello_control.voice.commands import validate_list, ALLOWED_ACTIONS, Command, ValidationError

OLLAMA_HOST  = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5:3b"

SYSTEM_PROMPT = """Du bist ein Parser, der deutsche Sprachbefehle für eine Drohne in JSON übersetzt.

Erlaubte Aktionen:
- takeoff      : abheben / starten (kein Wert)
- land         : landen (kein Wert)
- emergency    : Notstopp / sofort alle Motoren aus (kein Wert)
- forward      : vorwärts fliegen (Wert in cm, 20-500)
- back         : rückwärts fliegen (Wert in cm, 20-500)
- left         : nach links fliegen (Wert in cm, 20-500)
- right        : nach rechts fliegen (Wert in cm, 20-500)
- up           : hochsteigen (Wert in cm, 20-500)
- down         : sinken (Wert in cm, 20-500)
- rotate_cw    : im Uhrzeigersinn / nach rechts DREHEN (Wert in Grad, 1-360)
- rotate_ccw   : gegen den Uhrzeigersinn / nach links DREHEN (Wert in Grad, 1-360)

Regeln:
- Antworte AUSSCHLIESSLICH mit JSON, kein erklärender Text.
- Format: {"commands": [ {"action": "...", "value": N}, ... ]}
- Aktionen ohne Wert (takeoff/land/emergency) haben KEIN "value"-Feld.
- Meter in cm umrechnen: 1 Meter = 100 cm.
- "ein halber Meter" / "einen halben Meter" / "ein halber Meter" = IMMER 50 cm (NICHT 150).
- "anderthalb Meter" / "eineinhalb Meter" = 150 cm. "zweieinhalb Meter" = 250 cm.
- Unterscheide BEWEGEN (left/right) von DREHEN (rotate_ccw/rotate_cw)!
  "nach links fliegen" = left, "nach links drehen" = rotate_ccw.
- Mehrere Befehle in der gesprochenen Reihenfolge auflisten.

Beispiele:
Eingabe: "heb ab und flieg zwei meter nach vorne"
Ausgabe: {"commands": [{"action": "takeoff"}, {"action": "forward", "value": 200}]}

Eingabe: "dreh dich um 90 grad nach rechts und dann lande"
Ausgabe: {"commands": [{"action": "rotate_cw", "value": 90}, {"action": "land"}]}

Eingabe: "steig einen halben meter hoch und flieg einen meter nach links"
Ausgabe: {"commands": [{"action": "up", "value": 50}, {"action": "left", "value": 100}]}

Eingabe: "flieg einen halben meter nach vorne"
Ausgabe: {"commands": [{"action": "forward", "value": 50}]}

Eingabe: "flieg anderthalb meter nach vorne"
Ausgabe: {"commands": [{"action": "forward", "value": 150}]}

Eingabe: "notstopp"
Ausgabe: {"commands": [{"action": "emergency"}]}"""


class LLMError(Exception):
    """Ollama nicht erreichbar oder lieferte keine brauchbare Antwort."""
    pass


# ---------- Autostart-Helfer ----------

def is_ollama_running(host: str = OLLAMA_HOST) -> bool:
    """True, wenn der Ollama-Server auf /api/tags antwortet."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


def installed_models(host: str = OLLAMA_HOST) -> list[str]:
    """Liste der in Ollama installierten Modellnamen (z.B. ['qwen2.5:3b'])."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return []
    return [m.get("name", "") for m in data.get("models", [])]


def ensure_ollama(model: str = DEFAULT_MODEL, host: str = OLLAMA_HOST,
                  timeout: int = 15) -> None:
    """
    Stellt sicher, dass der Ollama-Server läuft und das Modell vorhanden ist.
    Startet 'ollama serve' bei Bedarf selbst. Wirft LLMError mit klarer Meldung,
    wenn ollama fehlt, der Start scheitert oder das Modell nicht gepullt ist.
    """
    if shutil.which("ollama") is None:
        raise LLMError(
            "Ollama ist nicht installiert. Installation: 'brew install ollama'."
        )

    if not is_ollama_running(host):
        print("Ollama-Server nicht erreichbar – starte ihn ...", flush=True)
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,   # vom Python-Prozess lösen
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            if is_ollama_running(host):
                break
            time.sleep(0.5)
        else:
            raise LLMError(
                f"Ollama-Server startete nicht innerhalb von {timeout}s. "
                "Versuch es manuell mit 'ollama serve'."
            )
        print("Ollama-Server läuft.", flush=True)

    models = installed_models(host)
    # Toleranz für Tag-Schreibweisen (z.B. 'qwen2.5:3b' vs. 'qwen2.5:3b-...')
    if not any(m == model or m.startswith(model) for m in models):
        raise LLMError(
            f"Modell '{model}' ist nicht installiert. Bitte einmalig pullen:\n"
            f"    ollama pull {model}"
        )


def _query_ollama(text: str, model: str = DEFAULT_MODEL,
                  host: str = OLLAMA_HOST, timeout: int = 60) -> str:
    """Schickt den Text an Ollama (JSON-Modus) und gibt den rohen Antwort-String zurück."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},   # deterministisch
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/chat", data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise LLMError(
            f"Ollama nicht erreichbar unter {host}. Läuft 'ollama serve'? ({e})"
        )
    return body["message"]["content"]


def parse_response(raw_json: str) -> list[Command]:
    """Parst rohen JSON-String aus dem LLM und validiert ihn (ohne Ollama testbar)."""
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise LLMError(f"LLM lieferte kein gültiges JSON: {e}\nAntwort war: {raw_json!r}")
    return validate_list(payload)


def parse(text: str, model: str = DEFAULT_MODEL, host: str = OLLAMA_HOST) -> list[Command]:
    """Kompletter Weg: deutscher Text → validierte Befehlsliste."""
    raw = _query_ollama(text, model=model, host=host)
    return parse_response(raw)

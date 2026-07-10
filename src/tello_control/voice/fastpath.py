"""
fastpath.py

Keyword-Kurzschluss für einfache, eindeutige Sprachbefehle: überspringt den
Ollama-LLM-Call (~0.8s) für Ein-Klausel-Sätze, die sich verlustfrei per Regex
auf das bestehende Befehlsschema abbilden lassen.

Nur eindeutige Fälle matchen (verankerte Regex, keine Verkettung/"und dann").
Alles andere gibt None zurück und läuft weiter über llm_parser.parse().
Nutzt dieselbe Validierung wie der LLM-Pfad (validate_list) — keine eigene
Datenstruktur, kein Sicherheits-Bypass.
"""

import re

from tello_control.voice.commands import validate_list, Command

DEFAULT_DISTANCE_CM = 100   # Default, wenn Distanz-Befehl ohne Zahl gesprochen wird
DEFAULT_ANGLE_DEG   = 90    # Default, wenn Dreh-Befehl ohne Zahl gesprochen wird

# (Aktion, Regex). Regex matcht den kompletten (gestrippten, lowercased) Text.
# Gruppe 1, falls vorhanden, ist die Zahl (cm/m oder Grad).
_NUMBER = r"(?:\s+(?:um\s+)?(\d+)\s*(cm|m|meter|grad)?)?"

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("takeoff",    re.compile(r"^(start|starte|heb ab|hebe ab|abheben)$")),
    ("land",       re.compile(r"^(lande|landen|land)$")),
    ("emergency",  re.compile(r"^(notstopp|notaus|stopp|stop)$")),
    ("forward",    re.compile(r"^(vor|vorwärts|nach vorne|nach vorn)" + _NUMBER + r"$")),
    ("back",       re.compile(r"^(zurück|rückwärts)" + _NUMBER + r"$")),
    ("left",       re.compile(r"^(links|nach links)" + _NUMBER + r"$")),
    ("right",      re.compile(r"^(rechts|nach rechts)" + _NUMBER + r"$")),
    ("up",         re.compile(r"^(hoch|höher|steig|steige)" + _NUMBER + r"$")),
    ("down",       re.compile(r"^(runter|tiefer|sink|sinke)" + _NUMBER + r"$")),
    ("rotate_ccw", re.compile(r"^(dreh dich links|drehe dich links|dreh links|drehe links)"
                               + _NUMBER + r"$")),
    ("rotate_cw",  re.compile(r"^(dreh dich rechts|drehe dich rechts|dreh rechts|drehe rechts)"
                               + _NUMBER + r"$")),
]

_ANGLE_ACTIONS = {"rotate_cw", "rotate_ccw"}


def _resolve_value(action: str, number: str | None, unit: str | None) -> int | None:
    if action in ("takeoff", "land", "emergency"):
        return None
    if number is None:
        return DEFAULT_ANGLE_DEG if action in _ANGLE_ACTIONS else DEFAULT_DISTANCE_CM
    value = int(number)
    if unit in ("m", "meter"):
        value *= 100
    return value


def try_fastpath(text: str) -> "list[Command] | None":
    """
    Versucht, 'text' ohne LLM-Aufruf direkt in eine validierte Befehlsliste zu
    übersetzen. Gibt None zurück, wenn kein Muster eindeutig passt (dann muss
    llm_parser.parse() den Text übernehmen).
    """
    if not text:
        return None
    cleaned = text.strip().lower().rstrip(".!?")

    for action, pattern in _PATTERNS:
        m = pattern.match(cleaned)
        if not m:
            continue
        groups = m.groups()
        number, unit = (groups[-2], groups[-1]) if len(groups) >= 2 else (None, None)
        value = _resolve_value(action, number, unit)
        raw = {"action": action} if value is None else {"action": action, "value": value}
        try:
            return validate_list({"commands": [raw]})
        except Exception:
            return None   # außerhalb der SDK-Grenzen -> lieber LLM entscheiden lassen

    return None

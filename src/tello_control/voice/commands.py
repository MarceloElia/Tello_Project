"""
commands.py

Befehlsschema + Validierungs-Layer für die Sprachsteuerung.

Das LLM liefert eine JSON-Befehlsliste. Bevor irgendetwas die Drohne erreicht,
wird JEDER Befehl hier gegen das erlaubte Schema und die SDK-Grenzen geprüft.
Sicherheitsprinzip: Die GESAMTE Liste muss valide sein – schlägt ein Befehl fehl,
wird nichts ausgeführt (kein halb-gefährlicher Teilflug).

JSON-Format das vom LLM erwartet wird:
    {"commands": [
        {"action": "takeoff"},
        {"action": "forward", "value": 100},
        {"action": "rotate_cw", "value": 90},
        {"action": "land"}
    ]}
"""

from dataclasses import dataclass

# SDK-Grenzen (wie in MockTello / djitellopy)
MIN_DIST, MAX_DIST = 20, 500     # cm
MIN_ANGLE, MAX_ANGLE = 1, 360    # Grad

# Befehlsschema: action -> (braucht_wert, min, max, einheit)
# braucht_wert=False → Wert wird ignoriert/verboten
SCHEMA = {
    "takeoff":    (False, None, None, None),
    "land":       (False, None, None, None),
    "emergency":  (False, None, None, None),
    "forward":    (True, MIN_DIST, MAX_DIST, "cm"),
    "back":       (True, MIN_DIST, MAX_DIST, "cm"),
    "left":       (True, MIN_DIST, MAX_DIST, "cm"),
    "right":      (True, MIN_DIST, MAX_DIST, "cm"),
    "up":         (True, MIN_DIST, MAX_DIST, "cm"),
    "down":       (True, MIN_DIST, MAX_DIST, "cm"),
    "rotate_cw":  (True, MIN_ANGLE, MAX_ANGLE, "Grad"),
    "rotate_ccw": (True, MIN_ANGLE, MAX_ANGLE, "Grad"),
}

ALLOWED_ACTIONS = sorted(SCHEMA.keys())


class ValidationError(Exception):
    """Ein Befehl oder die Liste verletzt das Schema / die SDK-Grenzen."""
    pass


@dataclass
class Command:
    action: str
    value: int | None = None

    def __str__(self):
        return self.action if self.value is None else f"{self.action} {self.value}"


def validate_command(raw: dict) -> Command:
    """Prüft einen einzelnen Roh-Befehl (dict) und gibt ein Command zurück."""
    if not isinstance(raw, dict):
        raise ValidationError(f"Befehl ist kein Objekt: {raw!r}")

    action = raw.get("action")
    if action not in SCHEMA:
        raise ValidationError(
            f"Unbekannte Aktion '{action}'. Erlaubt: {', '.join(ALLOWED_ACTIONS)}"
        )

    needs_value, lo, hi, unit = SCHEMA[action]
    value = raw.get("value")

    if not needs_value:
        # takeoff/land/emergency dürfen keinen Wert haben
        return Command(action=action, value=None)

    if value is None:
        raise ValidationError(f"'{action}' braucht einen Wert ({lo}-{hi} {unit}).")

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"'{action}': Wert muss eine Zahl sein, war {value!r}.")

    value = int(round(value))
    if not (lo <= value <= hi):
        raise ValidationError(
            f"'{action}': {value} {unit} außerhalb des erlaubten Bereichs ({lo}-{hi} {unit})."
        )

    return Command(action=action, value=value)


def validate_list(payload: dict) -> list[Command]:
    """
    Prüft die komplette LLM-Antwort. Gibt eine Liste validierter Commands zurück
    oder wirft ValidationError (dann wird NICHTS ausgeführt).
    """
    if not isinstance(payload, dict) or "commands" not in payload:
        raise ValidationError("Antwort enthält kein 'commands'-Feld.")

    raw_list = payload["commands"]
    if not isinstance(raw_list, list) or not raw_list:
        raise ValidationError("'commands' ist leer oder keine Liste.")

    commands = [validate_command(raw) for raw in raw_list]
    return commands

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

from tello_control.core.constants import DIST_MIN, DIST_MAX, ANGLE_MIN, ANGLE_MAX


@dataclass(frozen=True)
class ActionSpec:
    requires_value: bool
    min_val: int | None = None
    max_val: int | None = None
    unit: str | None = None


# Befehlsschema: action → Spezifikation (Wert nötig, Grenzen, Einheit)
SCHEMA: dict[str, ActionSpec] = {
    "takeoff":    ActionSpec(False),
    "land":       ActionSpec(False),
    "emergency":  ActionSpec(False),
    "forward":    ActionSpec(True, DIST_MIN, DIST_MAX, "cm"),
    "back":       ActionSpec(True, DIST_MIN, DIST_MAX, "cm"),
    "left":       ActionSpec(True, DIST_MIN, DIST_MAX, "cm"),
    "right":      ActionSpec(True, DIST_MIN, DIST_MAX, "cm"),
    "up":         ActionSpec(True, DIST_MIN, DIST_MAX, "cm"),
    "down":       ActionSpec(True, DIST_MIN, DIST_MAX, "cm"),
    "rotate_cw":  ActionSpec(True, ANGLE_MIN, ANGLE_MAX, "Grad"),
    "rotate_ccw": ActionSpec(True, ANGLE_MIN, ANGLE_MAX, "Grad"),
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

    spec = SCHEMA[action]
    value = raw.get("value")

    if not spec.requires_value:
        # takeoff/land/emergency dürfen keinen Wert haben
        return Command(action=action, value=None)

    if value is None:
        raise ValidationError(
            f"'{action}' braucht einen Wert ({spec.min_val}-{spec.max_val} {spec.unit})."
        )

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"'{action}': Wert muss eine Zahl sein, war {value!r}.")

    value = int(round(value))
    if not (spec.min_val <= value <= spec.max_val):
        raise ValidationError(
            f"'{action}': {value} {spec.unit} außerhalb des erlaubten Bereichs "
            f"({spec.min_val}-{spec.max_val} {spec.unit})."
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

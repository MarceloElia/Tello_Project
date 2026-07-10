"""
tello_control.gesture.velocity_map

Kontinuierliche Geschwindigkeitssteuerung (RC-Modus) — Gegenstück zu command_map.py.

Statt diskreter 30-cm-Sprünge (blockierende move_*-Befehle mit Ack-Roundtrip)
übersetzt dieser Modus eine *gehaltene* Geste in einen RC-Sollwert
(send_rc_control, feuern-und-vergessen). Die Bewegung startet sofort mit der
Erkennung — kein Warten auf ein Ack.

Zwei kleine, reine Bausteine:
  gesture_to_velocity(gesture) → (lr, fb, ud, yaw)  Ziel-Sollwert der Geste
  VelocityBlender.update(target) → geglätteter Sollwert

Der Blender rampt pro Frame höchstens MAX_STEP an das Ziel heran. Das glättet
Start/Stopp UND filtert Einzelbild-Fehlklassifikationen quasi gratis: ein einziger
Ausreißer-Frame verschiebt die Geschwindigkeit nur um einen Schritt und wird
sofort wieder zurückgezogen. Deshalb braucht der RC-Modus kein Frame-Debounce.

RC-Konvention (wie djitellopy.send_rc_control):
  lr  > 0 = rechts     fb  > 0 = vorwärts
  ud  > 0 = hoch       yaw > 0 = im Uhrzeigersinn
"""

from tello_control.core.constants import RC_CRUISE
from tello_control.gesture.detector import Gesture

MAX_STEP = 8    # max. Änderung je Achse pro Frame (Beschleunigungs-Glättung)
DEADZONE = 3    # Beträge darunter → 0 (verhindert Zittern nahe null)

# Geste → Ziel-Geschwindigkeit (lr, fb, ud, yaw). Spiegelt _GESTURE_COMMANDS.
# OPEN_HAND fehlt bewusst: Landen ist diskret, die App fängt es separat ab.
_GESTURE_VELOCITY: dict[Gesture, tuple[int, int, int, int]] = {
    Gesture.POINT_FORWARD: (0,          RC_CRUISE, 0,          0),
    Gesture.PEACE:         (0,         -RC_CRUISE, 0,          0),
    Gesture.THUMBS_UP:     (0,          0,          RC_CRUISE, 0),
    Gesture.THUMBS_DOWN:   (0,          0,         -RC_CRUISE, 0),
    Gesture.POINT_RIGHT:   (RC_CRUISE,  0,          0,          0),
    Gesture.POINT_LEFT:    (-RC_CRUISE, 0,          0,          0),
    Gesture.FIST:          (0,          0,          0,          0),  # aktives Bremsen/Hover
}


def gesture_to_velocity(gesture: Gesture) -> tuple[int, int, int, int]:
    """Ziel-RC-Sollwert der Geste. Unbekannt/Landung → Hover (0,0,0,0)."""
    return _GESTURE_VELOCITY.get(gesture, (0, 0, 0, 0))


class VelocityBlender:
    """Rampt den ausgegebenen RC-Sollwert pro Frame an das Ziel heran."""

    def __init__(self, max_step: int = MAX_STEP, deadzone: int = DEADZONE):
        self._max_step = max_step
        self._deadzone = deadzone
        self._current = (0, 0, 0, 0)

    @property
    def current(self) -> tuple[int, int, int, int]:
        return self._current

    def _step(self, cur: int, target: int) -> int:
        delta = target - cur
        if delta >  self._max_step: delta =  self._max_step
        if delta < -self._max_step: delta = -self._max_step
        nxt = cur + delta
        return 0 if abs(nxt) < self._deadzone else nxt

    def update(self, target: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        self._current = tuple(self._step(c, t) for c, t in zip(self._current, target))
        return self._current

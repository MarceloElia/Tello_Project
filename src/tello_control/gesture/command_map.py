"""
tello_control.gesture.command_map

Übersetzt eine erkannte Geste in einen DroneController-Befehl.

Debounce: Geste muss STABLE_FRAMES Frames stabil sein → Befehl auslösen.
Cooldown: COOLDOWN_FRAMES Frames Pause nach Auslösung (verhindert Dauerfeuer).

Gesten-Map:
  FIST          → hover (kein Befehl, sicherer Default)
  THUMBS_UP     → up(30)
  THUMBS_DOWN   → down(30)
  POINT_FORWARD → forward(30)
  POINT_LEFT    → left(30)
  POINT_RIGHT   → right(30)
  PEACE         → back(30)
  OPEN_HAND     → land()
  UNKNOWN       → kein Befehl
"""

from typing import Callable

from tello_control.gesture.detector import Gesture

STABLE_FRAMES   = 8    # Frames die die Geste stabil gehalten werden muss
COOLDOWN_FRAMES = 20   # Frames Pause nach Auslösung

# Map: Gesture → (command name, controller call).  Extend here to add new gestures.
_GESTURE_COMMANDS: dict[Gesture, tuple[str, Callable]] = {
    Gesture.OPEN_HAND:     ("land",    lambda c: c.land()),
    Gesture.THUMBS_UP:     ("up",      lambda c: c.up(30)),
    Gesture.THUMBS_DOWN:   ("down",    lambda c: c.down(30)),
    Gesture.POINT_FORWARD: ("forward", lambda c: c.forward(30)),
    Gesture.POINT_LEFT:    ("left",    lambda c: c.left(30)),
    Gesture.POINT_RIGHT:   ("right",   lambda c: c.right(30)),
    Gesture.PEACE:         ("back",    lambda c: c.back(30)),
    Gesture.FIST:          ("hover",   lambda c: None),
}


class GestureToCommand:
    def __init__(self, controller, stable_frames=STABLE_FRAMES,
                 cooldown_frames=COOLDOWN_FRAMES, verbose=True):
        self._ctrl     = controller
        self._stable   = stable_frames
        self._cooldown = cooldown_frames
        self._verbose  = verbose

        self._current  = Gesture.UNKNOWN
        self._streak   = 0
        self._cooldown_left = 0

    def _log(self, msg):
        if self._verbose:
            print(f"[GestureCmd] {msg}")

    def feed(self, gesture: Gesture) -> str | None:
        """Pro Frame aufrufen. Gibt Befehlsnamen zurück wenn ausgelöst, sonst None."""
        if self._cooldown_left > 0:
            self._cooldown_left -= 1
            return None

        if gesture == self._current:
            self._streak += 1
        else:
            self._current = gesture
            self._streak  = 1

        if self._streak == self._stable:
            return self._dispatch(gesture)

        return None

    def _dispatch(self, gesture: Gesture) -> str | None:
        self._cooldown_left = self._cooldown
        entry = _GESTURE_COMMANDS.get(gesture)
        if entry is None:
            return None
        name, action = entry
        self._log(f"{gesture.name} → {name}")
        try:
            action(self._ctrl)
        except Exception as e:
            self._log(f"Fehler bei Befehl: {e}")
        return name

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

from tello_control.gesture.detector import Gesture

STABLE_FRAMES   = 8    # Frames die die Geste stabil gehalten werden muss
COOLDOWN_FRAMES = 20   # Frames Pause nach Auslösung


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

        try:
            if gesture == Gesture.OPEN_HAND:
                self._log("OPEN_HAND → land()")
                self._ctrl.land()
                return "land"

            if gesture == Gesture.THUMBS_UP:
                self._log("THUMBS_UP → up(30)")
                self._ctrl.up(30)
                return "up"

            if gesture == Gesture.THUMBS_DOWN:
                self._log("THUMBS_DOWN → down(30)")
                self._ctrl.down(30)
                return "down"

            if gesture == Gesture.POINT_FORWARD:
                self._log("POINT_FORWARD → forward(30)")
                self._ctrl.forward(30)
                return "forward"

            if gesture == Gesture.POINT_LEFT:
                self._log("POINT_LEFT → left(30)")
                self._ctrl.left(30)
                return "left"

            if gesture == Gesture.POINT_RIGHT:
                self._log("POINT_RIGHT → right(30)")
                self._ctrl.right(30)
                return "right"

            if gesture == Gesture.PEACE:
                self._log("PEACE → back(30)")
                self._ctrl.back(30)
                return "back"

            if gesture == Gesture.FIST:
                self._log("FIST → hover")
                return "hover"

        except Exception as e:
            self._log(f"Fehler bei Befehl: {e}")

        return None

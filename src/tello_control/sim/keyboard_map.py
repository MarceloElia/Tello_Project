"""
tello_control.sim.keyboard_map

Reine Tastenzuordnung für die Sim-Tastatursteuerung: gedrückte Tasten → RC-Sollwert.
Kein PyBullet, kein State — damit hardware- und sim-frei testbar.

RC-Konvention (wie djitellopy.send_rc_control):
  lr  > 0 = rechts     fb  > 0 = vorwärts
  ud  > 0 = hoch       yaw > 0 = im Uhrzeigersinn
"""

from __future__ import annotations

from tello_control.core.constants import RC_CRUISE

__all__ = ["keys_to_velocity", "HELP", "MOVE_KEYS",
           "TAKEOFF", "LAND", "HOVER", "QUIT", "CAM_TOGGLE"]

TAKEOFF    = "t"
LAND       = "l"
HOVER      = " "     # Leertaste: alle Achsen auf null
QUIT       = "q"
CAM_TOGGLE = "c"     # Kamera-Nachführung an/aus (aus = Maus frei zum Umkreisen)

# Taste -> (lr, fb, ud, yaw) als Vielfache von RC_CRUISE
MOVE_KEYS: dict[str, tuple[int, int, int, int]] = {
    "w": (0,  1,  0,  0),   # vorwärts
    "s": (0, -1,  0,  0),   # zurück
    "a": (-1, 0,  0,  0),   # links
    "d": (1,  0,  0,  0),   # rechts
    "r": (0,  0,  1,  0),   # hoch
    "f": (0,  0, -1,  0),   # runter
    "e": (0,  0,  0,  1),   # drehen im Uhrzeigersinn
    "z": (0,  0,  0, -1),   # drehen gegen Uhrzeigersinn
}

HELP = f"""
  Tastatursteuerung (Fokus im PyBullet-Fenster!)
  ─────────────────────────────────────────────
   {TAKEOFF}        Start           w / s    vor / zurück
   {LAND}        Landen          a / d    links / rechts
   Leer     Hover (Stopp)   r / f    hoch / runter
   {CAM_TOGGLE}        Kamera folgt    e / z    drehen cw / ccw
   {QUIT}        Beenden

  Kamera:  SHIFT halten = Kameramodus. Die Nachführung pausiert, die Drohne schwebt.
           Dann ziehen = um die Drohne kreisen, Scroll/Trackpad = zoomen.
           Loslassen -> die Kamera folgt wieder, dein Winkel und Zoom bleiben.
           '{CAM_TOGGLE}' schaltet die Nachführung dauerhaft ab (feste Ansicht).

  Halten = fliegen. Loslassen = Hover. Geschwindigkeit: {RC_CRUISE} (RC-Einheiten).
"""


def keys_to_velocity(pressed: set[str], cruise: int = RC_CRUISE) -> tuple[int, int, int, int]:
    """Summiert die gehaltenen Bewegungstasten zu einem RC-Sollwert.

    Gegensätzliche Tasten (w+s) heben sich auf. Die Leertaste erzwingt Hover und
    schlägt jede andere gehaltene Taste. Werte werden auf +/-cruise geklemmt, damit
    Diagonalen (w+d) nicht schneller sind als eine einzelne Achse.
    """
    if HOVER in pressed:
        return (0, 0, 0, 0)

    lr = fb = ud = yaw = 0
    for key in pressed:
        vec = MOVE_KEYS.get(key)
        if vec is None:
            continue
        lr += vec[0]
        fb += vec[1]
        ud += vec[2]
        yaw += vec[3]

    clamp = lambda v: max(-cruise, min(cruise, v * cruise))
    return (clamp(lr), clamp(fb), clamp(ud), clamp(yaw))

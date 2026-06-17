"""
gesture_detector.py

Klassifiziert Handgesten via MediaPipe Hands (Tasks-API, 0.10+).

ROBUSTE ERKENNUNG – winkelbasiert statt positionsbasiert:
  Ein Finger gilt als gestreckt, wenn der Winkel am Mittelgelenk (MCP→PIP→TIP)
  groß ist (~180° = gerade). Gekrümmt = kleiner Winkel. Das ist unabhängig von
  Handdrehung, -neigung und -größe – der Standard für regelbasiertes Fingerzählen.

Daumen-Richtung:
  Daumenspitze relativ zur Knöchel-Linie der vier Finger (MCP von 5/9/13/17).
  Spitze klar darüber → hoch, klar darunter → runter, dazwischen → Faust.

Links/Rechts mit Dead Zone:
  Bei ausgestrecktem Zeigefinger zählt der Winkel zur Senkrechten.
  Innerhalb ±DEADZONE_DEG = vorwärts (neutrale Zone), darüber hinaus links/rechts.

Gesten-Map:
  FIST          – alle Finger gekrümmt              → hover
  THUMBS_UP     – Faust, Daumen über Knöcheln       → up
  THUMBS_DOWN   – Faust, Daumen unter Knöcheln      → down
  POINT_FORWARD – nur Zeigefinger, senkrecht        → forward
  POINT_LEFT    – nur Zeigefinger, nach links       → left
  POINT_RIGHT   – nur Zeigefinger, nach rechts      → right
  PEACE         – Zeige- + Mittelfinger             → back
  OPEN_HAND     – alle vier Finger gestreckt        → land
  UNKNOWN       – kein eindeutiger Match
"""

import os
import math
from dataclasses import dataclass
from enum import Enum, auto

import cv2
import mediapipe as mp

_BaseOptions    = mp.tasks.BaseOptions
_HandLandmarker = mp.tasks.vision.HandLandmarker
_HandOptions    = mp.tasks.vision.HandLandmarkerOptions
_RunningMode    = mp.tasks.vision.RunningMode

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "hand_landmarker.task")

# --- Tuning-Parameter ---
EXTENDED_ANGLE  = 150   # Finger gilt ab diesem Gelenkwinkel als gestreckt (Grad)
THUMB_MARGIN    = 0.35  # Daumen-Schwelle als Anteil der Handgröße
DEADZONE_DEG    = 30    # ±Winkel um die Senkrechte = "vorwärts"
SIDE_MAX_DEG    = 110   # darüber hinaus zählt die Geste nicht mehr als Zeigen


class Gesture(Enum):
    FIST          = auto()
    THUMBS_UP     = auto()
    THUMBS_DOWN   = auto()
    POINT_FORWARD = auto()
    POINT_LEFT    = auto()
    POINT_RIGHT   = auto()
    PEACE         = auto()
    OPEN_HAND     = auto()
    UNKNOWN       = auto()


# Landmark-Indizes
WRIST = 0
THUMB_TIP = 4
# (MCP, PIP, TIP) je Finger
INDEX  = (5, 6, 8)
MIDDLE = (9, 10, 12)
RING   = (13, 14, 16)
PINKY  = (17, 18, 20)
FINGER_MCPS = (5, 9, 13, 17)
MIDDLE_MCP  = 9

HAND_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),
    (0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),
    (9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),
    (0,17),
]


def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def _angle_at(vertex, p1, p2):
    """Winkel (Grad) am Punkt 'vertex', gebildet durch p1-vertex-p2."""
    ax, ay = p1.x - vertex.x, p1.y - vertex.y
    bx, by = p2.x - vertex.x, p2.y - vertex.y
    dot = ax * bx + ay * by
    mag = math.hypot(ax, ay) * math.hypot(bx, by)
    if mag == 0:
        return 180.0
    return math.degrees(math.acos(max(-1.0, min(1.0, dot / mag))))


def _finger_extended(lms, finger):
    """Gestreckt, wenn der Winkel am PIP-Gelenk (MCP→PIP→TIP) groß genug ist."""
    mcp, pip, tip = finger
    return _angle_at(lms[pip], lms[mcp], lms[tip]) > EXTENDED_ANGLE


def _hand_size(lms):
    """Referenzgröße der Hand: Handgelenk → Mittelfinger-Knöchel."""
    return _dist(lms[WRIST], lms[MIDDLE_MCP])


def _thumb_direction(lms):
    """'up' / 'down' / None anhand Daumenspitze vs. Knöchel-Linie der Finger."""
    knuckle_y = sum(lms[i].y for i in FINGER_MCPS) / len(FINGER_MCPS)
    margin = THUMB_MARGIN * _hand_size(lms)
    tip_y = lms[THUMB_TIP].y
    if tip_y < knuckle_y - margin:
        return "up"
    if tip_y > knuckle_y + margin:
        return "down"
    return None


def _index_angle(lms):
    """Winkel des Zeigefingers zur Senkrechten. 0=hoch, negativ=links, positiv=rechts."""
    mcp, _, tip = INDEX
    dx = lms[tip].x - lms[mcp].x
    dy = lms[tip].y - lms[mcp].y
    return math.degrees(math.atan2(dx, -dy))


def classify(lms) -> Gesture:
    idx = _finger_extended(lms, INDEX)
    mid = _finger_extended(lms, MIDDLE)
    rng = _finger_extended(lms, RING)
    pky = _finger_extended(lms, PINKY)

    # Alle vier Finger gestreckt → offene Hand
    if idx and mid and rng and pky:
        return Gesture.OPEN_HAND

    # Alle vier gekrümmt → Daumen-Geste oder Faust
    if not idx and not mid and not rng and not pky:
        d = _thumb_direction(lms)
        if d == "up":
            return Gesture.THUMBS_UP
        if d == "down":
            return Gesture.THUMBS_DOWN
        return Gesture.FIST

    # Zeige + Mittel → Peace
    if idx and mid and not rng and not pky:
        return Gesture.PEACE

    # Nur Zeigefinger → Richtung mit Dead Zone
    if idx and not mid and not rng and not pky:
        ang = _index_angle(lms)
        if -DEADZONE_DEG <= ang <= DEADZONE_DEG:
            return Gesture.POINT_FORWARD
        if -SIDE_MAX_DEG < ang < -DEADZONE_DEG:
            return Gesture.POINT_LEFT
        if DEADZONE_DEG < ang < SIDE_MAX_DEG:
            return Gesture.POINT_RIGHT
        return Gesture.UNKNOWN

    return Gesture.UNKNOWN


@dataclass
class DetectionResult:
    gesture: Gesture
    landmarks: list | None
    frame_rgb: object


class GestureDetector:
    """
    Webcam-Modus (camera_index=0): stream() liefert gespiegelte Frames + Geste.
    Extern-Modus (camera_index=None): detect_frame(bgr) für fremde Frames.
    """

    def __init__(self, camera_index=0,
                 min_detection_confidence=0.7,
                 min_tracking_confidence=0.5):
        if not os.path.exists(_MODEL_PATH):
            raise FileNotFoundError(
                f"Modelldatei nicht gefunden: {_MODEL_PATH}\n"
                "Bitte einmalig herunterladen mit:\n"
                "    python scripts/download_model.py"
            )
        options = _HandOptions(
            base_options=_BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=_RunningMode.IMAGE,
            num_hands=1,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._landmarker = _HandLandmarker.create_from_options(options)

        self._cap = None
        if camera_index is not None:
            self._cap = cv2.VideoCapture(camera_index)
            if not self._cap.isOpened():
                raise RuntimeError(f"Webcam {camera_index} nicht erreichbar.")

    def detect_frame(self, frame_bgr) -> DetectionResult:
        """Verarbeitet einen einzelnen BGR-Frame."""
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
        result    = self._landmarker.detect(mp_image)

        if result.hand_landmarks:
            lm      = result.hand_landmarks[0]
            gesture = classify(lm)
        else:
            lm      = None
            gesture = Gesture.UNKNOWN

        return DetectionResult(gesture=gesture, landmarks=lm, frame_rgb=frame_rgb)

    def stream(self):
        """Generator für Webcam-Modus. Frame wird gespiegelt (intuitive Links/Rechts)."""
        if self._cap is None:
            raise RuntimeError("stream() nicht verfügbar im Extern-Modus.")
        while True:
            ok, frame_bgr = self._cap.read()
            if not ok:
                break
            frame_bgr = cv2.flip(frame_bgr, 1)   # Spiegeln wie ein Selfie
            yield self.detect_frame(frame_bgr)

    def annotate(self, frame_rgb, landmarks):
        if landmarks is None:
            return frame_rgb
        h, w = frame_rgb.shape[:2]
        out = frame_rgb.copy()
        pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
        for a, b in HAND_CONNECTIONS:
            cv2.line(out, pts[a], pts[b], (0, 200, 0), 2)
        for x, y in pts:
            cv2.circle(out, (x, y), 4, (255, 255, 255), -1)
        return out

    def close(self):
        if self._cap is not None:
            self._cap.release()
        self._landmarker.close()

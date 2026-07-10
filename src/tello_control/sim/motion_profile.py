"""
tello_control.sim.motion_profile

Beschleunigungsbegrenzte Sollwert-Führung für die Physik-Sim.

Warum das nötig ist: Der DSLPID-Regler bekommt einen Positions-Sollwert. Springt
dieser Sollwert (z.B. schlagartig 30 cm nach vorn), sieht der Regler einen Stufen-
eingang, gibt Vollgas und schwingt über — die Drohne wirkt ruckartig. Genauso wirkt
ein Sollwert, der zwar wandert, aber sofort mit voller Geschwindigkeit losläuft:
das ist ein Geschwindigkeitssprung, also unendliche Beschleunigung.

Diese Rampen führen den Sollwert stattdessen mit begrenzter Geschwindigkeit UND
begrenzter Beschleunigung ans Ziel. Das Profil ist trapezförmig (bzw. dreieckig bei
kurzen Strecken) und bremst rechtzeitig ab, weil die erlaubte Restgeschwindigkeit
aus der Bremsdistanz folgt:  v_stop = sqrt(2 · a · s).

Reines Python/NumPy, kein PyBullet — damit hardware- und sim-frei testbar.
"""

from __future__ import annotations

import math

import numpy as np

__all__ = ["VectorRamp", "YawRamp", "shortest_angle_diff"]

_EPS = 1e-9


def _approach_speed(dist: float, speed: float, dt: float, v_max: float, a_max: float) -> float:
    """Nächste Geschwindigkeit (>=0) auf dem Weg zu einem `dist` entfernten Ziel."""
    # So schnell darf man noch sein, um in `dist` mit a_max zum Stehen zu kommen.
    v_stop = math.sqrt(max(0.0, 2.0 * a_max * dist))
    v_target = min(v_max, v_stop)
    dv = max(-a_max * dt, min(a_max * dt, v_target - speed))
    return max(0.0, min(v_max, speed + dv))


class VectorRamp:
    """Führt einen 3D-Positions-Sollwert beschleunigungsbegrenzt ans Ziel.

    Die Bewegung läuft stets entlang der aktuellen Verbindungslinie zum Ziel; die
    Richtung wird pro Schritt neu bestimmt, damit ein bewegtes Ziel (RC-Modus)
    sauber verfolgt wird. Es wird nie über das Ziel hinausgeschossen.
    """

    def __init__(self, pos, v_max: float, a_max: float):
        self.pos = np.asarray(pos, dtype=float).copy()
        self.v_max = float(v_max)
        self.a_max = float(a_max)
        self.speed = 0.0

    def reset(self, pos) -> None:
        self.pos = np.asarray(pos, dtype=float).copy()
        self.speed = 0.0

    def advance(self, target, dt: float) -> np.ndarray:
        target = np.asarray(target, dtype=float)
        delta = target - self.pos
        dist = float(np.linalg.norm(delta))

        if dist < _EPS:
            self.speed = max(0.0, self.speed - self.a_max * dt)
            self.pos = target.copy()
            return self.pos

        self.speed = _approach_speed(dist, self.speed, dt, self.v_max, self.a_max)
        step = self.speed * dt
        if step >= dist:
            # Würde überschießen: exakt landen. Die Restgeschwindigkeit bleibt stehen
            # und wird ab dem nächsten Aufruf im dist<eps-Zweig mit a_max abgebaut.
            # Hier auf 0 zu setzen wäre genau der Geschwindigkeitssprung, den diese
            # Klasse verhindern soll (und ein bewegtes Ziel müsste danach aus dem
            # Stand neu beschleunigen).
            self.pos = target.copy()
        else:
            self.pos = self.pos + delta / dist * step
        return self.pos


def shortest_angle_diff(target: float, current: float) -> float:
    """Kürzeste Winkeldifferenz target-current in rad, im Bereich (-pi, pi].

    Bei exakt pi (180°-Wende) sind beide Richtungen gleich weit; wir liefern +pi,
    drehen also im Uhrzeigersinn. Die naive Formel `(d+pi) % 2pi - pi` gibt hier
    -pi zurück und würde die Drohne in die Gegenrichtung schicken.
    """
    d = (target - current) % (2.0 * math.pi)
    return d - 2.0 * math.pi if d > math.pi else d


class YawRamp:
    """Wie VectorRamp, aber für einen Winkel (rad) mit kürzestem Weg über den Kreis."""

    def __init__(self, yaw: float, v_max: float, a_max: float):
        self.yaw = float(yaw)
        self.v_max = float(v_max)
        self.a_max = float(a_max)
        self.speed = 0.0          # Betrag der Drehrate

    def reset(self, yaw: float) -> None:
        self.yaw = float(yaw)
        self.speed = 0.0

    def advance(self, target: float, dt: float) -> float:
        delta = shortest_angle_diff(target, self.yaw)
        dist = abs(delta)

        if dist < _EPS:
            self.speed = max(0.0, self.speed - self.a_max * dt)
            self.yaw = target
            return self.yaw

        self.speed = _approach_speed(dist, self.speed, dt, self.v_max, self.a_max)
        step = self.speed * dt
        if step >= dist:                      # exakt landen; Restrate baut der nächste Aufruf ab
            self.yaw = target
        else:
            self.yaw += math.copysign(step, delta)
        return self.yaw

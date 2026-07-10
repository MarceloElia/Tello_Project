"""
tello_control.sim.tuning_panel

Live-Regler im PyBullet-Fenster: Flugparameter und PID-Gains zur Laufzeit verstellen.

Aufbau wie bei keyboard_map.py: Die Spezifikation der Regler (Bereiche, Defaults) und
die Umrechnung in PID-Arrays sind reines Python/NumPy und damit ohne PyBullet testbar.
Nur `TuningPanel` fasst PyBullet an.

PyBullet-Details:
  * `addUserDebugParameter(name, lo, hi, start)` erzeugt einen Slider.
  * Ist `lo > hi`, entsteht stattdessen ein **Button**; sein gelesener Wert zählt bei
    jedem Klick um 1 hoch. Ein Klick wird also durch Vergleich mit dem letzten Wert erkannt.
  * Slider liegen in PyBullets GUI-Panel. Es muss über COV_ENABLE_GUI=1 sichtbar sein,
    sonst sind die Regler unsichtbar (aber lesbar).

Nicht enthalten: die Drehmoment-Gains P/I/D_COEFF_TOR (Werte um 70000). Kleine
Änderungen dort destabilisieren die Lageregelung sofort.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["Spec", "SPECS", "BUTTONS", "clamp", "pid_arrays", "defaults", "TuningPanel"]


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    lo: float
    hi: float
    default: float


# Defaults spiegeln die heutigen Werte aus pybullet_backend.py bzw. DSLPIDControl.
SPECS: tuple[Spec, ...] = (
    Spec("cruise_ms", "Speed [m/s]",       0.10, 2.00, 0.60),
    Spec("max_acc",   "Beschl. [m/s2]",    0.20, 5.00, 1.20),
    Spec("yaw_rate",  "Drehrate [deg/s]", 10.00, 360.0, 90.00),
    Spec("yaw_acc",   "Drehbeschl.",      30.00, 720.0, 240.0),
    Spec("rc_cruise", "RC-Speed",         10.00, 100.0, 40.00),
    Spec("p_xy",      "PID  P xy",         0.05, 1.20, 0.40),
    Spec("p_z",       "PID  P z",          0.20, 2.50, 1.25),
    Spec("i_xy",      "PID  I xy",         0.00, 0.30, 0.05),
    Spec("d_xy",      "PID  D xy",         0.00, 0.80, 0.20),
    Spec("d_z",       "PID  D z",          0.00, 1.50, 0.50),
)

# name -> Beschriftung. Buttons, nicht Slider.
BUTTONS: dict[str, str] = {
    "menu":      "<< Zurueck zum Menue",
    "reset_pid": "PID-Zustand zuruecksetzen",
    "defaults":  "Defaults wiederherstellen",
}

_BY_KEY = {s.key: s for s in SPECS}


def clamp(spec: Spec, value: float) -> float:
    """Wert in den erlaubten Bereich des Reglers zwingen."""
    return max(spec.lo, min(spec.hi, float(value)))


def defaults() -> dict[str, float]:
    return {s.key: s.default for s in SPECS}


def pid_arrays(p_xy: float, p_z: float, i_xy: float,
               d_xy: float, d_z: float) -> dict[str, np.ndarray]:
    """Slider-Werte -> die [x, y, z]-Arrays, die DSLPIDControl erwartet.

    I und D auf der z-Achse bleiben bei ihren Defaults (0.05 bzw. per Slider d_z),
    weil die Höhenregelung sonst zwei zusätzliche Regler bräuchte, ohne viel zu zeigen.
    """
    return {
        "P_COEFF_FOR": np.array([p_xy, p_xy, p_z], dtype=float),
        "I_COEFF_FOR": np.array([i_xy, i_xy, 0.05], dtype=float),
        "D_COEFF_FOR": np.array([d_xy, d_xy, d_z], dtype=float),
    }


class TuningPanel:
    """Slider + Buttons im PyBullet-Fenster. Braucht COV_ENABLE_GUI=1 zum Sehen.

    Ohne GUI (p.DIRECT) existieren Debug-Parameter nicht: `addUserDebugParameter`
    liefert dann eine unbrauchbare ID und `readUserDebugParameter` wirft `pybullet.error`.
    Das Panel degradiert deshalb still zu "Defaults, nie geklickt", statt die Flugschleife
    mitzureißen — headless laufende Tests und Benchmarks bleiben so lauffähig.
    """

    def __init__(self, client_id: int):
        import pybullet as p          # lokal: Modul bleibt ohne PyBullet importierbar

        self._p = p
        self._cid = client_id
        self._sliders: dict[str, int] = {}
        self._buttons: dict[str, int] = {}
        self._clicks: dict[str, float] = {}
        self._last: dict[str, float] = defaults()

        for spec in SPECS:
            self._sliders[spec.key] = p.addUserDebugParameter(
                spec.label, spec.lo, spec.hi, spec.default, physicsClientId=client_id
            )
        for name, label in BUTTONS.items():
            # lo > hi  =>  Button statt Slider
            self._buttons[name] = p.addUserDebugParameter(
                label, 1, 0, 0, physicsClientId=client_id
            )
            self._clicks[name] = 0.0

        self.available = self._probe()

    def _probe(self) -> bool:
        """Sind die Parameter wirklich lesbar? (Nur mit GUI der Fall.)"""
        try:
            uid = next(iter(self._sliders.values()))
            self._p.readUserDebugParameter(uid, physicsClientId=self._cid)
            return True
        except Exception:
            return False

    def read(self) -> dict[str, float]:
        """Aktuelle Sliderwerte. Ohne GUI: die zuletzt bekannten (= Defaults)."""
        if not self.available:
            return dict(self._last)
        try:
            self._last = {
                key: clamp(_BY_KEY[key],
                           self._p.readUserDebugParameter(uid, physicsClientId=self._cid))
                for key, uid in self._sliders.items()
            }
        except Exception:                 # Fenster zwischendurch geschlossen
            self.available = False
        return dict(self._last)

    def clicked(self, name: str) -> bool:
        """True genau einmal pro Klick auf den Button."""
        if not self.available:
            return False
        try:
            value = self._p.readUserDebugParameter(self._buttons[name],
                                                   physicsClientId=self._cid)
        except Exception:
            self.available = False
            return False
        fired = value > self._clicks[name]
        self._clicks[name] = value
        return fired

    def reset_to_defaults(self) -> dict[str, float]:
        """Slider können nicht gesetzt werden — also neu anlegen.

        PyBullet bietet kein setUserDebugParameter. `removeAllUserParameters` löscht
        allerdings *alle* Parameter des Clients, deshalb baut diese Methode Slider und
        Buttons komplett neu auf.
        """
        self._p.removeAllUserParameters(physicsClientId=self._cid)
        self.__init__(self._cid)
        return defaults()

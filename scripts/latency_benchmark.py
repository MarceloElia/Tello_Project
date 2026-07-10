"""
Latenz-Benchmark: diskrete move_*-Befehle vs. kontinuierliche RC-Steuerung.

Worum es geht
-------------
Diskrete Befehle (`move_forward(30)` …) blockieren in djitellopy auf einen
UDP-Ack-Roundtrip der Drohne — der Aufruf kehrt erst zurück, wenn die Drohne
bestätigt hat (~100–300 ms je nach WLAN). `send_rc_control(...)` ist dagegen
feuern-und-vergessen: ein UDP-Paket, kein Ack, sofortige Rückkehr.

Dieses Skript *modelliert* diesen Unterschied: ein MockTello mit konfigurierbarer
`ack_delay` in den move_*-Methoden (RC bleibt verzögerungsfrei). Es misst so den
architektonischen Latenz-/Durchsatz-Vorteil, ohne echte Hardware. Die echten
Zahlen liefert später ein Lauf mit `--real` an der Drohne.

    python scripts/latency_benchmark.py
    python scripts/latency_benchmark.py --commands 100 --ack-delays 0 100 200 300
"""

import argparse
import time

from tello_control.core.controller import DroneController
from tello_control.core.mock_tello import MockTello


class _LatencyMockTello(MockTello):
    """MockTello, das den blockierenden Ack-Roundtrip echter move_*-Befehle nachbildet.

    Nur die diskreten Bewegungsbefehle warten `ack_delay` Sekunden; send_rc_control
    erbt unverändert (kein Delay) — genau der Unterschied, den wir messen wollen.
    """

    def __init__(self, ack_delay=0.0, **kw):
        super().__init__(**kw)
        self._ack_delay = ack_delay

    def move_forward(self, cm):
        time.sleep(self._ack_delay)      # UDP-Ack-Roundtrip der echten Drohne
        super().move_forward(cm)


def _time_calls(fn, n):
    """Ruft fn() n-mal auf, gibt (Gesamtzeit_s, ms_pro_Aufruf, Aufrufe_pro_s) zurück."""
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    total = time.perf_counter() - t0
    per_cmd_ms = total / n * 1000
    rate = n / total if total > 0 else float("inf")
    return total, per_cmd_ms, rate


def _bench_row(ack_delay, n):
    # Diskret: Controller mit dem ack_delay-Backend (Drohne vor connect ersetzen).
    disc = DroneController(backend="mock", verbose=False)
    disc.drone = _LatencyMockTello(ack_delay=ack_delay, verbose=False)
    disc.connect(); disc.takeoff()
    _, disc_ms, disc_rate = _time_calls(lambda: disc.forward(30), n)

    # RC: feuern-und-vergessen, kein Ack.
    rc = DroneController(backend="mock", verbose=False)
    rc.connect(); rc.takeoff()
    _, rc_ms, rc_rate = _time_calls(lambda: rc.send_rc_control(0, 40, 0, 0), n)

    saved_ms = disc_ms - rc_ms   # eingesparte Latenz pro Befehl (~ ack_delay)
    return disc_ms, disc_rate, rc_ms, rc_rate, saved_ms


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--commands", type=int, default=50,
                        help="Anzahl Befehle pro Messung (Default 50)")
    parser.add_argument("--ack-delays", type=int, nargs="+", default=[0, 50, 100, 200, 300],
                        help="Modellierte Ack-Verzögerungen in ms (Default 0 50 100 200 300)")
    args = parser.parse_args()

    n = args.commands
    print(f"\nLatenz-Benchmark  ·  {n} Befehle je Messung")
    print("Modell: move_forward() blockiert auf ack_delay, send_rc_control() feuert-und-vergisst.\n")
    header = (f"{'Ack':>6} | {'diskret/Befehl':>14} | {'diskret Rate':>13} | "
              f"{'RC/Befehl':>10} | {'gespart/Befehl':>14}")
    print(header)
    print("-" * len(header))

    for ack_ms in args.ack_delays:
        disc_ms, disc_rate, rc_ms, rc_rate, saved_ms = _bench_row(ack_ms / 1000.0, n)
        print(f"{ack_ms:>4}ms | {disc_ms:>11.2f} ms | {disc_rate:>9.0f}/s | "
              f"{rc_ms:>7.3f} ms | {saved_ms:>11.2f} ms")

    print("\nHinweis: reines Modell der Kommando-Ebene. Der echte Ack-Roundtrip hängt vom")
    print("WLAN ab; live kappt zusätzlich der busy-drop des AsyncCommandRunner den")
    print("diskreten Durchsatz. Echte Zahlen: an der Drohne mit --real messen.")


if __name__ == "__main__":
    main()

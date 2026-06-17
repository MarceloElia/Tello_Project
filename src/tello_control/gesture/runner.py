"""
command_runner.py

Entkoppelt die (blockierenden) Flugbefehle von der Webcam-/Anzeige-Schleife.

Problem: Im Main-Thread laufen Frame-Capture, MediaPipe-Inferenz und cv2-Anzeige.
Ruft eine Geste einen Flugbefehl auf (im Sim die Physik-Schleife, real der
blockierende djitellopy-Call), friert das Webcam-Bild für die Flugdauer ein.

Lösung: Ein einzelner Worker-Thread arbeitet die Befehle ab. Der Main-Thread
bleibt frei für Kamera + Anzeige (cv2/PyBullet-GUI müssen ohnehin im Main-Thread
laufen). Nur der Worker fasst die Drohne/PyBullet an → keine Race Conditions.

Benutzung:
    runner   = AsyncCommandRunner(ctrl)
    commander = GestureToCommand(ThreadedCtrlAdapter(runner))
    ...
    runner.stop()   # beim Beenden
"""

import queue
import threading


class AsyncCommandRunner:
    """Führt Controller-Methoden in einem Hintergrund-Thread aus.

    Während ein Befehl läuft (_busy gesetzt), werden neue Befehle verworfen –
    Flugbefehle sollen sich nicht stapeln.
    """

    def __init__(self, ctrl, verbose=True):
        self._ctrl    = ctrl
        self._verbose = verbose
        self._q       = queue.Queue()
        self._busy    = threading.Event()
        self._stop    = threading.Event()
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _log(self, msg):
        if self._verbose:
            print(f"[CmdRunner] {msg}")

    @property
    def busy(self) -> bool:
        return self._busy.is_set()

    def submit(self, method_name: str, *args) -> bool:
        """Befehl einreihen. Gibt False zurück, wenn gerade ein Befehl läuft."""
        if self._busy.is_set():
            self._log(f"busy → '{method_name}' verworfen")
            return False
        self._q.put((method_name, args))
        return True

    def _loop(self):
        while not self._stop.is_set():
            try:
                method_name, args = self._q.get(timeout=0.1)
            except queue.Empty:
                continue
            self._busy.set()
            try:
                getattr(self._ctrl, method_name)(*args)
            except Exception as e:
                self._log(f"Fehler bei '{method_name}': {e}")
            finally:
                self._busy.clear()
                self._q.task_done()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2.0)


class ThreadedCtrlAdapter:
    """Sieht aus wie der DroneController, leitet Methodenaufrufe aber an den
    AsyncCommandRunner weiter (nicht-blockierend).

    So bleibt GestureToCommand unverändert: ein `adapter.up(30)` reiht den Befehl
    nur ein, statt zu blockieren.
    """

    def __init__(self, runner: AsyncCommandRunner):
        self._runner = runner

    def __getattr__(self, name):
        return lambda *args: self._runner.submit(name, *args)

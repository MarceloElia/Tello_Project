# Projektstand – Tello-Steuerungssystem

> Lebendes Statusdokument. Nach jeder Session aktualisieren (Datum + offene Punkte).
> Aufruf-/Startbefehle stehen in `COMMANDS.md` (gleicher Ordner), nicht hier.

**Stand:** 2026-06-17
**Aktive Phase:** A3 Kern fertig (PyBullet-Sim) · A0 + A1 + A2 + A3-Kern stehen
**Letztes Ergebnis (2026-06-17):** GitHub-Umbau zu installierbarem Paket. Code nach
`src/tello_control/{core,gesture,voice,sim,hardware}/`, sys.path-Hacks raus, absolute
Imports, `pyproject.toml` + console-scripts, `requirements.txt`, `environment-sim.yml`,
`.gitignore`, MIT-`LICENSE`, hardware-freie pytest-Suite (46 Tests grün). Modell jetzt
per `scripts/download_model.py` (nicht committed). Englisches `README.md` +
`docs/PROJECT.pdf` (Tiefen-Doku) erstellt. Aufrufe: siehe `COMMANDS.md`.

**Offen über alle Phasen:**
- Echte-Drohne-Tests für A1 (Gesten) und A2 (Sprache) – braucht Hardware.
- GUI-Live-Run der Sim durch den User.
- Optional: ROS-2-Layer (CV-Ziel), A4-Integration.

---

## Aufgaben nach Phase

### A0 · Fundament & Architektur ✅ FERTIG
- [x] venv + djitellopy eingerichtet
- [x] Verbindungs-/Telemetrietest (Akku 86 %, Sensor-Werte)
- [x] Erster Flugtest: takeoff()/land() auf echter Drohne
- [x] Würfel-Demo auf echter Drohne
- [x] DroneController-Abstraktion
- [x] MockTello: Position, Protokoll, Karte, Sicherheitsprüfungen

### A1 · Gestensteuerung (MediaPipe) ✅ FERTIG (bis auf echte Drohne)
- [x] MediaPipe (Tasks-API 0.10+, `gesture/hand_landmarker.task` lokal)
- [x] Winkelbasierter Klassifikator (orientierungsunabhängig, nicht nur Position)
- [x] Gesten-Map (Tabelle unten)
- [x] Debounce (N Frames stabil) + Befehlsauslösung
- [x] Gegen MockTello getestet, live mit Webcam getestet (funktioniert gut)
- [ ] Gegen echte Drohne testen (Hardware)

**Gesten-Map (final, `gesture/gesture_to_command.py`):**
| Geste                   | Befehl     |
|-------------------------|------------|
| Faust                   | hover      |
| Daumen hoch             | up 30      |
| Daumen runter           | down 30    |
| Zeigefinger senkrecht   | forward 30 |
| Zeigefinger nach links  | left 30    |
| Zeigefinger nach rechts | right 30   |
| Peace (✌️)              | back 30    |
| Offene Hand             | land       |

Bild gespiegelt (Selfie), Dead Zone ±30° um die Senkrechte für forward.

### A2 · Sprachsteuerung (lokales LLM) ✅ FERTIG (bis auf echte Drohne)
- [x] faster-whisper 1.2.1 + sounddevice
- [x] Ollama, Modell `qwen2.5:3b` gepullt + In-App-Autostart (`ensure_ollama()`)
- [x] `voice/commands.py` – Schema + Validierung (8 Negativfälle abgewiesen)
- [x] `voice/llm_parser.py` – Text → JSON, deutsches Few-Shot, Temp 0
      (Bugfix: „einen halben Meter" → 50, war vorher 150)
- [x] `voice/stt.py` – Mikrofon → faster-whisper (deutsch)
- [x] `voice/listener.py` – Dauerhören + Wake-Word „Drohne" (Energie-VAD, pur numpy)
- [x] `voice/voice_run.py` – ENTER- und Dauerhör-Modus, Bestätigung vor echtem Flug
- [x] Live-Mikrofontest (funktioniert gut, Whisper `small` reicht)
- [ ] Live-Test Dauerhören (energy_factor ggf. justieren)
- [ ] Gegen echte Drohne testen (Hardware)

### A3 · Simulation (PyBullet / gym-pybullet-drones) ✅ KERN FERTIG
Statt Gazebo: PyBullet (nativ auf M1, kein Docker, echte Quadrotor-Physik, fertige PID-Regler).
- [x] Machbarkeit M1 geklärt → PyBullet nativ (Gazebo verworfen wegen GUI-Schmerz)
- [x] conda-Env `tello-sim` (Python 3.11)
- [x] `sim/pybullet_backend.py` – erbt von MockTello, treibt Physik (3D-Fenster), Pose 1:1 wie Mock
- [x] `drone_controller.py` – Backend-Auswahl `mock|sim|real` (+ Abwärtskompat `simulated=`)
- [x] `sim/demo_sim.py` – Würfel-Flug, Report deckt sich mit Mock
- [x] `sim/control_lab.py` – PID-Sprungantwort + Plot
- [x] `sim/run.py` – Test-Launcher (Menü, jeder Modus eigener Prozess)
- [x] Gesten/Sprache gegen Sim integriert (`--sim`, mediapipe+whisper in tello-sim)
- [ ] GUI-Live-Run durch User
- [ ] Optional: ROS-2-Layer (Pose/Cmd als Topics, nativ auf M1)

### A3.5 · Flugregelung – im Sim umgesetzt
Erkenntnis: echter Tello erlaubt nur Velocity-Setpoints, kein Motorzugriff → geht nur im Sim.
`sim/control_lab.py`: P-Gain-Vergleich an 1-m-X-Sprung, misst Überschwingen/Einschwingen,
speichert `control_lab_step.png`. Default (P=0.4) sauber, aggressiv (P=0.9) ~100 % Überschwingen.
**Offene Ideen:** PI/PID-Vergleich, Z-/Yaw-Achse, Positionshaltung mit Störung, Setpoints bis Instabilität.

### A4 · Integration & Portfolio (offen)
- [ ] `main.py`: Geste + Sprache + Backend-Auswahl in einer App
- [ ] Architektur-Diagramm (README)
- [ ] Demo-Video
- [ ] CV-Text: „Echtzeit-Drohnensteuerung, hardware-unabhängige Testschicht, lokale LLM-Kommandoverarbeitung"

---

## Setup-Notizen / Quirks (für künftige Sessions wichtig)
- **Zwei Umgebungen:** 3.14-`venv` (mock/real/Gesten/Sprache) und conda-Env `tello-sim`
  (Python 3.11, alles mit PyBullet-Sim). Aktivierung siehe `Commands.txt`.
- **PyBullet via conda-forge**, NICHT pip: Apple clang 21 bricht den pip-Build (alter
  K&R-C-Code in gebündeltem zlib). conda-forge liefert ein fertiges Binary.
- **gym-pybullet-drones:** editable installiert unter `~/gym-pybullet-drones-src`,
  mit `pip install --no-deps` (sonst würde es PyBullet überschreiben/neu bauen und SB3+torch ziehen).
  Laufzeit-Deps separat via conda-forge (numpy/scipy/matplotlib/gymnasium/transforms3d/pillow/control).
- **`setuptools<81`** nötig: gym-pybullet-drones nutzt `pkg_resources`, das ≥81 entfernt wurde.
- **mediapipe + faster-whisper** auch in `tello-sim` installiert (numpy bleibt 2.x, kein Konflikt).
- **cv2/av-Konflikt:** OpenCV und PyAV bündeln beide ffmpeg → objc-Doppelklassen-Warnung.
  Deshalb startet `sim/run.py` jeden Modus als **eigenen Prozess** (cv2 und av nie zusammen).
- **Bekanntes macOS-Thema:** `gesture --sim` öffnet Webcam- UND PyBullet-Fenster zugleich –
  zwei GUI-Fenster im selben Prozess; im Live-Test prüfen, ob beide sauber aufgehen.
- **Sim-Backend-Optionen** (`backend_kwargs`): `gui`, `speed` (1=Echtzeit, 1.5=Demo-Default,
  0=max), `camera_follow` (Kamera folgt der Drohne; Maus: ziehen=drehen, Scroll=Zoom).

---

## Technischer Stack
| Komponente     | Bibliothek / Tool          | Zweck                          |
|----------------|----------------------------|--------------------------------|
| Drohne         | djitellopy                 | SDK für Tello                  |
| Logik-Sim      | MockTello (selbst)         | Test ohne Hardware             |
| Physik-Sim     | PyBullet / gym-pybullet-drones | echte Quadrotor-Physik, PID |
| Gesten         | mediapipe                  | Hand-Landmarks                 |
| Sprache → Text | faster-whisper             | lokal, kein Cloud              |
| Text → Befehl  | Ollama (qwen2.5:3b)        | lokales LLM                    |
| Hardware       | DJI Tello (eBay)           | echte Drohne, WLAN TELLO-XXXX  |
| Rechner        | MacBook Air M1             | Entwicklung                    |

---

## Hardware-Referenz
- **Drohne:** Tello (Ryze / DJI, nicht EDU) – SDK 1.3
- **WLAN:** TELLO-XXXXXX, IP 192.168.10.1, Port 8889 (UDP)
- **Akku beim Kauf:** 86 % (Secondhand)
- **Tello-App:** für Firmware-Updates nötig (vor erstem SDK-Einsatz)
- **Ping:** ~4–6 ms wenn verbunden, DUP beim ersten Paket normal

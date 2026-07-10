# Projektstand – Tello-Steuerungssystem

> **Internes Arbeitsprotokoll (Deutsch).** Kein Einstiegsdokument — für einen Überblick
> siehe `../README.md`, für die Tiefen-Doku `PROJECT.md`, für Design-Entscheidungen
> `DECISIONS.md`.
>
> Lebendes Statusdokument. Nach jeder Session aktualisieren (Datum + offene Punkte).
> Aufruf-/Startbefehle stehen in `COMMANDS.md` (gleicher Ordner), nicht hier.

**Stand:** 2026-07-10
**Aktive Phase:** A3 Kern fertig (PyBullet-Sim) · A0 + A1 + A2 + A3-Kern stehen
**Letztes Ergebnis (2026-07-10, Regler-Panel):** Live-Slider im Sim-Fenster.
- Neues Modul `sim/tuning_panel.py`: Slider für Flugparameter (Speed, Beschleunigung,
  Drehrate/-beschl., RC-Speed) und PID-Positions-Gains (`P/I/D_COEFF_FOR`), plus Buttons
  „Zurück zum Menü", „PID-Zustand zurücksetzen", „Defaults". Reine Spec/Mathematik von
  der PyBullet-Schicht getrennt (wie `keyboard_map.py`) → 8 Tests ohne PyBullet.
- `PyBulletBackend`: Flugparameter sind jetzt Instanzwerte statt Modulkonstanten;
  neu `set_flight_limits()`, `set_pid_gains()`, `reset_pid_state()`. Neues Argument
  `show_gui_panel` (default aus) — die Slider brauchen `COV_ENABLE_GUI=1`, und das
  Seitenpanel soll nicht in Würfel-Demo und Demo-Videos hängen.
- **Integrator-Falle:** `DSLPIDControl` hält `integral_pos_e`. Wird `I` live hochgezogen,
  multipliziert der neue Gain einen alten, aufgelaufenen Fehler → Schlag. Daher der
  Reset-Button; `reset_to_defaults()` setzt den Zustand gleich mit zurück.
- **Beim Testen gefunden:** Debug-Parameter existieren nur mit GUI. In `p.DIRECT` wirft
  `readUserDebugParameter` einen `pybullet.error`. Das Panel degradiert jetzt still zu
  „Defaults, nie geklickt" (`available`-Flag), statt die Flugschleife mitzureißen.
- **Drehmoment-Gains bewusst nicht exponiert** (`_TOR`, ~70000): destabilisieren die
  Lageregelung sofort. Ein Test hält das fest.
- `sim/launcher.py`: Menüpunkt 6 „Tastatursteuerung + Regler". Der Menü-Button beendet
  nur die Sim; der Launcher zeigt danach ohnehin wieder sein Menü.
- 151 Tests grün. **Offen:** GUI-Live-Lauf — ob die Slider erscheinen und ob `P xy = 0.9`
  sichtbar aufschwingt, lässt sich headless nicht prüfen.
**Letztes Ergebnis (2026-07-10, Sim-Qualität):** Ruckeln behoben, RC in der Sim, Tastatur.
- **Ursache 1 (blockierend, `demo.py --backend sim`):** `_sim_goto` führte den Sollwert
  geschwindigkeits-, aber nicht *beschleunigungs*begrenzt: ab Schritt 1 volle 0,6 m/s,
  am Ende harter Schnapp aufs Ziel. Zwei Geschwindigkeitssprünge → der PID musste den
  Ruck ausregeln. Zusätzlich Vollstopp (`VEL_TOL`) nach jedem 30-cm-Schritt.
- **Ursache 2 (kooperativ, Gesten/Sprache `--sim`):** `tick()` setzte `target` direkt auf
  die Logik-Pose — ein `move_forward(30)` war ein 30-cm-**Stufeneingang**. Keine Rampe.
- **Ursache 3 (Optik):** Kamera sprang hart auf die Drohnenposition, `sleep()` lief
  240×/s statt pro Bild. Beides verstärkt den Eindruck.
- **Fix:** neues Modul `sim/motion_profile.py` (`VectorRamp`, `YawRamp`) mit trapezför-
  migem Profil (`v_stop = sqrt(2·a·s)`), genutzt von `_sim_goto` **und** `tick()`.
  Kamera exponentiell geglättet, Rendering pro Bild (`RENDER_HZ`), Szenenaufbau ohne
  Rendering. Zwei echte Bugs dabei gefunden: `shortest_angle_diff(π,0)` gab `-π` zurück
  (180°-Wende drehte falsch herum) und das harte Nullen der Restgeschwindigkeit beim
  Landen auf dem Ziel war selbst ein Geschwindigkeitssprung.
- **RC in der Sim funktioniert jetzt:** `PyBulletBackend.tick()` rief nie `super().tick()`,
  der RC-Sollwert wurde also nie integriert. Genau deshalb war `--rc --sim` gesperrt —
  keine Design-Entscheidung, eine fehlende Zeile. Sperre in `gesture/app.py` entfernt.
  `DroneController.tick(dt=None)` reicht `dt` jetzt durch (Determinismus in Tests).
- **Neu: Tastatursteuerung** `sim/keyboard_control.py` (+ reine `sim/keyboard_map.py`),
  Konsolen-Skript `tello-sim-keys`. Gehaltene Taste → RC-Sollwert, derselbe Pfad wie
  der Gesten-`--rc`-Modus. WASD/RF/EZ, T Start, L Landen, Leer Hover, Q Ende.
- **Ursache 4 (der eigentliche Optik-Bug):** PyBullets GUI belegt eigene Debug-Tasten —
  `w`=Wireframe, `s`=Schatten, `a`=AABB, `d`=Deaktivierung, `l`=Constraint-Limits.
  Die WASD-Flugsteuerung löste sie mit aus, deshalb "buggte" das Bild beim Fliegen.
  Fix: `COV_ENABLE_KEYBOARD_SHORTCUTS` aus (+ `COV_ENABLE_MOUSE_PICKING` aus, sonst
  zerrt ein Klick die Drohne durch die Luft).
- **Kamera umkreisen ging nicht**, weil `_follow_camera` jeden Frame
  `resetDebugVisualizerCamera` rief und damit den laufenden Maus-Drag überschrieb.
  Jetzt nur noch bei Zielbewegung > `CAM_MIN_MOVE` (2 cm); im Schwebeflug fasst die
  Sim die Kamera gar nicht an. Taste `c` schaltet die Nachführung zur Laufzeit ab.
- **Szene neu:** dunkler Boden + helles 0,5-m-Raster + Höhenmast statt hellem Beton und
  cremeweißem Drahtwürfel (die Kanten zogen mehr Blick als die Drohne, und die
  hellgraue Crazyflie verschwand vor hellem Grund). Dunkler `rgbBackground`, dazu eine
  mitlaufende Lotlinie Drohne→Boden als Höhen-/Tiefenhinweis.
- Neue Tests: `test_motion_profile.py`, `test_keyboard_map.py` (beide PyBullet-frei).
  Gesamt 125 Tests grün.
- **Gemessen** (`scripts/sim_smoothness_benchmark.py`, 30-cm-Schritt, PID unverändert):

  | Sollwert-Führung | Überschwingen | \|a\|max | \|Ruck\|max |
  |---|---|---|---|
  | Sprung (alt: Tastatur/Gesten/Sprache) | 5,85 % | 2,39 m/s² | 23 m/s³ |
  | Rampe ohne Beschl.-Limit (alt: `demo.py`) | 5,12 % | 1,24 m/s² | 8 m/s³ |
  | Trapezprofil (neu, beide Pfade) | 5,09 % | 0,95 m/s² | 5 m/s³ |

  Ruck 4,6× kleiner im interaktiven Pfad. **Das Überschwingen bleibt bei ~5 %** — das
  hängt an den PID-Gains, nicht an der Sollwert-Führung. Wer es wegbekommen will, muss
  im `control_lab` an den Reglerparametern drehen. Ehrlich: für den blockierenden
  `demo.py`-Pfad allein war der Gewinn klein (8→5 m/s³); der große Effekt liegt im
  kooperativen Modus, wo vorher ein 30-cm-Stufeneingang anlag.
- **Offen:** GUI-Live-Lauf. Szene, Kamera-Logik und Lotlinie laufen nur mit `gui=True`
  und sind daher headless nicht getestet.
**Letztes Ergebnis (2026-07-10):** Repo für Veröffentlichung vorbereitet.
- `.gitignore`: `*.mov`/`*.mp4` raus (334 MB Rohvideos, eine Datei 142 MB > GitHubs
  100-MB-Limit). Blanket-`.aider*` durch explizite Einträge ersetzt, damit ein
  repo-lokales `.aider.conf.yml` mitkommt (sonst liest ein frischer Clone `AIDER.md` nie).
- Untracked-Code committed: `velocity_map.py`, `fastpath.py`, `latency_benchmark.py`,
  5 Testdateien. `COMMANDS.md` dokumentierte `--rc` schon, der Code war nicht in git.
- Stale Fakten korrigiert: 49→97 Tests, `STABLE_FRAMES` 8→5, sechs tote Dateinamen hier
  plus zwei in Source-Docstrings, Graph 355/569/29 → gemessen 537/807/38.
- **Graphify-Benchmark** (`scripts/graphify_benchmark.py`): die alte 10×-Behauptung war
  unbelegt. Gemessen: Median **4,8×** (3,5–22×), aber **0 von 5** Fragen wurden
  vollständig beantwortet — der Graph ist ein Index, kein Orakel. Die billigste Abfrage
  (147×) lag komplett daneben. `query --budget 2000` ist teurer als ein kleines Modul
  zu lesen; `explain` lohnt sich.
- Tooling wird mitveröffentlicht: 4 Skills unter `.claude/skills/` (Q_A ausgeschlossen —
  zeigt auf privaten Wissensspeicher), `generate_gate` sagte 7b statt 3b.
- CI: GitHub Actions, 97 Tests auf py3.11 + 3.12.
- Demo-Videos: 3 echte Flüge (Geste, `--rc`, Sprache) auf 1920p/CRF24 komprimiert
  (142→8,3 MB, VMAF 95,3), als GitHub-Attachments eingebunden; 10-s-Highlight-GIFs in
  `docs/images/`. Repo ist public, CI grün.
**Letztes Ergebnis (2026-07-09):** Zwei getrennte Latenz-Optimierungen für die
Gestensteuerung (nur Mock getestet, echte Drohne noch offen):
- **Kontinuierliche RC-Geschwindigkeitssteuerung** (`--rc`, opt-in): gehaltene Geste →
  nicht-blockierendes `send_rc_control` (kein Ack-Roundtrip), statt diskreter 30-cm-
  Sprünge. Neues Modul `gesture/velocity_map.py` (`gesture_to_velocity` +
  `VelocityBlender` mit Bewegungs-Blending, das nebenbei Einzelbild-Fehlklassifikationen
  filtert → kein Debounce nötig). `MockTello.send_rc_control` + `tick()` integrieren die
  Pose. `--rc --sim` wirft bewusst einen Fehler (Sim-RC = Folgeaufgabe). Diskreter Modus
  bleibt unverändert Default. `send_rc_control` als Passthrough im `DroneController`,
  neue Konstanten `RC_MIN/RC_MAX/RC_CRUISE`.
- **Webcam-Capture gepinnt** (`gesture/detector.py`): `CaptureConfig` (640x480/MJPG/
  30fps/buffersize=1) via `_apply_capture_config`, das die *tatsächlich* akzeptierten
  Werte zurückliest (macOS/AVFoundation ignoriert manche still).
- Neue Tests: `test_capture_config.py`, `test_velocity_map.py`, `test_mock_rc.py`.
  Alle 97 Tests grün.
- **Latenz-Benchmark** (`scripts/latency_benchmark.py`): modelliert die Kommando-Ebene
  (blockierendes `move_*` mit Ack-Roundtrip vs. feuern-und-vergessen `send_rc_control`).
  Bei realistischen 200 ms Ack: diskret ~200 ms/Befehl (~5 Befehle/s), RC spart die
  vollen ~200 ms/Befehl. Echte Zahlen erst am `--real`-Lauf.

**Letztes Ergebnis (2026-07-01):** Latenz-Fixes für Gesten- und Sprachsteuerung (nur
Mock/Sim getestet, kein Umbau auf kontinuierliche Geschwindigkeitssteuerung):
- Gesten: `STABLE_FRAMES` 8→5, `COOLDOWN_FRAMES` 20→10 (`gesture/command_map.py`);
  Frame-Downscale (480p) vor MediaPipe-Inferenz, Anzeige bleibt in voller Auflösung
  (`gesture/detector.py`).
- Sprache: neuer Keyword-Fastpath (`voice/fastpath.py`) überspringt den Ollama-Call
  für einfache Ein-Klausel-Befehle; `silence_ms` 800→500 (`voice/listener.py`);
  ENTER-Modus nutzt jetzt VAD-basiertes Aufnahmeende (`stt.record_until_silence`)
  statt festem 10s-Fenster.
- Neue Tests: `tests/test_voice_fastpath.py`, `tests/test_energy_segmenter.py`.
  Alle 72 Tests grün.

**Letztes Ergebnis (2026-06-17):** GitHub-Umbau zu installierbarem Paket. Code nach
`src/tello_control/{core,gesture,voice,sim,hardware}/`, sys.path-Hacks raus, absolute
Imports, `pyproject.toml` + console-scripts, `requirements.txt`, `environment-sim.yml`,
`.gitignore`, MIT-`LICENSE`, hardware-freie pytest-Suite (46 Tests grün). Modell jetzt
per `scripts/download_model.py` (nicht committed). Englisches `README.md` +
`docs/PROJECT.pdf` (Tiefen-Doku) erstellt. Aufrufe: siehe `COMMANDS.md`.

**Offen über alle Phasen:**
- Latenz-Messung `--real` vs. `--real --rc` in Zahlen festhalten (Flüge erfolgt,
  Messwerte noch nicht dokumentiert).
- Latenz-Benchmark (Geste→Befehl) diskret vs. RC dokumentieren – Portfolio-Zahl.
- GUI-Live-Run der Sim durch den User.
- Optional: ROS-2-Layer (CV-Ziel), A4-Integration.
- Optional (Folgeaufgabe): RC-Modus auch im Sim (Geschwindigkeits-Sollwert über
  PyBullet-PID, `target_vel`) – aktuell wirft `--rc --sim` bewusst einen Fehler.

---

## Aufgaben nach Phase

### A0 · Fundament & Architektur ✅ FERTIG
- [x] venv + djitellopy eingerichtet
- [x] Verbindungs-/Telemetrietest (Akku 86 %, Sensor-Werte)
- [x] Erster Flugtest: takeoff()/land() auf echter Drohne
- [x] Würfel-Demo auf echter Drohne
- [x] DroneController-Abstraktion
- [x] MockTello: Position, Protokoll, Karte, Sicherheitsprüfungen

### A1 · Gestensteuerung (MediaPipe) ✅ FERTIG
- [x] MediaPipe (Tasks-API 0.10+, `gesture/hand_landmarker.task` lokal)
- [x] Winkelbasierter Klassifikator (orientierungsunabhängig, nicht nur Position)
- [x] Gesten-Map (Tabelle unten)
- [x] Debounce (N Frames stabil) + Befehlsauslösung
- [x] Gegen MockTello getestet, live mit Webcam getestet (funktioniert gut)
- [x] Gegen echte Drohne testen (Hardware) — geflogen 2026-07-10

**Gesten-Map (final, `gesture/command_map.py`):**
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

### A2 · Sprachsteuerung (lokales LLM) ✅ FERTIG
- [x] faster-whisper 1.2.1 + sounddevice
- [x] Ollama, Modell `qwen2.5:3b` gepullt + In-App-Autostart (`ensure_ollama()`)
- [x] `voice/commands.py` – Schema + Validierung (8 Negativfälle abgewiesen)
- [x] `voice/llm_parser.py` – Text → JSON, deutsches Few-Shot, Temp 0
      (Bugfix: „einen halben Meter" → 50, war vorher 150)
- [x] `voice/stt.py` – Mikrofon → faster-whisper (deutsch)
- [x] `voice/listener.py` – Dauerhören + Wake-Word „Drohne" (Energie-VAD, pur numpy)
- [x] `voice/app.py` – ENTER- und Dauerhör-Modus, Bestätigung vor echtem Flug
- [x] Live-Mikrofontest (funktioniert gut, Whisper `small` reicht)
- [ ] Live-Test Dauerhören (energy_factor ggf. justieren)
- [x] Gegen echte Drohne testen (Hardware) — geflogen 2026-07-10

### A3 · Simulation (PyBullet / gym-pybullet-drones) ✅ KERN FERTIG
Statt Gazebo: PyBullet (nativ auf M1, kein Docker, echte Quadrotor-Physik, fertige PID-Regler).
- [x] Machbarkeit M1 geklärt → PyBullet nativ (Gazebo verworfen wegen GUI-Schmerz)
- [x] conda-Env `tello-sim` (Python 3.11)
- [x] `sim/pybullet_backend.py` – erbt von MockTello, treibt Physik (3D-Fenster), Pose 1:1 wie Mock
- [x] `core/controller.py` – Backend-Auswahl `mock|sim|real` (+ Abwärtskompat `simulated=`)
- [x] `sim/demo.py` – Würfel-Flug, Report deckt sich mit Mock
- [x] `sim/control_lab.py` – PID-Sprungantwort + Plot
- [x] `sim/launcher.py` – Test-Launcher (Menü, jeder Modus eigener Prozess)
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
  (Python 3.11, alles mit PyBullet-Sim). Aktivierung siehe `COMMANDS.md`.
- **PyBullet via conda-forge**, NICHT pip: Apple clang 21 bricht den pip-Build (alter
  K&R-C-Code in gebündeltem zlib). conda-forge liefert ein fertiges Binary.
- **gym-pybullet-drones:** editable installiert unter `~/Projects/gym-pybullet-drones-src`,
  mit `pip install --no-deps` (sonst würde es PyBullet überschreiben/neu bauen und SB3+torch ziehen).
  Laufzeit-Deps separat via conda-forge (numpy/scipy/matplotlib/gymnasium/transforms3d/pillow/control).
- **`setuptools<81`** nötig: gym-pybullet-drones nutzt `pkg_resources`, das ≥81 entfernt wurde.
- **mediapipe + faster-whisper** auch in `tello-sim` installiert (numpy bleibt 2.x, kein Konflikt).
- **cv2/av-Konflikt:** OpenCV und PyAV bündeln beide ffmpeg → objc-Doppelklassen-Warnung.
  Deshalb startet `sim/launcher.py` jeden Modus als **eigenen Prozess** (cv2 und av nie zusammen).
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

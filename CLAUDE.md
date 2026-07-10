# Tello Drohnen-Steuerungssystem

Persönliches Projekt von Marcelo. Ziel: eine Drohne per **Geste** und **Sprache**
steuern – alles lokal, ohne Cloud, und ohne echte Hardware testbar. Eine
Physik-Simulation sitzt als Mittelstufe zwischen Logik-Mock und echter Drohne.

> **Detaillierter Projektstand & offene Punkte:** `docs/PROJEKTSTAND.md`
> **Wie rufe ich was auf (alle Start-/Testbefehle):** `docs/COMMANDS.md`
> **Öffentliche Doku (Englisch):** `README.md` · Tiefen-Doku `docs/PROJECT.pdf`

---

## Was bisher steht (Überblick)

- **A0 Fundament** ✅ – DroneController-Abstraktion, MockTello, erste echte Flüge
- **A1 Gestensteuerung** ✅ – MediaPipe, winkelbasierter Klassifikator, Debounce
- **A2 Sprachsteuerung** ✅ – faster-whisper → Ollama (qwen2.5:3b) → JSON, Wake-Word
- **A3 Physik-Sim** ✅ Kern – PyBullet/gym-pybullet-drones als 3. Backend, PID-Labor
- **A4 Integration** ⏳ offen – `main.py`, Demo-Video, Portfolio

Offen quer durch A1–A3: echte-Drohne-Tests (Hardware). Details: `PROJEKTSTAND.md`.

---

## Architektur-Prinzip

```
Geste / Sprache
      │
      ▼
DroneController(backend="mock" | "sim" | "real")
      │
      ├─── MockTello          ← Logik testen, kein WLAN
      ├─── PyBulletBackend    ← Physik testen (erbt von MockTello)
      └─── djitellopy.Tello   ← echte Drohne, WLAN TELLO-XXXXXX
```

Der Code oberhalb des Controllers weiß nie, welches Backend läuft.
Umschalten = ein Argument ändern.

---

## Projektstruktur

```
tello-projekt/
├── README.md                  ← öffentliches Schaufenster (Englisch)
├── CLAUDE.md                  ← diese Datei (schlank halten)
├── pyproject.toml             ← Paket-Metadaten + Deps + console-scripts
├── requirements.txt           ← Core-Deps (Spiegel) · environment-sim.yml ← Sim-Env (conda)
│
├── src/tello_control/         ← das installierbare Paket (pip install -e .)
│   ├── core/
│   │   ├── controller.py      ← Abstraktion: backend="mock"|"sim"|"real"
│   │   └── mock_tello.py      ← Software-Drohne (Logik). Basis für mock UND Sim
│   ├── gesture/               ← A1: Gestensteuerung
│   │   ├── detector.py        ← MediaPipe → Geste (winkelbasiert)
│   │   ├── command_map.py     ← Geste → Befehl + Debounce
│   │   ├── runner.py          ← Async-Worker (entkoppelt Flug von Anzeige)
│   │   ├── app.py             ← Haupt-Loop (--sim/--real/--fpv)
│   │   └── models/            ← hand_landmarker.task (git-ignored, Download-Skript)
│   ├── voice/                 ← A2: Sprachsteuerung
│   │   ├── stt.py · llm_parser.py · commands.py · listener.py
│   │   └── app.py             ← Haupt-Loop (--sim/--real/--continuous)
│   ├── sim/                   ← A3: Physik-Sim (PyBullet, conda-Env tello-sim)
│   │   ├── pybullet_backend.py ← Sim-Backend (erbt von MockTello)
│   │   ├── demo.py · control_lab.py · launcher.py
│   └── hardware/              ← Skripte für die echte Drohne (telemetry, flight_test)
│
├── examples/                  ← demo.py (cube/functions), ps4_controller.py
├── scripts/                   ← download_model.py, webcam_check.py
├── tests/                     ← hardware-freie pytest-Suite
└── docs/                      ← PROJECT.pdf/.md, COMMANDS.md, PROJEKTSTAND.md,
                                 djitellopy_api.txt, images/
```

Aufrufe als Modul (`python -m tello_control.gesture.app`) oder via console-scripts
(`tello-gesture`, `tello-voice`, `tello-sim`).

---

## Konventionen

- Alle Distanzen in **cm**, alle Winkel in **Grad**.
- SDK-Grenzen: Distanz 20–500 cm, Winkel 1–360°.
- Niemals direkt `djitellopy.Tello` importieren außerhalb von
  `tello_control/core/controller.py` (Ausnahme: die rohen Hardware-Skripte in
  `tello_control/hardware/`).
- Neue Features immer erst gegen Mock/Sim testen, dann echte Drohne.
- Nach jeder Session: `docs/PROJEKTSTAND.md` aktualisieren (Datum + offene Punkte).

---

## Quick orientation for Claude

- **Einstieg:** `src/tello_control/core/controller.py` + `core/mock_tello.py`
- **Tests validieren schnell:** `pytest tests/ -q` (hardware-frei, ~1 s, 151 Tests)
- **Gesture und Voice sind unabhängig** — eines kann ohne das andere verstanden/geändert werden.
- **Mock ≈ 80 % der Logik** — Sim/Real nur für physik-spezifische Fragen nötig.
- **SDK-Grenzen:** einzelne Quelle in `src/tello_control/core/constants.py`.

## Glossar

- **MockTello** – In-Memory-Drohne (kein WLAN, kein Hardware); Basis für Mock und Sim.
- **DroneController** – Abstraktion, versteckt Backend-Wahl (`mock|sim|real`).
- **PyBulletBackend** – erbt von MockTello, überschreibt Flugmethoden mit Physik.
- **Wake Word** – "Drohne" — Sicherheits-Gate im Dauerhör-Modus der Sprachsteuerung.
- **`_after_move()`** – PyBullet-Hook: treibt Physik zur neuen Logik-Pose nach super()-Aufruf.

## Für Claude: Arbeitshinweise

- Neue Features zuerst gegen Mock/Sim – nie direkt mit echter Drohne debuggen.
- Neue Dateien in das passende Subpaket (`src/tello_control/{core,gesture,voice,sim,hardware}/`).
- Fehler aus MockTello kommen als `TelloException` – in der echten Pipeline abfangen.
- Keine externen APIs, kein Cloud – alles lokal (kein Internet während Drohnenflug).
- Stand-Updates gehören in `docs/PROJEKTSTAND.md`, Aufruf-Befehle in `docs/COMMANDS.md` –
  CLAUDE.md schlank halten (Identität, Überblick, Architektur, Struktur, Konventionen).
- PDF neu bauen nach Doku-Änderungen: `bash docs/build_pdf.sh`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
  Nur `update` ist AST-only — der erste Build (`graphify extract`) fährt einen semantischen
  LLM-Pass und kostet Tokens.

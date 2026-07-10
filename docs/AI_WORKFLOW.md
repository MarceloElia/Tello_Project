---
title: "AI-Workflow mit Claude Code"
subtitle: "Von der IDE bis zum lokalen Modell"
author: "Marcelo Leindl"
date: "2026"
---

> **Deutschsprachige Tiefen-Doku zum Tooling.** Die Kurzfassung auf Englisch steht in
> `../README.md` unter *How this was built*. Zahlen zum Graphen stammen aus
> `../scripts/graphify_benchmark.py` und sind reproduzierbar.

## Überblick

Statt KI-Tools ad hoc zu nutzen, ist hier ein geschlossener Workflow entstanden,
der Claude Code, Projektskills, eine Wissensgraph-Schicht und ein lokales Coding-Agent
als stufenweises System verbindet.

```
Claude Code (VS Code)
      │
      ├── Project Skills    ← /scaffold-here, /graphify, /generate_gate, /aider-compact …
      │
      ├── Graphify          ← Codebase → Knowledge Graph (einmalig gebaut)
      │                        Queries statt roher Datei-Lesevorgänge
      │
      └── Generate-Gate     ← /generate_gate → AIDER.md Task Gate
                                     │
                                     └── Aider + qwen2.5-coder:3b   ← lokal, token-frei
                                           Datei-Zugriff · Diffs · Git
```

---

## 1. Claude Code in VS Code

Claude Code läuft als CLI und als VS Code Extension. Im Editor hat es direkten
Zugriff auf die gesamte Codebasis, Git-History und das Terminal. Claude liest,
bearbeitet und erstellt Dateien, führt Tests aus und legt Commits an – alles
innerhalb eines Gesprächs.

**Typischer Einsatz:**

- Neue Features gegen Mock/Sim entwerfen und sofort testen
- Refactoring mit direktem Test-Feedback (`pytest -q`)
- Architektur-Entscheidungen diskutieren und direkt umsetzen
- Debugging über mehrere Dateien hinweg, ohne den Kontext zu verlieren

Der entscheidende Vorteil: Claude sieht das gesamte Projekt und kann
Code-Änderungen, Tests und Dokumentation in einem einzigen Gesprächsfluss
koordinieren.

---

## 2. Project Skills

Skills sind projektspezifische Slash-Commands, die in
`~/.claude/skills/<name>/SKILL.md` oder `.claude/skills/` liegen. Eine
`SKILL.md` ist eine Instruktionsdatei, die Claude als Aufgabe bekommt,
wenn der Nutzer `/skillname` tippt.

**Beispiele:**

| Skill | Was er tut |
|-------|-----------|
| `/scaffold-here` | Legt professionelle Python-Paketstruktur im aktuellen Ordner an |
| `/graphify` | Baut den Wissensgraph aus dem gesamten Repo |
| `/generate_gate` | Analysiert das Projekt und schreibt `AIDER.md` |
| `/aider-compact` | Komprimiert die letzten N Aider-Sessions in `.aider.memory.md` |
| `/code-review` | Reviewt den aktuellen Diff auf Bugs und Vereinfachungen |
| `/run` | Startet die App und beobachtet das Verhalten im echten Betrieb |

Skills machen Routineaufgaben reproduzierbar: einmal als Skill formuliert,
läuft dieselbe Logik in jedem neuen Projekt ohne erneute Erklärung.

---

## 3. Graphify

`graphify` wandelt die gesamte Codebasis – Code, Docs, Diagramme – in einen
persistenten Wissensgraph um. Knoten sind Klassen, Funktionen, Konzepte und
Dokumente; Kanten sind Beziehungen (erbt von, ruft auf, referenziert).

**Was der Graph spart – und was nicht:**

Statt Quelldateien roh zu lesen, genügt oft eine gezielte Abfrage:

```bash
graphify explain "DroneController"             # 320 Token  (Datei lesen: 1112)
graphify explain "PyBulletBackend"             # 307 Token  (Dateien lesen: 6779)
graphify explain "validate_list"               # 212 Token  (Datei lesen: 1008)
```

Der Graph wird einmalig gebaut und nach Code-Änderungen per `graphify update .`
aktualisiert. Nur `update` ist reine AST-Analyse; der **erste Build fährt einen
semantischen LLM-Pass und kostet Tokens**.

In diesem Projekt: **776 Knoten · 1114 Kanten · 63 Communities**.

**Gemessen** (`scripts/graphify_benchmark.py`, fünf vorab festgelegte Fragen):
der Median-Kontextgewinn liegt bei **≈ 4,8×** (Spanne 3,5–22×) – nicht bei den
früher behaupteten 10×. Wichtiger als die Zahl ist die Einschränkung: **keine**
der fünf Fragen wurde vom Graph vollständig beantwortet. Er enthält keinen Code,
sondern Struktur. Er sagt, *wo* etwas steht und *was* damit verbunden ist, nie
*wie* es funktioniert – die Datei muss danach trotzdem geöffnet werden.

Die billigste Abfrage im Benchmark (scheinbar 147× Ersparnis) war die einzige,
die komplett danebenlag: `query "main modules…"` matchte auf `main()`-Funktionen
in `demo.py` und `ps4_controller.py`. Genau deshalb ist Token-Zahl allein ein
schlechtes Maß. `graphify query` ist bei seinem Default-`--budget 2000` **nicht**
billiger, als ein kleines Modul einfach zu lesen; `explain` dagegen schon.

Skills wie `/generate_gate` nutzen den Graph zur Orientierung, bevor sie Dateien öffnen.

---

## 4. Generate-Gate (`/generate_gate`)

`/generate_gate` analysiert das Projekt und schreibt `AIDER.md` – eine
Task-Gate-Datei, die exakt definiert, welche Aufgaben der lokale Coding-Agent
sicher erledigen kann und welche für Claude reserviert bleiben.

**Aufbau von `AIDER.md`:**

- **✅ Aider handles** – Kategorien mit Confidence-Level, auslösenden Keywords
  und konkreten Beispielen aus dem eigenen Repo
- **🔴 Hold for Claude** – Aufgaben, die mehrere Dateien oder async-Logik
  betreffen, mit Begründung
- **Aider setup** – fertiger `aider`-Befehl, kein weiterer Setup nötig
- **Held Tasks Log** – Tabelle für Aufgaben, die Aider abgelehnt hat, bereit
  für die nächste Claude-Session

Das Gate wird einmalig generiert und bei größeren Refactorings mit
`/generate_gate` neu erzeugt. Aider lädt `AIDER.md` automatisch beim Start –
dafür liegt `.aider.conf.yml` im Repo (`read: [AIDER.md, .aider.memory.md]`),
nicht nur im Home-Verzeichnis. Sonst würde ein frischer Clone das Gate ignorieren.

---

## 5. Aider + qwen2.5-coder:3b (lokal, token-frei)

Wenn Claude-API-Tokens aufgebraucht sind, übernimmt **Aider** mit
**qwen2.5-coder:3b** – ein ~4,7 GB Coding-Modell, das vollständig lokal läuft.
Im Gegensatz zu einem reinen Chat-Modell hat Aider echten Dateizugriff: es
liest Quelldateien, schlägt Diffs vor und fragt vor jeder Änderung nach.

```bash
conda activate aider
cd ~/Projects/tello-projekt
aider src/tello_control/core/mock_tello.py
# → Aider liest die Datei, AIDER.md und .aider.memory.md automatisch
# → Aufgabe in Klartext eingeben → Diff anzeigen → y/n zum Anwenden
```

**Was Aider zuverlässig erledigt** (durch `AIDER.md` klar definiert):

- Docstrings und Type Hints für einzelne Funktionen schreiben
- Konstanten, Label-Texte und Anzeigestrings anpassen
- Kurze Funktionsrümpfe aus einem klaren Stub implementieren
- Einzelne Dict-Einträge nach bestehendem Muster hinzufügen
- Einfache isolierte Bugfixes in einer Datei
- Variablen innerhalb einer Datei umbenennen
- Projektdokumentation (`PROJEKTSTAND.md`, `COMMANDS.md`) erweitern

**Session-Gedächtnis mit `/aider-compact`:**

Aider selbst hat kein Langzeitgedächtnis. Der Skill `/aider-compact` löst das:
er liest `.aider.chat.history.md` (automatisch von Aider geschrieben),
komprimiert die letzten N Sessions in `.aider.memory.md` und trägt die Datei
in `.aider.conf.yml` ein – ab dann lädt Aider sie bei jedem Start automatisch.

---

## Kernprinzip

> Jede Schicht ist für das optimiert, was sie am besten kann.

| Schicht | Stärke |
|---------|--------|
| **Claude Code** | Architektur, Multi-File-Logik, neue Features |
| **Graphify** | Orientierung ohne Datei-Overhead, gemessen ≈ 4,8× günstiger (Index, kein Orakel) |
| **Skills** | Reproduzierbare Routineaufgaben, projektweit konsistent |
| **Aider + qwen2.5-coder:3b** | Token-freie Aufgaben mit echtem Dateizugriff, klar durch `AIDER.md` begrenzt |

Der Workflow skaliert: In jedem neuen Projekt wird der Graph gebaut,
`/generate_gate` schreibt das Gate, `/aider-compact` hält das Gedächtnis aktuell –
und Aider übernimmt sofort die definierten Aufgaben ohne erneute Konfiguration.

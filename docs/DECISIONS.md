# Architecture Decision Records

Short records of the non-obvious design choices made during this project.
Each entry answers: what was chosen, why, and what was ruled out.

---

## ADR-1 · Simulation: PyBullet instead of Gazebo

**Chosen:** PyBullet + gym-pybullet-drones  
**Why:** Gazebo on Apple Silicon M1 requires Docker for the full GUI stack, which adds
latency and setup friction. PyBullet runs natively on ARM, ships ready-made quadrotor
models (`CtrlAviary`) and PID controllers (`DSLPIDControl`), and needs no ROS installation.  
**Ruled out:** Gazebo (Docker overhead, no native M1 binary at the time), AirSim
(Windows-first, GPU-heavy).

---

## ADR-2 · Gesture classifier: angle-based rules instead of ML model

**Chosen:** Angle-based rule classifier on MediaPipe hand landmarks  
**Why:** The finger extension check (`MCP→PIP→TIP` joint angle > threshold) is
orientation-independent and robust to hand size — properties a position-based
classifier doesn't have without a labelled training set. Produces deterministic
output, easy to tune and inspect.  
**Ruled out:** Training a custom gesture-recognition model (no labelled dataset,
unnecessary for 8 discrete gestures), MediaPipe's built-in `GestureRecognizer`
(limited pre-defined gesture set, hard to extend).

---

## ADR-3 · Voice parsing: local LLM (Ollama) instead of rule-based NLP

**Chosen:** Ollama `qwen2.5:3b` in JSON mode, temperature 0  
**Why:** German natural-language commands have too many surface forms for a simple
regex/keyword matcher (e.g. "einen halben Meter" = 50 cm). A small local LLM handles
these fluently and stays offline. JSON mode + temperature 0 makes output deterministic.  
**Ruled out:** OpenAI/cloud APIs (violates the offline constraint, data privacy during
flight), spaCy rule-based NER (brittle on number-word variants), Whisper built-in
intent parsing (Whisper is STT only).

---

## ADR-4 · Threading model for gesture control

**Chosen:** Single worker thread owns the drone; main thread owns webcam + PyBullet GUI  
**Why:** Flight commands block (djitellopy waits for the drone's ACK; the sim runs a
physics loop). If called on the main thread they freeze the webcam preview. OpenCV and
the PyBullet GUI both require the main thread. One worker thread eliminates all race
conditions: the queue ensures commands don't stack up, and the busy flag drops new
gestures while a command is in flight.  
**Ruled out:** asyncio (djitellopy is synchronous; wrapping in a thread pool adds
complexity without benefit), multiple worker threads (command ordering becomes
undefined).

---

## ADR-5 · Voice safety gate: all-or-nothing validation

**Chosen:** Validate the full command list before executing any command  
**Why:** The LLM is treated as an untrusted source. A partial execution (first 2 of 5
commands succeed, third fails validation) leaves the drone in an unknown position.
All-or-nothing means the user either gets the full intended manoeuvre or nothing moves.  
**Ruled out:** Execute-and-stop-on-error (leaves drone mid-manoeuvre), per-command
in-flight validation (same problem — partial execution is dangerous).

---

## ADR-6 · Gesture latency: continuous RC setpoints alongside discrete moves

**Chosen:** Keep discrete `move_*` as the default, add continuous `send_rc_control`
behind an opt-in `--rc` flag
**Why:** Every discrete `move_forward(30)` blocks until the Tello acknowledges it. At a
realistic 200 ms round-trip that caps the system at roughly 5 commands/second and makes
the drone feel like it is stepping rather than flying. `send_rc_control` is
fire-and-forget: a held gesture becomes a velocity setpoint and motion starts on
recognition. Ramping the setpoint (`VelocityBlender`, max step per axis per frame) buys
smoothing and single-frame misclassification filtering in one mechanism, so the RC path
needs no debounce at all. Discrete stays the default because it is what has actually
been flown on hardware, and because its behaviour is exactly reproducible in the mock.
**Ruled out:** Replacing discrete moves outright (they are the only mode flown on the
real drone, and they map cleanly onto the mock's analytic pose model); shortening the
debounce further (it was already cut from 8 frames to 5, and what is left is ACK latency
rather than debounce); RC in the simulation (`--rc --sim` raises on purpose, because
feeding a velocity setpoint through `DSLPIDControl` is its own task).

> The command-level model is in `scripts/latency_benchmark.py`. Real numbers await a
> `--real --rc` flight; the figures there are a model, not a measurement.

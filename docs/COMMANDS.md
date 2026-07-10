# Commands — how to run everything

## Environments

```bash
# Main environment (mock / real drone / gestures / voice)
cd ~/Projects/tello-projekt
source venv/bin/activate
pip install -e .                 # once, registers the tello_control package

# Simulation environment (PyBullet) — separate conda env, see environment-sim.yml
conda env create -f environment-sim.yml      # once
conda activate tello-sim
pip install --no-deps -e .                    # register the package in this env too
```

One-time setup: download the MediaPipe model used by gesture control:

```bash
python scripts/download_model.py
```

## Demos (`examples/`)

```bash
python examples/demo.py cube                  # cube flight (mock)
python examples/demo.py cube --backend sim    # cube flight in the 3D window
python examples/demo.py cube --backend real   # cube flight on the real drone
python examples/demo.py functions             # walk through every command

python examples/ps4_controller.py --test      # check the PS4 controller mapping
python examples/ps4_controller.py             # fly the real drone with the controller
```

## Gesture control (`tello-gesture` / module)

```bash
tello-gesture                                 # mock
python -m tello_control.gesture.app           # same, explicit module form
python -m tello_control.gesture.app --sim     # against the physics sim (conda)
python -m tello_control.gesture.app --real    # real drone
python -m tello_control.gesture.app --real --fpv   # + drone camera window
python -m tello_control.gesture.app --rc      # continuous RC velocity mode (mock/real)
python -m tello_control.gesture.app --real --rc    # lowest-latency real-drone control
```

`--rc` = continuous velocity control: a held gesture keeps the drone moving
(non-blocking `send_rc_control`, no per-command ack wait) instead of discrete
30 cm hops. Not supported with `--sim` yet. Default (no `--rc`) stays the proven
discrete mode.

## Voice control (`tello-voice` / module)

```bash
tello-voice                                   # mock, press ENTER to speak
python -m tello_control.voice.app --sim       # against the physics sim (conda)
python -m tello_control.voice.app --real      # real drone
python -m tello_control.voice.app --continuous # always-listening, wake word "Drohne"
```

Requires a local Ollama server with the model pulled once:
`ollama pull qwen2.5:3b` (the app starts the server automatically if needed).

## Simulation (conda env `tello-sim`)

```bash
python -m tello_control.sim.launcher          # menu launcher (all sim modes)
python -m tello_control.sim.demo              # cube flight in the 3D window
python -m tello_control.sim.control_lab       # PID step response → results/control_lab_step.png
```

## Real-drone helper scripts

```bash
python -m tello_control.hardware.telemetry    # battery / temperature / barometer
python -m tello_control.hardware.flight_test  # takeoff, hover, land
```

## Latency benchmark (discrete vs RC)

```bash
python scripts/latency_benchmark.py                       # default: 50 cmds, ack 0-300ms
python scripts/latency_benchmark.py --commands 100 --ack-delays 0 100 200 300
```

Models the drone's command-layer latency: blocking `move_*` (waits on a UDP ack)
vs. fire-and-forget `send_rc_control`. At a realistic 200 ms ack the discrete path
is ~200 ms/command (≈5 commands/s); RC saves that full ~200 ms per command. Real
numbers come from a `--real` run on the drone.

## Tests

```bash
pytest                                        # hardware-free suite (97 tests)
```

## Graphify benchmark

```bash
pip install tiktoken
python scripts/graphify_benchmark.py
```

Compares `graphify` output against reading the files that answer the same question,
over five pre-registered questions. Prints a token ratio *and* a hand-graded sufficiency
column, because the graph indexes structure and never contains code — a cheap answer is
not automatically a good one.

## Demo assets

Raw `.mov` / `.mp4` are git-ignored: they exceed GitHub's limits (100 MB hard cap per
file). Two artefacts per video, both cut from the same source.

**1 — 5 s highlight GIF** (committed to `docs/images/`, autoplays and loops in the
README, no click). Replace `-ss` with the start of the moment you want:

```bash
ffmpeg -ss 00:00:12 -t 5 -i Drohne_Gesten_test.mov \
  -vf "fps=12,scale=480:-1:flags=lanczos,palettegen" -y /tmp/pal.png
ffmpeg -ss 00:00:12 -t 5 -i Drohne_Gesten_test.mov -i /tmp/pal.png \
  -lavfi "fps=12,scale=480:-1:flags=lanczos[x];[x][1:v]paletteuse" \
  -y docs/images/gesture_highlight.gif
```

**2 — full clip** (~3–8 MB for a 40–50 s source, plays inline *with audio*):

```bash
ffmpeg -i Drohne_Gesten_test.mov -vf "scale=1280:-2" \
  -c:v libx264 -crf 28 -preset slow -c:a aac -b:a 96k \
  -movflags +faststart full_gesture.mp4
```

Then drag `full_gesture.mp4` into any GitHub issue comment **without submitting the
issue**, copy the resulting `https://github.com/user-attachments/assets/…` URL, and put
it in the README under the GIF. GitHub only renders an inline player for files it hosts
itself — a committed video will never play.

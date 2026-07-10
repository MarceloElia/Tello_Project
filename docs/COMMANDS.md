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

> **`deactivate` the venv first.** Activating the venv after the conda env puts
> `venv/bin` ahead on `PATH`, so `python` resolves to the venv interpreter — which
> deliberately has no PyBullet. The symptom is `ModuleNotFoundError: No module named
> 'pybullet'` even though the conda env is fine. A prompt showing `(tello-sim) (venv)`
> means you are in the wrong interpreter.

```bash
conda activate tello-sim
python -m tello_control.sim.launcher          # menu launcher (all sim modes)
python -m tello_control.sim.demo              # cube flight in the 3D window
python -m tello_control.sim.keyboard_control  # fly it with the keyboard
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

## Keyboard control in the simulation

Runs in the conda env `tello-sim`. **If the venv is active, run `deactivate` first** —
otherwise its `python` shadows the conda one and PyBullet appears to be missing.

```bash
conda activate tello-sim
python -m tello_control.sim.keyboard_control     # or: tello-sim-keys
```

The PyBullet window must have focus. Hold a key to fly, release to hover.

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| `t` | take off | `w` / `s` | forward / back |
| `l` | land | `a` / `d` | left / right |
| `space` | hover (stop) | `r` / `f` | up / down |
| `q` | quit | `e` / `z` | rotate cw / ccw |
| `c` | camera follow on/off | **`shift`** (hold) | camera mode |

**Hold `shift`** to orbit: camera following pauses, the drone hovers, and the mouse is
yours — drag to rotate around the drone, scroll/trackpad to zoom. Release and the camera
resumes following, keeping your angle and zoom.

Held keys become a continuous `send_rc_control` setpoint — the same path the gesture
`--rc` mode uses. `tello-gesture --sim --rc` now works too.

Note the sim disables PyBullet's built-in debug shortcuts (`COV_ENABLE_KEYBOARD_SHORTCUTS`):
its GUI binds `w` to wireframe, `s` to shadows, `a` to AABB boxes and `l` to constraint
limits, which would otherwise fire on every WASD keystroke.

### Live tuning panel

This mode opens PyBullet's side panel with live sliders — change them mid-flight and watch
the behaviour change. Three buttons sit below: **back to menu**, **reset PID state**, and
**restore defaults**.

| Slider | Range | Default | What it does |
|---|---|---|---|
| Speed | 0.1–2.0 m/s | 0.6 | how fast the setpoint travels |
| Beschl. | 0.2–5.0 m/s² | 1.2 | setpoint acceleration; low = gentle, high = snappy |
| Drehrate | 10–360 °/s | 90 | yaw speed |
| Drehbeschl. | 30–720 °/s² | 240 | yaw acceleration |
| RC-Speed | 10–100 | 40 | how fast a held key flies |
| PID P xy / P z | 0.05–1.2 / 0.2–2.5 | 0.4 / 1.25 | position gain — **this is what causes overshoot** |
| PID I xy | 0.0–0.3 | 0.05 | integral gain |
| PID D xy / D z | 0.0–0.8 / 0.0–1.5 | 0.2 / 0.5 | damping |

Try `P xy = 0.9`: the drone overshoots its target by roughly 100 %, the same effect
`control_lab.py` plots offline. After a large gain change, hit **reset PID state** —
`DSLPIDControl` keeps an integral term, and a stale one gets multiplied by the new gain.

The torque gains (`P/I/D_COEFF_TOR`, values around 70000) are deliberately not exposed;
small changes there destabilise attitude control immediately.

The panel needs `COV_ENABLE_GUI=1`, so only this mode shows PyBullet's side panels — the
cube demo and the gesture sim keep the clean view used for the demo videos.

## Tests

```bash
pytest                                        # hardware-free suite (97 tests)
```

## Simulation smoothness benchmark

```bash
conda activate tello-sim
python scripts/sim_smoothness_benchmark.py
```

Flies the same 30 cm step through the same PID with the old and the new setpoint
guidance, and reports overshoot, peak acceleration and jerk measured on the drone's
actual position. Jerk (the derivative of acceleration) is what the eye reads as
"jerky".

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

**1 — highlight GIF** (committed to `docs/images/`, autoplays and loops in the README,
no click needed). `-ss` is the start, `-t` the length:

```bash
ffmpeg -ss 11 -t 10 -i demo-clips/gesture_control.mp4 \
  -vf "fps=10,scale=440:-1:flags=lanczos,palettegen=stats_mode=diff" -y /tmp/pal.png
ffmpeg -ss 11 -t 10 -i demo-clips/gesture_control.mp4 -i /tmp/pal.png \
  -lavfi "fps=10,scale=440:-1:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=3" \
  -loop 0 -y docs/images/gesture_highlight.gif
```

10 fps at 440 px lands around 2 MB for 10 s. 12 fps at 480 px costs ~30 % more for no
visible gain — these autoplay on every page load, so keep them lean.

**2 — full clip** (plays inline *with audio*). Settings chosen by measurement, not by
feel: encoded at several qualities and scored with `libvmaf` against the source.

```bash
ffmpeg -i Tello_drone_rc_gesture.mov -vf "scale=1920:-2:flags=lanczos" \
  -c:v libx264 -crf 24 -preset slow -pix_fmt yuv420p \
  -c:a aac -b:a 128k -movflags +faststart Tello_drone_rc_gesture.mp4
```

142 MB → 8.3 MB at **VMAF 95.3**, i.e. visually indistinguishable from the source. Note
the source is already lossy H.264, so nothing here is *mathematically* lossless — a true
lossless re-encode (`-crf 0`) would be **larger** than the original. Two findings from
the sweep worth keeping:

| | est. size (47 s) | VMAF |
|---|---|---|
| 1920p CRF 23 | 10.1 MB | 95.5 |
| **1920p CRF 24** | **8.4 MB** | **95.1** |
| 1600p CRF 23 | 6.9 MB | 93.6 |
| 720p CRF 28 | 2.5 MB | 86.9 |

Keeping full width and raising CRF beats downscaling at an equal byte budget (1920p/CRF 25
scores 94.2 at 7.1 MB; 1600p/CRF 23 scores 93.6 at 6.9 MB). Don't trade away resolution
to save bits. Reproduce a score with:

```bash
ffmpeg -i out.mp4 -i src.mov -lavfi "[0:v]scale=1920:1080[d];[1:v]scale=1920:1080[r];[d][r]libvmaf" -f null -
```

Then drag the `.mp4` into a GitHub issue comment and **submit the issue** — an attachment
that is only uploaded but never posted stays private, and its
`https://github.com/user-attachments/assets/…` URL returns 404 for logged-out visitors.
Once the issue exists the URL is public and stable; the issue can then be closed. Verify
before embedding:

```bash
curl -sL -o /dev/null -w '%{http_code} %{content_type}\n' <asset-url>   # want: 200 video/mp4
```

Paste the bare URL on its own line in the README. GitHub only renders an inline player
for files it hosts itself — a committed video will never play.

# Commands — how to run everything

## Environments

```bash
# Main environment (mock / real drone / gestures / voice)
cd ~/tello-projekt
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
```

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

## Tests

```bash
pytest                                        # hardware-free suite
```

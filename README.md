# LEGO NXT Robot – Python Controller

Control your LEGO Mindstorms NXT brick with Python using the `nxt-python` library.

## Requirements

- Python 3.9+
- LEGO Mindstorms NXT brick connected via **USB** or **Bluetooth**
- `nxt-python` library

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Connect your NXT brick** via USB cable or pair it over Bluetooth.

3. **Run the program:**
   ```bash
   python main.py
   ```

## Features

| Function | Description |
|---|---|
| `move_forward` | Drive both motors forward |
| `move_backward` | Drive both motors backward |
| `turn_left` | Pivot left |
| `turn_right` | Pivot right |
| `read_touch_sensor` | Read a touch sensor value |
| `read_ultrasonic_sensor` | Read distance (cm) |
| `obstacle_avoidance_demo` | Drive forward and avoid obstacles |

## Hardware Assumptions

| Port | Device |
|---|---|
| Motor A | Left wheel |
| Motor B | Right wheel |
| Sensor port 1 | Touch sensor |
| Sensor port 4 | Ultrasonic sensor |

Adjust the port constants in `main.py` to match your actual build.

## Troubleshooting

- If the brick is not found, make sure it is powered on and connected.
- On macOS you may need to install a USB driver or enable Bluetooth pairing first.
- Run `python -c "import nxt; print(nxt.__version__)"` to confirm the library is installed.

# Apple TV Remote + LEGO NXT Robot – Python Controller

## 🍎 Apple TV Remote (Raspberry Pi 4 — always-on)

Control your Apple TV from your iPhone **even when your Mac is off**, using a Raspberry Pi 4 as a 24/7 server.

### Quick Setup (on the Pi)

```bash
# 1. Clone the repo on your Pi
git clone https://github.com/YOUR_USERNAME/nxtlego2.git
cd nxtlego2

# 2. Run the one-shot setup script
bash pi_setup.sh
```

The script will:
- Install Python, pyatv, Flask
- Set up a **systemd service** (auto-starts on boot, auto-restarts on crash)
- Optionally install a **Cloudflare Tunnel** for remote access from *anywhere*

### Usage

| Mode | URL |
|------|-----|
| Home WiFi | `http://<pi-ip>:9876` |
| Anywhere (Cloudflare) | `https://xxxx.trycloudflare.com` |

Get the Cloudflare URL after setup:
```bash
sudo journalctl -u cloudflared-appletv -n 30 | grep trycloudflare
```

### Useful Pi commands

```bash
sudo systemctl status appletv-remote    # check status
sudo journalctl -u appletv-remote -f    # live logs
sudo systemctl restart appletv-remote  # restart
```

---

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

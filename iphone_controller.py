"""
iPhone Robot Controller
Opens a webpage you can visit on your iPhone to control the robot simulator.
Make sure your iPhone and Mac are on the same WiFi network!
"""

import math
import os
import socket
import threading
import time

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# --- Robot state ---
robot = {
    "x": 10.0,
    "y": 10.0,
    "angle": 0.0,   # degrees, 0 = facing up
    "action": "Waiting for input...",
    "speed": 80,
}
driving = {"active": False, "command": None}


def move_step(command):
    """Move the robot one small step based on the command."""
    speed = robot["speed"] / 800
    if command == "forward":
        rad = math.radians(robot["angle"] - 90)
        robot["x"] = max(0, min(21, robot["x"] + math.cos(rad) * speed))
        robot["y"] = max(0, min(21, robot["y"] + math.sin(rad) * speed))
        robot["action"] = "⬆️ Forward"
    elif command == "backward":
        rad = math.radians(robot["angle"] - 90)
        robot["x"] = max(0, min(21, robot["x"] - math.cos(rad) * speed))
        robot["y"] = max(0, min(21, robot["y"] - math.sin(rad) * speed))
        robot["action"] = "⬇️ Backward"
    elif command == "left":
        robot["angle"] = (robot["angle"] - 4) % 360
        robot["action"] = "⬅️ Spinning left"
    elif command == "right":
        robot["angle"] = (robot["angle"] + 4) % 360
        robot["action"] = "➡️ Spinning right"


def drive_loop():
    """Background loop that keeps moving the robot while a button is held."""
    while True:
        if driving["active"] and driving["command"]:
            move_step(driving["command"])
        time.sleep(0.05)


threading.Thread(target=drive_loop, daemon=True).start()


# --- Web page served to the iPhone ---
PAGE = """
<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, user-scalable=no">
  <title>🤖 Robot Controller</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #111;
      color: white;
      font-family: -apple-system, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 100vh;
      padding: 20px;
      gap: 16px;
    }
    h1 { font-size: 1.4em; margin-top: 10px; }
    #status {
      background: #222;
      border-radius: 12px;
      padding: 10px 20px;
      font-size: 0.95em;
      color: #aaa;
      width: 100%;
      max-width: 340px;
      text-align: center;
    }
    canvas {
      background: #1a1a2e;
      border-radius: 12px;
      border: 2px solid #444;
    }
    .controls {
      display: grid;
      grid-template-columns: repeat(3, 90px);
      grid-template-rows: repeat(3, 90px);
      gap: 10px;
    }
    .btn {
      background: #222;
      border: 2px solid #444;
      border-radius: 16px;
      color: white;
      font-size: 2em;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      user-select: none;
      -webkit-user-select: none;
      transition: background 0.1s;
      touch-action: none;
    }
    .btn:active, .btn.pressed { background: #0af; border-color: #0af; }
    .btn.empty { border: none; background: transparent; pointer-events: none; }
    #speed-container {
      width: 100%;
      max-width: 340px;
      background: #222;
      border-radius: 12px;
      padding: 14px 20px;
    }
    #speed-container label { font-size: 0.9em; color: #aaa; }
    input[type=range] { width: 100%; margin-top: 8px; accent-color: #0af; }
  </style>
</head>
<body>
  <h1>🤖 Robot Controller</h1>
  <div id="status">Waiting for input...</div>

  <canvas id="grid" width="280" height="280"></canvas>

  <div class="controls">
    <div class="btn empty"></div>
    <div class="btn" id="btn-forward" data-cmd="forward">⬆️</div>
    <div class="btn empty"></div>
    <div class="btn" id="btn-left"    data-cmd="left">⬅️</div>
    <div class="btn empty"></div>
    <div class="btn" id="btn-right"   data-cmd="right">➡️</div>
    <div class="btn empty"></div>
    <div class="btn" id="btn-backward" data-cmd="backward">⬇️</div>
    <div class="btn empty"></div>
  </div>

  <div id="speed-container">
    <label>Speed: <span id="speed-val">80</span></label>
    <input type="range" id="speed" min="20" max="127" value="80">
  </div>

<script>
  // Button hold logic
  const buttons = document.querySelectorAll('.btn[data-cmd]');
  buttons.forEach(btn => {
    const cmd = btn.dataset.cmd;
    const start = () => { sendCmd(cmd, true); btn.classList.add('pressed'); };
    const stop  = () => { sendCmd(null, false); btn.classList.remove('pressed'); };
    btn.addEventListener('touchstart',  e => { e.preventDefault(); start(); }, {passive:false});
    btn.addEventListener('touchend',    e => { e.preventDefault(); stop();  }, {passive:false});
    btn.addEventListener('mousedown',   start);
    btn.addEventListener('mouseup',     stop);
    btn.addEventListener('mouseleave',  stop);
  });

  function sendCmd(cmd, active) {
    fetch('/command', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({command: cmd, active: active})
    });
  }

  // Speed slider
  const speedSlider = document.getElementById('speed');
  const speedVal    = document.getElementById('speed-val');
  speedSlider.addEventListener('input', () => {
    speedVal.textContent = speedSlider.value;
    fetch('/speed', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({speed: parseInt(speedSlider.value)})
    });
  });

  // Poll server for robot state and redraw
  const canvas = document.getElementById('grid');
  const ctx    = canvas.getContext('2d');
  const status = document.getElementById('status');
  const CELL   = canvas.width / 22;

  function drawRobot(state) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Grid lines
    ctx.strokeStyle = '#2a2a4a';
    ctx.lineWidth = 0.5;
    for (let i = 0; i <= 22; i++) {
      ctx.beginPath(); ctx.moveTo(i*CELL, 0); ctx.lineTo(i*CELL, canvas.height); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, i*CELL); ctx.lineTo(canvas.width, i*CELL); ctx.stroke();
    }

    // Robot
    const rx = (state.x + 0.5) * CELL;
    const ry = (state.y + 0.5) * CELL;
    const rad = (state.angle - 90) * Math.PI / 180;

    ctx.save();
    ctx.translate(rx, ry);
    ctx.rotate(rad);

    // Body
    ctx.fillStyle = '#0af';
    ctx.beginPath();
    ctx.roundRect(-CELL*0.35, -CELL*0.35, CELL*0.7, CELL*0.7, 4);
    ctx.fill();

    // Direction arrow
    ctx.fillStyle = 'white';
    ctx.beginPath();
    ctx.moveTo(0, -CELL*0.38);
    ctx.lineTo(-CELL*0.18, -CELL*0.08);
    ctx.lineTo(CELL*0.18, -CELL*0.08);
    ctx.closePath();
    ctx.fill();

    ctx.restore();

    status.textContent = state.action;
  }

  setInterval(() => {
    fetch('/state')
      .then(r => r.json())
      .then(drawRobot);
  }, 50);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE)


@app.route("/command", methods=["POST"])
def command():
    from flask import request
    data = request.get_json()
    driving["command"] = data.get("command")
    driving["active"] = data.get("active", False)
    if not driving["active"]:
        robot["action"] = "Stopped"
    return jsonify(ok=True)


@app.route("/speed", methods=["POST"])
def set_speed():
    from flask import request
    data = request.get_json()
    robot["speed"] = int(data.get("speed", 80))
    return jsonify(ok=True)


@app.route("/state")
def state():
    return jsonify(
        x=robot["x"],
        y=robot["y"],
        angle=robot["angle"],
        action=robot["action"],
    )


def get_local_ip():
    """Get the Mac's local WiFi IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


if __name__ == "__main__":
    ip = get_local_ip()
    print("\n" + "=" * 44)
    print("  🤖  iPhone Robot Controller is running!")
    print("=" * 44)
    print(f"\n  On your iPhone, open Safari and go to:\n")
    print(f"  👉  http://{ip}:8080\n")
    print("  Make sure iPhone & Mac are on same WiFi!")
    print("\n  Press Ctrl+C to stop.")
    print("=" * 44 + "\n")
    app.run(host="0.0.0.0", port=8080)

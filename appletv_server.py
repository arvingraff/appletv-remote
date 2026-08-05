"""
Apple TV Headless Remote Server
Runs the iPhone web remote with NO GUI — safe to run as a background service.
Start automatically at login via LaunchAgent.
"""

import asyncio
import socket
import threading
import logging

# ── Silence Flask/Werkzeug logs ───────────────────────────────────────────────
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

from flask import Flask, jsonify, request as flask_request
import pyatv

# ── Config (must match apple_tv_gui.py) ──────────────────────────────────────
APPLE_TV_ID = "12:FD:8F:CE:56:74"
COMPANION_CREDENTIALS = (
    "fcdc3f48ff8846f5e4ab9513e996504b5d1bd1ac42d6a2bc8b2b433e1ec9eef3:"
    "2778b797daf3cbf3909a063fa049419bc02e5c2aa16a4c3a00bd552137dbeb37:"
    "31324644384643452d353637342d344243422d413435452d413233343646333731334431:"
    "62396137376637662d396639662d343461302d623338642d356165626530323336376166"
)
AIRPLAY_CREDENTIALS = (
    "fcdc3f48ff8846f5e4ab9513e996504b5d1bd1ac42d6a2bc8b2b433e1ec9eef3:"
    "b267a6daf1231833fa57942ad1712c74eb89f990076221b8fda361b42cc2ba0e:"
    "31324644384643452d353637342d344243422d413435452d413233343646333731334431:"
    "34333131306434342d393966662d343531362d626131372d613637643232396666303063"
)
PORT = 9876

# ── State ─────────────────────────────────────────────────────────────────────
atv        = None
loop       = asyncio.new_event_loop()
now_playing = ""
connected  = False

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def run(coro):
    """Run a coroutine on the background event loop and wait for the result."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=8)

# ── Connect ───────────────────────────────────────────────────────────────────

async def _connect():
    global atv, connected
    print("🔍 Scanning for Apple TV…")
    while True:
        try:
            devices = await pyatv.scan(loop, identifier=APPLE_TV_ID)
            if devices:
                devices[0].set_credentials(pyatv.Protocol.Companion, COMPANION_CREDENTIALS)
                devices[0].set_credentials(pyatv.Protocol.AirPlay,   AIRPLAY_CREDENTIALS)
                atv = await pyatv.connect(devices[0], loop)
                connected = True
                ip = get_local_ip()
                print(f"✅ Connected to Apple TV!")
                print(f"📱 Open on iPhone: http://{ip}:{PORT}")
                break
            else:
                print("❌ Apple TV not found, retrying in 10s…")
        except Exception as e:
            print(f"❌ Error: {e}, retrying in 10s…")
        await asyncio.sleep(10)

async def _refresh():
    """Poll now-playing every 5 seconds."""
    global now_playing
    while True:
        if atv:
            try:
                p = await atv.metadata.playing()
                title = p.title or ""
                state = str(p.device_state).split(".")[-1]
                now_playing = f"🎬 {title}  [{state}]" if title else ""
            except Exception:
                now_playing = ""
        await asyncio.sleep(5)

def _run_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

# ── iPhone Web Page ───────────────────────────────────────────────────────────

PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>🍎 Apple TV Remote</title>
<style>
  :root {
    --bg:#0d0d1a; --card:#16213e; --accent:#e94560;
    --green:#00b894; --blue:#1e3a8a; --text:#ffffff; --sub:#aaaaaa;
  }
  *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
  body{
    background:var(--bg);color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif;
    min-height:100dvh;
    padding:env(safe-area-inset-top,20px) 16px env(safe-area-inset-bottom,20px);
    display:flex;flex-direction:column;align-items:center;gap:14px;
  }
  h1{font-size:1.3em;letter-spacing:.03em;margin-top:6px}
  #status{font-size:.8em;color:var(--sub);min-height:1.2em;text-align:center}
  #nowplaying{font-size:.85em;color:#ff6666;text-align:center;min-height:1.2em}
  .card{
    background:var(--card);border-radius:20px;padding:14px;
    width:100%;max-width:360px;display:flex;flex-direction:column;align-items:center;gap:10px;
  }
  .row{display:flex;gap:10px;justify-content:center;width:100%}
  button{
    background:var(--blue);color:var(--text);border:none;
    border-radius:16px;font-size:1.1em;font-weight:700;
    cursor:pointer;user-select:none;
    transition:transform .08s,opacity .08s;
    display:flex;align-items:center;justify-content:center;
  }
  button:active{transform:scale(.92);opacity:.8}
  .btn-sq{width:72px;height:72px}
  .btn-wide{flex:1;height:56px}
  .red{background:var(--accent)}
  .green{background:var(--green)}
  .dark{background:#2d3561}
  .gray{background:#3a3a4a}
  .dpad{position:relative;width:200px;height:200px}
  .dpad button{position:absolute;background:var(--blue);border-radius:14px}
  .dpad .up   {top:0;   left:50%;transform:translateX(-50%);width:60px;height:60px}
  .dpad .dn   {bottom:0;left:50%;transform:translateX(-50%);width:60px;height:60px}
  .dpad .lt   {left:0;  top:50%; transform:translateY(-50%);width:60px;height:60px}
  .dpad .rt   {right:0; top:50%; transform:translateY(-50%);width:60px;height:60px}
  .dpad .ok   {
    position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
    width:72px;height:72px;border-radius:50%;background:#334155;font-size:1.4em;
  }
  .section-label{
    font-size:.7em;text-transform:uppercase;letter-spacing:.08em;
    color:var(--sub);width:100%;text-align:left;padding-left:4px;
  }
</style>
</head>
<body>
<h1>🍎 Apple TV Remote</h1>
<div id="status">Connecting…</div>
<div id="nowplaying"></div>

<div class="card">
  <div class="section-label">Playback</div>
  <div class="row">
    <button class="btn-sq dark" onclick="cmd('previous')">⏮</button>
    <button class="btn-sq green" onclick="cmd('play_pause')">⏯</button>
    <button class="btn-sq dark" onclick="cmd('next')">⏭</button>
  </div>
  <div class="row">
    <button class="btn-wide dark" onclick="cmd('skip_backward')">⏪ -10s</button>
    <button class="btn-wide dark" onclick="cmd('skip_forward')">+10s ⏩</button>
  </div>
  <div class="row">
    <button class="btn-wide gray" onclick="cmd('volume_down')">🔉 Vol−</button>
    <button class="btn-wide gray" onclick="cmd('volume_up')">🔊 Vol+</button>
  </div>
</div>

<div class="card">
  <div class="section-label">Navigate</div>
  <div class="dpad">
    <button class="up"  onclick="cmd('up')">▲</button>
    <button class="dn"  onclick="cmd('down')">▼</button>
    <button class="lt"  onclick="cmd('left')">◀</button>
    <button class="rt"  onclick="cmd('right')">▶</button>
    <button class="ok"  onclick="cmd('select')">OK</button>
  </div>
</div>

<div class="card">
  <div class="section-label">System</div>
  <div class="row">
    <button class="btn-wide green" onclick="cmd('home')">🏠 Home</button>
    <button class="btn-wide dark"  onclick="cmd('menu')">◀ Back</button>
  </div>
  <div class="row">
    <button class="btn-wide red"  onclick="cmd('sleep')">⏻ Sleep</button>
    <button class="btn-wide gray" onclick="cmd('screensaver')">🌙 Screen saver</button>
  </div>
  <div class="row">
    <button class="btn-wide dark" onclick="cmd('subtitles')">💬 Subtitles</button>
  </div>
</div>

<div class="card">
  <div class="section-label">Apps</div>
  <div class="row" style="flex-wrap:wrap;gap:8px">
    <button style="flex:0 0 calc(50% - 4px);height:48px;background:#E50914" onclick="launch('com.netflix.Netflix')">🎬 Netflix</button>
    <button style="flex:0 0 calc(50% - 4px);height:48px;background:#113CCF" onclick="launch('com.disney.disneyplus')">🏰 Disney+</button>
    <button style="flex:0 0 calc(50% - 4px);height:48px;background:#00693E" onclick="launch('no.nrk.nrktvapp')">📺 NRK TV</button>
    <button style="flex:0 0 calc(50% - 4px);height:48px;background:#6A0DAD" onclick="launch('com.wbd.stream')">💜 HBO</button>
    <button style="flex:0 0 calc(50% - 4px);height:48px;background:#FF0000" onclick="launch('com.google.ios.youtube')">▶️ YouTube</button>
    <button style="flex:0 0 calc(50% - 4px);height:48px;background:#FF6600" onclick="launch('no.tv2.sumo')">📺 TV 2</button>
  </div>
</div>

<script>
async function cmd(action){
  try{
    const r=await fetch('/x/do',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});
    const d=await r.json();
    document.getElementById('status').textContent=d.status||action;
  }catch(e){document.getElementById('status').textContent='⚠️ '+e;}
}
async function launch(bundle_id){
  try{
    const r=await fetch('/x/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bundle_id})});
    const d=await r.json();
    document.getElementById('status').textContent=d.status||bundle_id;
  }catch(e){document.getElementById('status').textContent='⚠️ '+e;}
}
async function poll(){
  try{
    const r=await fetch('/x/now');
    const d=await r.json();
    document.getElementById('status').textContent=d.connected?'✅ Connected':'❌ Not connected';
    document.getElementById('nowplaying').textContent=d.now_playing||'';
  }catch(e){}
}
poll();setInterval(poll,5000);
</script>
</body>
</html>
"""

# ── Flask app ─────────────────────────────────────────────────────────────────

flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return PAGE

@flask_app.route("/x/do", methods=["POST"])
def api_do():
    if not atv:
        return jsonify({"status": "⚠️ Not connected"})
    data   = flask_request.get_json(force=True)
    action = data.get("action", "")
    async def _do():
        rc = atv.remote_control
        if   action == "play_pause":    await rc.play_pause()
        elif action == "next":          await rc.next()
        elif action == "previous":      await rc.previous()
        elif action == "volume_up":     await rc.volume_up()
        elif action == "volume_down":   await rc.volume_down()
        elif action == "up":            await rc.up()
        elif action == "down":          await rc.down()
        elif action == "left":          await rc.left()
        elif action == "right":         await rc.right()
        elif action == "select":        await rc.select()
        elif action == "menu":          await rc.menu()
        elif action == "home":          await rc.home()
        elif action == "skip_forward":  await rc.skip_forward()
        elif action == "skip_backward": await rc.skip_backward()
        elif action == "screensaver":   await rc.screensaver()
        elif action == "subtitles":    await rc.subtitle()
        elif action == "sleep":
            try:    await atv.power.turn_off()
            except Exception: await rc.suspend()
    try:
        run(_do())
        return jsonify({"status": f"✅ {action}"})
    except Exception as e:
        return jsonify({"status": f"❌ {e}"})

@flask_app.route("/x/open", methods=["POST"])
def api_open():
    if not atv:
        return jsonify({"status": "⚠️ Not connected"})
    data      = flask_request.get_json(force=True)
    bundle_id = data.get("bundle_id", "")
    try:
        run(atv.apps.launch_app(bundle_id))
        return jsonify({"status": f"🚀 Launched"})
    except Exception as e:
        return jsonify({"status": f"❌ {e}"})

@flask_app.route("/x/now")
def api_now():
    return jsonify({"connected": connected, "now_playing": now_playing})

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Start the asyncio event loop in a background thread
    t = threading.Thread(target=_run_loop, daemon=True)
    t.start()

    # Connect to Apple TV
    asyncio.run_coroutine_threadsafe(_connect(), loop)
    asyncio.run_coroutine_threadsafe(_refresh(), loop)

    ip = get_local_ip()
    print(f"🌐 Starting server on http://{ip}:{PORT}")
    flask_app.run(host="0.0.0.0", port=PORT, use_reloader=False)

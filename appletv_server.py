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

# ── Config ───────────────────────────────────────────────────────────────────
APPLE_TV_ID = "12:FD:8F:CE:56:74"

import json as _json, os as _os
_CREDS_FILE = _os.path.join(_os.path.dirname(__file__), "credentials.json")
try:
    _creds = _json.load(open(_CREDS_FILE))
    COMPANION_CREDENTIALS = _creds["companion"]
    AIRPLAY_CREDENTIALS   = _creds["airplay"]
except Exception:
    COMPANION_CREDENTIALS = ""
    AIRPLAY_CREDENTIALS   = ""
    print("⚠️  credentials.json not found — run pair_pi.py first")
PORT = 9876

# ── State ─────────────────────────────────────────────────────────────────────
atv         = None
loop        = asyncio.new_event_loop()
now_playing = ""
now_position = 0
now_total    = 0
connected   = False

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
    global now_playing, now_position, now_total
    while True:
        if atv:
            try:
                p = await atv.metadata.playing()
                title = p.title or ""
                state = str(p.device_state).split(".")[-1]
                now_playing  = f"🎬 {title}  [{state}]" if title else ""
                now_position = p.position or 0
                now_total    = p.total_time or 0
            except Exception:
                now_playing = ""
        await asyncio.sleep(4)

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
  :root{--bg:#0d0d1a;--card:#16213e;--accent:#e94560;--green:#00b894;--blue:#1e3a8a;--text:#ffffff;--sub:#aaaaaa}
  *{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
  body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Display",sans-serif;min-height:100dvh;padding:env(safe-area-inset-top,20px) 16px env(safe-area-inset-bottom,20px);display:flex;flex-direction:column;align-items:center;gap:14px}
  h1{font-size:1.3em;letter-spacing:.03em;margin-top:6px}
  #status{font-size:.8em;color:var(--sub);min-height:1.2em;text-align:center}
  #nowplaying{font-size:.85em;color:#ff6666;text-align:center;min-height:1.2em}
  .card{background:var(--card);border-radius:20px;padding:14px;width:100%;max-width:360px;display:flex;flex-direction:column;align-items:center;gap:10px}
  .row{display:flex;gap:10px;justify-content:center;width:100%}
  button{background:var(--blue);color:var(--text);border:none;border-radius:16px;font-size:1.1em;font-weight:700;cursor:pointer;user-select:none;transition:transform .08s,opacity .08s;display:flex;align-items:center;justify-content:center}
  button:active{transform:scale(.92);opacity:.8}
  .btn-sq{width:72px;height:72px}
  .btn-wide{flex:1;height:56px}
  .red{background:var(--accent)}
  .green{background:var(--green)}
  .dark{background:#2d3561}
  .gray{background:#3a3a4a}
  .purple{background:#6c3483}
  .dpad{position:relative;width:200px;height:200px}
  .dpad button{position:absolute;background:var(--blue);border-radius:14px}
  .dpad .up{top:0;left:50%;transform:translateX(-50%);width:60px;height:60px}
  .dpad .dn{bottom:0;left:50%;transform:translateX(-50%);width:60px;height:60px}
  .dpad .lt{left:0;top:50%;transform:translateY(-50%);width:60px;height:60px}
  .dpad .rt{right:0;top:50%;transform:translateY(-50%);width:60px;height:60px}
  .dpad .ok{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:72px;height:72px;border-radius:50%;background:#334155;font-size:1.4em}
  .section-label{font-size:.7em;text-transform:uppercase;letter-spacing:.08em;color:var(--sub);width:100%;text-align:left;padding-left:4px}
  /* scrubber */
  .scrubber-row{width:100%;display:flex;flex-direction:column;gap:4px}
  .scrubber-row input[type=range]{width:100%;accent-color:var(--green);height:6px}
  .scrubber-times{display:flex;justify-content:space-between;font-size:.75em;color:var(--sub)}
  /* apps grid */
  #apps-grid{display:flex;flex-wrap:wrap;gap:8px;width:100%}
  #apps-grid button{flex:0 0 calc(50% - 4px);height:48px;font-size:.8em;border-radius:12px}
</style>
</head>
<body>
<h1>🍎 Apple TV Remote</h1>
<div id="status">Connecting…</div>
<div id="nowplaying"></div>

<!-- Playback -->
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
  <!-- Scrubber -->
  <div class="scrubber-row">
    <input type="range" id="scrubber" min="0" max="100" value="0" oninput="onScrub(this)">
    <div class="scrubber-times"><span id="pos-cur">0:00</span><span id="pos-tot">0:00</span></div>
  </div>
  <div class="row">
    <button class="btn-wide gray" onclick="cmd('volume_down')">🔉 Vol−</button>
    <button class="btn-wide gray" onclick="cmd('volume_up')">🔊 Vol+</button>
  </div>
</div>

<!-- Navigate -->
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

<!-- System -->
<div class="card">
  <div class="section-label">System</div>
  <div class="row">
    <button class="btn-wide green"  onclick="cmd('home')">🏠 Home</button>
    <button class="btn-wide dark"   onclick="cmd('menu')">◀ Back</button>
  </div>
  <div class="row">
    <button class="btn-wide purple" onclick="cmd('siri')">🎤 Siri</button>
    <button class="btn-wide dark"   onclick="cmd('subtitles')">💬 Subtitles</button>
  </div>
  <div class="row">
    <button class="btn-wide red"    onclick="cmd('sleep')">⏻ Sleep</button>
    <button class="btn-wide gray"   onclick="cmd('screensaver')">🌙 Screen saver</button>
  </div>
</div>

<!-- Apps -->
<div class="card">
  <div class="section-label">Apps</div>
  <div id="apps-grid">
    <button style="background:#E50914" onclick="launch('com.netflix.Netflix')">🎬 Netflix</button>
    <button style="background:#113CCF" onclick="launch('com.disney.disneyplus')">🏰 Disney+</button>
    <button style="background:#00693E" onclick="launch('no.nrk.nrktvapp')">📺 NRK TV</button>
    <button style="background:#6A0DAD" onclick="launch('com.wbd.stream')">💜 HBO</button>
    <button style="background:#FF0000" onclick="launch('com.google.ios.youtube')">▶️ YouTube</button>
    <button style="background:#FF6600" onclick="launch('no.tv2.sumo')">📺 TV 2</button>
  </div>
  <div class="row" style="margin-top:4px">
    <button class="btn-wide dark" onclick="loadApps()">📋 Load all apps</button>
  </div>
</div>

<script>
let scrubbing=false, totalSecs=0;

async function cmd(action){
  try{
    const r=await fetch('/x/do',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action})});
    const d=await r.json();
    document.getElementById('status').textContent=d.status||action;
  }catch(e){document.getElementById('status').textContent='⚠️ '+e}
}

async function launch(bundle_id){
  document.getElementById('status').textContent='🚀 Launching…';
  try{
    const r=await fetch('/x/open',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({bundle_id})});
    const d=await r.json();
    document.getElementById('status').textContent=d.status||bundle_id;
  }catch(e){document.getElementById('status').textContent='⚠️ '+e}
}

async function loadApps(){
  document.getElementById('status').textContent='📋 Loading apps…';
  try{
    const r=await fetch('/x/apps');
    const d=await r.json();
    if(!d.apps||!d.apps.length){document.getElementById('status').textContent='⚠️ No apps found';return}
    const grid=document.getElementById('apps-grid');
    grid.innerHTML='';
    d.apps.forEach(a=>{
      const b=document.createElement('button');
      b.textContent=a.name;
      b.onclick=()=>launch(a.id);
      grid.appendChild(b);
    });
    document.getElementById('status').textContent=`✅ Loaded ${d.apps.length} apps`;
  }catch(e){document.getElementById('status').textContent='⚠️ '+e}
}

function fmt(s){const m=Math.floor(s/60);return m+':'+(s%60).toString().padStart(2,'0')}

function onScrub(el){
  scrubbing=true;
  document.getElementById('pos-cur').textContent=fmt(Math.round(el.value));
}
document.getElementById('scrubber').addEventListener('change',async function(){
  scrubbing=false;
  await fetch('/x/seek',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({position:parseInt(this.value)})});
});

async function poll(){
  try{
    const r=await fetch('/x/now');
    const d=await r.json();
    document.getElementById('status').textContent=d.connected?'✅ Connected':'❌ Not connected';
    document.getElementById('nowplaying').textContent=d.now_playing||'';
    if(!scrubbing && d.total_time>0){
      totalSecs=d.total_time;
      const sc=document.getElementById('scrubber');
      sc.max=totalSecs;
      sc.value=d.position||0;
      document.getElementById('pos-cur').textContent=fmt(d.position||0);
      document.getElementById('pos-tot').textContent=fmt(totalSecs);
    }
  }catch(e){}
}
poll();setInterval(poll,4000);
</script>
</body>
</html>
"""
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
        elif action == "subtitles":    await rc.top_menu()
        elif action == "siri":         await rc.home_hold()
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

@flask_app.route("/x/apps")
def api_apps():
    if not atv:
        return jsonify({"apps": []})
    try:
        apps = run(atv.apps.app_list())
        return jsonify({"apps": [{"name": a.name, "id": a.identifier} for a in apps]})
    except Exception as e:
        return jsonify({"apps": [], "error": str(e)})

@flask_app.route("/x/seek", methods=["POST"])
def api_seek():
    if not atv:
        return jsonify({"status": "⚠️ Not connected"})
    data = flask_request.get_json(force=True)
    pos  = int(data.get("position", 0))
    try:
        run(atv.remote_control.set_position(pos))
        return jsonify({"status": f"⏩ {pos}s"})
    except Exception as e:
        return jsonify({"status": f"❌ {e}"})

@flask_app.route("/x/now")
def api_now():
    return jsonify({
        "connected":   connected,
        "now_playing": now_playing,
        "position":    now_position,
        "total_time":  now_total,
    })

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

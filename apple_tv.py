"""
Apple TV Controller 🍎📺
Control your Apple TV from your Mac using Python!
No need to press Enter — just tap a key and it fires instantly!

Keybindings:
  space — Play / Pause
  n     — Next
  p     — Previous
  +     — Volume Up
  -     — Volume Down
  i     — What's playing?
  h     — Home screen
  w     — Up
  s     — Down
  a     — Left
  d     — Right
  enter — Select
  b     — Back / Menu
  q     — Quit
"""

import asyncio
import sys
import tty
import termios
import os
import pyatv

APPLE_TV_ID = "12:FD:8F:CE:56:74"  # Entertainment Room
COMPANION_CREDENTIALS = "fcdc3f48ff8846f5e4ab9513e996504b5d1bd1ac42d6a2bc8b2b433e1ec9eef3:2778b797daf3cbf3909a063fa049419bc02e5c2aa16a4c3a00bd552137dbeb37:31324644384643452d353637342d344243422d413435452d413233343646333731334431:62396137376637662d396639662d343461302d623338642d356165626530323336376166"

# App bundle IDs
APPS = {
    "1": ("🎬 Netflix",    "com.netflix.Netflix"),
    "2": ("🏰 Disney+",    "com.disney.disneyplus"),
    "3": ("📺 NRK TV",     "no.nrk.nrktvapp"),
    "4": ("💜 HBO Max",    "com.wbd.stream"),
    "5": ("▶️  YouTube",   "com.google.ios.youtube"),
    "6": ("📺 TV 2 Play",  "no.tv2.sumo"),
}


def getch():
    """Read a single keypress without needing Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def clear():
    os.system("clear")


async def get_atv():
    """Find and connect to the Apple TV using saved credentials."""
    print("🔍 Connecting to Entertainment Room...")
    devices = await pyatv.scan(asyncio.get_event_loop(), identifier=APPLE_TV_ID)
    if not devices:
        print("❌ Apple TV not found! Make sure it's on and on the same WiFi.")
        return None
    devices[0].set_credentials(pyatv.Protocol.Companion, COMPANION_CREDENTIALS)
    atv = await pyatv.connect(devices[0], asyncio.get_event_loop())
    print("✅ Connected!\n")
    return atv


async def now_playing(atv):
    """Show what's currently playing."""
    try:
        playing = await atv.metadata.playing()
        title  = playing.title or "Unknown"
        artist = playing.artist or "—"
        state  = str(playing.device_state).split(".")[-1]
        pos    = playing.position or 0
        total  = playing.total_time or 0
        return f"🎬 {title} — {artist}  [{state}]  {pos}s/{total}s"
    except Exception:
        return "🎬 Nothing playing"


async def send(coro, label):
    """Send a command, return a status message."""
    try:
        await coro
        return label
    except Exception as e:
        return f"❌ {e}"


def draw(status, now):
    """Redraw the controller UI."""
    clear()
    app_lines = "  ".join([f"\033[1m{k}\033[0m {v[0]}" for k, v in APPS.items()])
    print(f"""
\033[1m\033[96m  🍎 APPLE TV — Entertainment Room\033[0m
  ─────────────────────────────────────────
  \033[90mApps\033[0m
  {app_lines}

  \033[90mPlayback\033[0m
   \033[1mSPACE\033[0m  ▶️  Play / Pause     \033[1mN\033[0m  ⏭️  Next
   \033[1mP\033[0m      ⏮️  Previous

  \033[90mVolume\033[0m
   \033[1m+\033[0m      🔊 Volume Up        \033[1m-\033[0m  🔉 Volume Down

  \033[90mNavigation\033[0m
        \033[1mW\033[0m ⬆️
   \033[1mA\033[0m ⬅️   \033[1mS\033[0m ⬇️   \033[1mD\033[0m ➡️
   \033[1mENTER\033[0m  ✅ Select
   \033[1mB\033[0m      ◀️  Back / Menu
   \033[1mH\033[0m      🏠 Home screen

  \033[90mInfo\033[0m
   \033[1mI\033[0m      🎬 Now playing      \033[1mQ\033[0m  🚪 Quit
  ─────────────────────────────────────────""")
    print(f"  {now}")
    print(f"  \033[93m{status}\033[0m")
    print()
    print("  Press a key...")


async def main():
    atv = await get_atv()
    if not atv:
        return

    status = "Ready!"
    now    = await now_playing(atv)
    draw(status, now)

    try:
        while True:
            key = getch()
            rc  = atv.remote_control

            if   key == " ":  status = await send(rc.play_pause(), "▶️  Play / Pause")
            elif key == "n":  status = await send(rc.next(),        "⏭️  Next")
            elif key == "p":  status = await send(rc.previous(),    "⏮️  Previous")
            elif key == "+":  status = await send(rc.volume_up(),   "🔊 Volume Up")
            elif key == "-":  status = await send(rc.volume_down(), "🔉 Volume Down")
            elif key == "w":  status = await send(rc.up(),          "⬆️  Up")
            elif key == "s":  status = await send(rc.down(),        "⬇️  Down")
            elif key == "a":  status = await send(rc.left(),        "⬅️  Left")
            elif key == "d":  status = await send(rc.right(),       "➡️  Right")
            elif key == "\r": status = await send(rc.select(),      "✅ Select")
            elif key == "b":  status = await send(rc.menu(),        "◀️  Back / Menu")
            elif key == "h":  status = await send(rc.home(),        "🏠 Home")
            elif key in APPS:
                name, bundle_id = APPS[key]
                status = await send(atv.apps.launch_app(bundle_id), f"🚀 Launching {name}...")
            elif key == "i":
                now    = await now_playing(atv)
                status = "ℹ️  Updated!"
            elif key == "q":
                clear()
                print("\n  👋 Bye!\n")
                break
            else:
                status = f"❓ Unknown key '{key}'"

            if key != "i":
                now = await now_playing(atv)
            draw(status, now)
            await asyncio.sleep(0.1)

    finally:
        atv.close()


if __name__ == "__main__":
    asyncio.run(main())

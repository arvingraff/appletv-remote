"""
Apple TV Game Controller 🍎🎮
A game-controller style GUI for your Apple TV.
Click buttons or press keys — no terminal needed!
"""

import asyncio
import threading
import subprocess
import datetime
import io
import socket
import tkinter as tk
from tkinter import font as tkfont

from flask import Flask, jsonify, request as flask_request

# ── Spoof macOS build number so pyatv's native libs don't abort ──────────────
import platform
_real_mac_ver = platform.mac_ver
platform.mac_ver = lambda: ("15.7.4", ("", "", ""), "arm64")

import pyatv

try:
    from PIL import Image, ImageTk, ImageFilter, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ── Config ────────────────────────────────────────────────────────────────────
APPLE_TV_ID = "YOUR_APPLE_TV_MAC_ADDRESS"   # e.g. "AA:BB:CC:DD:EE:FF"
COMPANION_CREDENTIALS = ""   # paste your Companion credentials here (run: atvremote --id <id> pair)
AIRPLAY_CREDENTIALS   = ""   # paste your AirPlay credentials here

APPS = [
    ("🎬 Netflix",   "com.netflix.Netflix",       "#E50914"),
    ("🏰 Disney+",   "com.disney.disneyplus",      "#113CCF"),
    ("📺 NRK TV",    "no.nrk.nrktvapp",            "#00693E"),
    ("💜 HBO",       "com.wbd.stream",             "#6A0DAD"),
    ("▶️ YouTube",  "com.google.ios.youtube",     "#FF0000"),
    ("📺 TV 2 Play", "no.tv2.sumo",               "#FF6600"),
]

GAMES = [
    ("🏎️ Road Rush",   "com.ketchapp.RoadRush",          "#e17055"),
    ("🐦 Crossy Road", "com.yodo1.crossyroad.atv",        "#00b894"),
    ("🎮 Rayman Mini", "com.ubisoft.RaymanMini",          "#6c5ce7"),
    ("⚽ Badminton",   "com.natenai.badmintonclash",      "#fdcb6e"),
    ("🎯 Archery",     "com.natenai.archeryclash",        "#e84393"),
    ("🧩 Alto's Odd.", "com.noodlecake.altosodyssey.atv", "#0984e3"),
]

# ── Colour themes ─────────────────────────────────────────────────────────────
DARK_THEME = {
    "BG":        "#0d0d1a",
    "CARD":      "#16213e",
    "CARD2":     "#1a2550",
    "BTN_NAV":   "#1e3a8a",
    "BTN_HOT":   "#e94560",
    "BTN_GREEN": "#00b894",
    "BTN_TEXT":  "#ff3333",
    "LABEL_FG":  "#ff3333",
    "STATUS_FG": "#ff6666",
    "NOW_FG":    "#ff3333",
    "CLOCK_FG":  "#ff3333",
    "ENTRY_BG":  "#0d1b2a",
    "ENTRY_FG":  "#ff3333",
    "FOOTER_FG": "#cc2222",
}
LIGHT_THEME = {
    "BG":        "#f0f4ff",
    "CARD":      "#ffffff",
    "CARD2":     "#e8eeff",
    "BTN_NAV":   "#3b82f6",
    "BTN_HOT":   "#e94560",
    "BTN_GREEN": "#059669",
    "BTN_TEXT":  "#cc0000",
    "LABEL_FG":  "#cc0000",
    "STATUS_FG": "#ff3333",
    "NOW_FG":    "#cc0000",
    "CLOCK_FG":  "#cc0000",
    "ENTRY_BG":  "#e8eeff",
    "ENTRY_FG":  "#cc0000",
    "FOOTER_FG": "#ff6666",
}


class AppleTVController:
    def __init__(self, root: tk.Tk):
        self.root       = root
        self.atv        = None
        self.loop       = asyncio.new_event_loop()
        self._dark_mode = True
        self._theme     = DARK_THEME
        self._art_photo = None   # keep reference to avoid GC

        self._status_var = tk.StringVar(value="Connecting…")
        self._now_var    = tk.StringVar(value="🎬 Nothing playing")
        self._search_var = tk.StringVar()
        self._clock_var  = tk.StringVar()

        root.title("🍎 Apple TV Controller")
        root.resizable(True, True)

        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{sw}x{sh}+0+0")
        root.attributes("-fullscreen", True)

        self._build_ui()
        self._apply_theme()
        self._bind_keys()
        self._tick_clock()

        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        root.after(200, lambda: self._run(self._connect()))

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self):
        T = self._theme
        self.root.configure(bg=T["BG"])
        # Walk every widget and recolour
        self._recolour_widget(self.root)

    def _recolour_widget(self, w):
        T = self._theme
        cls = w.winfo_class()
        try:
            if cls in ("Frame", "Toplevel"):
                current = w.cget("bg")
                # Map old colour -> new
                mapping = {
                    DARK_THEME["BG"]:    T["BG"],
                    LIGHT_THEME["BG"]:   T["BG"],
                    DARK_THEME["CARD"]:  T["CARD"],
                    LIGHT_THEME["CARD"]: T["CARD"],
                    DARK_THEME["CARD2"]: T["CARD2"],
                    LIGHT_THEME["CARD2"]:T["CARD2"],
                }
                w.configure(bg=mapping.get(current, current))
            elif cls == "Label":
                w.configure(bg=self._map_bg(w.cget("bg")),
                            fg=self._map_fg(w.cget("fg")))
            elif cls == "Button":
                w.configure(fg=T["BTN_TEXT"],
                            activeforeground=T["BTN_TEXT"])
            elif cls == "Entry":
                w.configure(bg=T["ENTRY_BG"], fg=T["ENTRY_FG"],
                            insertbackground=T["ENTRY_FG"])
        except Exception:
            pass
        for child in w.winfo_children():
            self._recolour_widget(child)

    def _map_bg(self, c):
        T = self._theme
        m = {
            DARK_THEME["BG"]:    T["BG"],
            LIGHT_THEME["BG"]:   T["BG"],
            DARK_THEME["CARD"]:  T["CARD"],
            LIGHT_THEME["CARD"]: T["CARD"],
            DARK_THEME["CARD2"]: T["CARD2"],
            LIGHT_THEME["CARD2"]:T["CARD2"],
        }
        return m.get(c, c)

    def _map_fg(self, c):
        T = self._theme
        m = {
            DARK_THEME["LABEL_FG"]:  T["LABEL_FG"],
            LIGHT_THEME["LABEL_FG"]: T["LABEL_FG"],
            DARK_THEME["STATUS_FG"]: T["STATUS_FG"],
            LIGHT_THEME["STATUS_FG"]:T["STATUS_FG"],
            DARK_THEME["NOW_FG"]:    T["NOW_FG"],
            LIGHT_THEME["NOW_FG"]:   T["NOW_FG"],
            DARK_THEME["CLOCK_FG"]:  T["CLOCK_FG"],
            LIGHT_THEME["CLOCK_FG"]: T["CLOCK_FG"],
            DARK_THEME["FOOTER_FG"]: T["FOOTER_FG"],
            LIGHT_THEME["FOOTER_FG"]:T["FOOTER_FG"],
            "#a0c4ff": T["LABEL_FG"],
            "#b2bec3": T["LABEL_FG"],
        }
        return m.get(c, c)

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        self._theme = DARK_THEME if self._dark_mode else LIGHT_THEME
        self._apply_theme()
        icon = "🌙 Dark" if not self._dark_mode else "☀️ Light"
        self._theme_btn.configure(text=icon)

    # ── Async helpers ─────────────────────────────────────────────────────────

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _run(self, coro):
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    async def _connect(self):
        self._set_status("🔍 Connecting…")
        try:
            devices = await pyatv.scan(self.loop, identifier=APPLE_TV_ID)
            if not devices:
                self._set_status("❌ Apple TV not found!")
                return
            devices[0].set_credentials(pyatv.Protocol.Companion, COMPANION_CREDENTIALS)
            devices[0].set_credentials(pyatv.Protocol.AirPlay,   AIRPLAY_CREDENTIALS)
            self.atv = await pyatv.connect(devices[0], self.loop)
            ip = _get_local_ip()
            self._set_status(f"✅ Connected — 📱 iPhone: http://{ip}:{IPHONE_PORT}")
            await self._refresh_now_playing()
        except Exception as e:
            self._set_status(f"❌ {e}")

    async def _send(self, coro, label: str):
        if not self.atv:
            self._set_status("❌ Not connected"); return
        try:
            await coro
            self._set_status(label)
            await self._refresh_now_playing()
        except Exception as e:
            self._set_status(f"❌ {e}")

    async def _launch(self, name: str, bundle_id: str):
        if not self.atv:
            self._set_status("❌ Not connected"); return
        try:
            self._set_status(f"🚀 Launching {name}…")
            await self.atv.apps.launch_app(bundle_id)
            await self._refresh_now_playing()
        except Exception as e:
            self._set_status(f"❌ {e}")

    async def _refresh_now_playing(self):
        if not self.atv:
            return
        try:
            p     = await self.atv.metadata.playing()
            title = p.title or "Unknown"
            state = str(p.device_state).split(".")[-1]
            self.root.after(0, lambda: self._now_var.set(f"🎬 {title}  [{state}]"))
            # Fetch artwork
            if HAS_PIL:
                art = await self.atv.metadata.artwork(width=120, height=120)
                if art and art.bytes:
                    self.root.after(0, lambda: self._update_artwork(art.bytes))
        except Exception:
            self.root.after(0, lambda: self._now_var.set("🎬 Nothing playing"))

    def _update_artwork(self, data: bytes):
        """Render now-playing artwork in the info card."""
        try:
            img = Image.open(io.BytesIO(data)).resize((50, 50), Image.LANCZOS)
            mask = Image.new("L", (50, 50), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([0, 0, 50, 50], radius=8, fill=255)
            img.putalpha(mask)
            self._art_photo = ImageTk.PhotoImage(img)
            self._art_label.configure(image=self._art_photo, text="")
        except Exception:
            pass

    async def _do_search(self, query: str):
        if not self.atv or not query.strip():
            return
        self._set_status(f'🔍 Opening search for "{query}"…')
        try:
            await self.atv.apps.launch_app("com.apple.TVSearch")
            await asyncio.sleep(3.0)
            await self.atv.keyboard.text_set(query)
            self._set_status(f'✅ Typed "{query}" — press OK to search!')
        except Exception as e:
            self._set_status(f"❌ Search failed: {e}")

    def _set_status(self, msg: str):
        self.root.after(0, lambda: self._status_var.set(msg))

    async def _load_all_apps(self):
        """Fetch every installed app from the Apple TV and show as buttons."""
        if not self.atv:
            self._set_status("❌ Not connected"); return
        self._set_status("📲 Loading apps…")
        try:
            app_list = await self.atv.apps.app_list()
            def build():
                # Clear old buttons
                for w in self._all_apps_frame.winfo_children():
                    w.destroy()
                colours = ["#e17055","#00b894","#6c5ce7","#0984e3","#e84393","#fdcb6e","#e94560","#1e3a8a"]
                row = tk.Frame(self._all_apps_frame, bg=self._theme["CARD"])
                row.pack(fill="x")
                for i, app in enumerate(sorted(app_list, key=lambda a: a.name or "")):
                    if i % 8 == 0 and i != 0:
                        row = tk.Frame(self._all_apps_frame, bg=self._theme["CARD"])
                        row.pack(fill="x", pady=(4, 0))
                    colour = colours[i % len(colours)]
                    name   = (app.name or app.identifier)[:14]
                    bid    = app.identifier
                    self._make_btn(row, name, colour,
                                   lambda b=bid, n=name: self._run(self._launch(n, b)),
                                   side="left", padx=6, pady=6, big=False)
                self._set_status(f"✅ Found {len(app_list)} apps")
            self.root.after(0, build)
        except Exception as e:
            self._set_status(f"❌ {e}")

    def _tick_clock(self):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._clock_var.set(f"🕐 {now}")
        self.root.after(1000, self._tick_clock)

    # ── UI Builder ────────────────────────────────────────────────────────────

    def _build_ui(self):
        T = self._theme

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=T["BG"])
        hdr.pack(fill="x", padx=30, pady=(20, 6))

        tk.Label(hdr, text="🍎  Apple TV Controller", bg=T["BG"],
                 fg=T["LABEL_FG"], font=("SF Pro Display", 34, "bold")).pack(side="left")
        tk.Label(hdr, textvariable=self._clock_var, bg=T["BG"],
                 fg=T["CLOCK_FG"], font=("SF Pro Display", 26, "bold")).pack(side="left", padx=(28, 0))

        # Right-side buttons
        tk.Button(hdr, text="✕  Quit", command=self._quit,
                  bg=T["BTN_HOT"], fg=T["BTN_TEXT"], relief="flat", bd=0,
                  font=("SF Pro Display", 15, "bold"), padx=16, pady=8,
                  cursor="hand2").pack(side="right")
        tk.Button(hdr, text="⏻  Sleep", command=self._sleep_atv,
                  bg="#4a4a4a", fg=T["BTN_TEXT"], relief="flat", bd=0,
                  font=("SF Pro Display", 15, "bold"), padx=16, pady=8,
                  cursor="hand2").pack(side="right", padx=(0, 10))
        # Persistent Home button in header for quick access
        tk.Button(hdr, text="🏠  Home", command=lambda: self._run(self._send(self.atv.remote_control.home(), "🏠 Home")) if self.atv else None,
                  bg=T["BTN_GREEN"], fg=T["BTN_TEXT"], relief="flat", bd=0,
                  font=("SF Pro Display", 15, "bold"), padx=14, pady=8,
                  cursor="hand2").pack(side="right", padx=(0, 10))
        self._theme_btn = tk.Button(hdr, text="☀️ Light", command=self._toggle_theme,
                  bg="#334155", fg=T["BTN_TEXT"], relief="flat", bd=0,
                  font=("SF Pro Display", 15, "bold"), padx=16, pady=8,
                  cursor="hand2")
        self._theme_btn.pack(side="right", padx=(0, 10))

        # ── Now Playing card ──────────────────────────────────────────────────
        info = tk.Frame(self.root, bg=T["CARD"], bd=0)
        info.pack(fill="x", padx=30, pady=(0, 8))

        # Small artwork thumbnail (left side)
        self._art_label = tk.Label(info, bg=T["CARD"],
                                   text="🎬", font=("SF Pro Display", 20))
        self._art_label.pack(side="left", padx=(12, 8), pady=6)

        # Text info (right of artwork)
        info_text = tk.Frame(info, bg=T["CARD"])
        info_text.pack(side="left", fill="both", expand=True, pady=6)
        tk.Label(info_text, textvariable=self._now_var, bg=T["CARD"], fg=T["NOW_FG"],
                 font=("SF Pro Display", 16), anchor="w").pack(anchor="w")
        tk.Label(info_text, textvariable=self._status_var, bg=T["CARD"], fg=T["STATUS_FG"],
                 font=("SF Pro Display", 14), anchor="w").pack(anchor="w", pady=(2, 0))

        # ── Search bar ────────────────────────────────────────────────────────
        srch_outer = tk.Frame(self.root, bg=T["BG"])
        srch_outer.pack(fill="x", padx=30, pady=(0, 8))
        tk.Label(srch_outer, text="🔍  Quick Search", bg=T["BG"], fg=T["LABEL_FG"],
                 font=("SF Pro Display", 17, "bold")).pack(anchor="w", pady=(0, 4))
        srch_card = tk.Frame(srch_outer, bg=T["CARD"])
        srch_card.pack(fill="x")
        srch_row = tk.Frame(srch_card, bg=T["CARD"])
        srch_row.pack(fill="x", padx=12, pady=10)
        self._search_entry = tk.Entry(
            srch_row, textvariable=self._search_var,
            bg=T["ENTRY_BG"], fg=T["ENTRY_FG"], insertbackground=T["ENTRY_FG"],
            font=("SF Pro Display", 20), relief="flat", bd=0,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 10))
        tk.Button(srch_row, text="Search  ↵", command=self._fire_search,
                  bg=T["BTN_GREEN"], fg=T["BTN_TEXT"], relief="flat", bd=0,
                  font=("SF Pro Display", 17, "bold"), padx=18, pady=8,
                  cursor="hand2").pack(side="left")
        self._search_entry.bind("<Return>", lambda e: self._fire_search())

        # ── Apps (fixed favourites) ───────────────────────────────────────────
        sec = self._section("📱  Favourite Apps")
        app_row = tk.Frame(sec, bg=T["CARD"])
        app_row.pack(fill="x", padx=12, pady=(0, 12))
        for name, bundle_id, colour in APPS:
            self._make_btn(app_row, name, colour,
                           lambda n=name, b=bundle_id: self._run(self._launch(n, b)),
                           side="left", padx=8, pady=8, big=True)

        # ── All Apps (fetched live from Apple TV) ─────────────────────────────
        all_sec = self._section("📲  All Apps on Apple TV")
        all_hdr = tk.Frame(all_sec, bg=T["CARD"])
        all_hdr.pack(fill="x", padx=12, pady=(6, 0))
        self._make_btn(all_hdr, "🔄 Load Apps", T["BTN_NAV"],
                       lambda: self._run(self._load_all_apps()),
                       side="left", padx=8, pady=6)
        self._all_apps_frame = tk.Frame(all_sec, bg=T["CARD"])
        self._all_apps_frame.pack(fill="x", padx=12, pady=(4, 12))

        # ── Playback + D-Pad ──────────────────────────────────────────────────
        mid = tk.Frame(self.root, bg=T["BG"])
        mid.pack(fill="both", expand=True, padx=30, pady=6)

        pb_outer = tk.Frame(mid, bg=T["BG"])
        pb_outer.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(pb_outer, text="▶️  Playback", bg=T["BG"], fg=T["LABEL_FG"],
                 font=("SF Pro Display", 17, "bold")).pack(anchor="w", pady=(0, 6))
        pb_card = tk.Frame(pb_outer, bg=T["CARD"])
        pb_card.pack(fill="both", expand=True)
        pb = tk.Frame(pb_card, bg=T["CARD"])
        pb.pack(expand=True)
        self._make_btn(pb, "⏮\nPrev",       T["BTN_NAV"], lambda: self._run(self._send(self.atv.remote_control.previous(),   "⏮ Previous")),   side="left", padx=6, pady=10, big=True, h=3)
        self._make_btn(pb, "⏪\n-10s",       T["BTN_NAV"], lambda: self._run(self._send(self.atv.remote_control.skip_backward(), "⏪ -10s")),     side="left", padx=6, pady=10, big=True, h=3)
        self._make_btn(pb, "⏯\nPlay/Pause", T["BTN_HOT"], lambda: self._run(self._send(self.atv.remote_control.play_pause(), "⏯ Play/Pause")), side="left", padx=6, pady=10, big=True, h=3)
        self._make_btn(pb, "⏩\n+10s",       T["BTN_NAV"], lambda: self._run(self._send(self.atv.remote_control.skip_forward(),  "⏩ +10s")),     side="left", padx=6, pady=10, big=True, h=3)
        self._make_btn(pb, "⏭\nNext",       T["BTN_NAV"], lambda: self._run(self._send(self.atv.remote_control.next(),       "⏭ Next")),        side="left", padx=6, pady=10, big=True, h=3)

        dp_outer = tk.Frame(mid, bg=T["BG"])
        dp_outer.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(dp_outer, text="🕹  Navigate", bg=T["BG"], fg=T["LABEL_FG"],
                 font=("SF Pro Display", 17, "bold")).pack(anchor="w", pady=(0, 6))
        dp_card = tk.Frame(dp_outer, bg=T["CARD"])
        dp_card.pack(fill="both", expand=True)
        dpad = tk.Frame(dp_card, bg=T["CARD"])
        dpad.pack(expand=True)

        tk.Frame(dpad, bg=T["CARD"], width=80).grid(row=0, column=0)
        self._make_dpad(dpad, "▲", 0, 1, lambda: self._run(self._send(self.atv.remote_control.up(),      "⬆ Up")))
        tk.Frame(dpad, bg=T["CARD"], width=80).grid(row=0, column=2)
        self._make_dpad(dpad, "◀", 1, 0, lambda: self._run(self._send(self.atv.remote_control.left(),    "⬅ Left")))
        self._make_dpad(dpad, "OK",  1, 1, lambda: self._run(self._send(self.atv.remote_control.select(), "✅ Select")), colour=T["BTN_HOT"])
        self._make_dpad(dpad, "▶", 1, 2, lambda: self._run(self._send(self.atv.remote_control.right(),   "➡ Right")))
        self._make_dpad(dpad, "▼", 2, 1, lambda: self._run(self._send(self.atv.remote_control.down(),    "⬇ Down")))

        bh = tk.Frame(dp_card, bg=T["CARD"])
        bh.pack(pady=(6, 10))
        self._make_btn(bh, "◀  Back", T["BTN_NAV"],   lambda: self._run(self._send(self.atv.remote_control.menu(), "◀ Back")), side="left", padx=8, big=True)
        self._make_btn(bh, "🏠  Home", T["BTN_GREEN"], lambda: self._run(self._send(self.atv.remote_control.home(), "🏠 Home")), side="left", padx=8, big=True)

        # ── Footer ────────────────────────────────────────────────────────────
        tk.Label(self.root,
                 text="⌨️  WASD/Arrows = navigate  •  Space = play  •  B = back  •  H = home  •  1-6 = apps  •  Q/Esc = quit",
                 bg=T["BG"], fg=T["FOOTER_FG"], font=("SF Pro Display", 12)).pack(pady=(6, 14))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fire_search(self):
        query = self._search_var.get().strip()
        if query:
            self._run(self._do_search(query))
            self._search_var.set("")

    def _section(self, title: str) -> tk.Frame:
        T = self._theme
        outer = tk.Frame(self.root, bg=T["BG"])
        outer.pack(fill="x", padx=30, pady=4)
        tk.Label(outer, text=title, bg=T["BG"], fg=T["LABEL_FG"],
                 font=("SF Pro Display", 17, "bold")).pack(anchor="w", pady=(0, 4))
        card = tk.Frame(outer, bg=T["CARD"], bd=0)
        card.pack(fill="x")
        return card

    def _make_btn(self, parent, text, colour, command,
                  side="left", padx=4, pady=4, width=None, big=False, h=None):
        T   = self._theme
        fs  = 19 if big else 13
        px  = 26 if big else 14
        py  = 16 if big else 10
        kw  = dict(height=h) if h else {}
        btn = tk.Button(
            parent, text=text, command=command,
            bg=colour, fg=T["BTN_TEXT"],
            activebackground=self._lighten(colour),
            activeforeground=T["BTN_TEXT"],
            relief="flat", bd=0,
            font=("SF Pro Display", fs, "bold"),
            padx=px, pady=py, cursor="hand2",
            width=width, **kw,
        )
        btn.pack(side=side, padx=padx, pady=pady)
        # Glow animation on hover
        btn.bind("<Enter>", lambda e, b=btn, c=colour: self._btn_glow(b, c, True))
        btn.bind("<Leave>", lambda e, b=btn, c=colour: self._btn_glow(b, c, False))
        btn.bind("<ButtonPress-1>",   lambda e, b=btn, c=colour: b.configure(bg=self._darken(c)))
        btn.bind("<ButtonRelease-1>", lambda e, b=btn, c=colour: b.configure(bg=self._lighten(c)))
        return btn

    def _make_dpad(self, parent, text, row, col, command, colour=None):
        T      = self._theme
        colour = colour or T["BTN_NAV"]
        btn = tk.Button(
            parent, text=text, command=command,
            bg=colour, fg=T["BTN_TEXT"],
            activebackground=self._lighten(colour),
            activeforeground=T["BTN_TEXT"],
            relief="flat", bd=0,
            font=("SF Pro Display", 22, "bold"),
            width=5, height=2, cursor="hand2",
        )
        btn.grid(row=row, column=col, padx=8, pady=8)
        btn.bind("<Enter>", lambda e, b=btn, c=colour: self._btn_glow(b, c, True))
        btn.bind("<Leave>", lambda e, b=btn, c=colour: self._btn_glow(b, c, False))
        btn.bind("<ButtonPress-1>",   lambda e, b=btn, c=colour: b.configure(bg=self._darken(c)))
        btn.bind("<ButtonRelease-1>", lambda e, b=btn, c=colour: b.configure(bg=self._lighten(c)))

    def _btn_glow(self, btn, colour, entering: bool):
        """Animate button brightness on hover."""
        steps  = 6
        delay  = 18
        target = self._lighten(colour) if entering else colour

        def step(i):
            if i > steps:
                btn.configure(bg=target)
                return
            t = i / steps
            r1, g1, b1 = self._hex_to_rgb(colour)
            r2, g2, b2 = self._hex_to_rgb(self._lighten(colour))
            if not entering:
                r1, g1, b1, r2, g2, b2 = r2, g2, b2, r1, g1, b1
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            try:
                btn.configure(bg=f"#{r:02x}{g:02x}{b:02x}")
                btn.after(delay, lambda: step(i + 1))
            except Exception:
                pass

        step(0)

    @staticmethod
    def _hex_to_rgb(h):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    @staticmethod
    def _lighten(h):
        h = h.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{min(255,r+45):02x}{min(255,g+45):02x}{min(255,b+45):02x}"

    @staticmethod
    def _darken(h):
        h = h.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{max(0,r-30):02x}{max(0,g-30):02x}{max(0,b-30):02x}"

    # ── Key bindings ──────────────────────────────────────────────────────────

    def _bind_keys(self):
        r = self.root
        r.bind("<space>",  lambda e: self._run(self._send(self.atv.remote_control.play_pause(), "⏯ Play/Pause")) if self.atv else None)
        r.bind("n",        lambda e: self._run(self._send(self.atv.remote_control.next(),       "⏭ Next"))       if self.atv else None)
        r.bind("p",        lambda e: self._run(self._send(self.atv.remote_control.previous(),   "⏮ Previous"))   if self.atv else None)
        r.bind("+",        lambda e: self._run(self._send(self.atv.remote_control.volume_up(),  "🔊 Vol Up"))     if self.atv else None)
        r.bind("-",        lambda e: self._run(self._send(self.atv.remote_control.volume_down(),"🔉 Vol Down"))   if self.atv else None)
        r.bind("<Up>",     lambda e: self._run(self._send(self.atv.remote_control.up(),         "⬆ Up"))         if self.atv else None)
        r.bind("<Down>",   lambda e: self._run(self._send(self.atv.remote_control.down(),       "⬇ Down"))       if self.atv else None)
        r.bind("<Left>",   lambda e: self._run(self._send(self.atv.remote_control.left(),       "⬅ Left"))       if self.atv else None)
        r.bind("<Right>",  lambda e: self._run(self._send(self.atv.remote_control.right(),      "➡ Right"))      if self.atv else None)
        r.bind("w",        lambda e: self._run(self._send(self.atv.remote_control.up(),         "⬆ Up"))         if self.atv else None)
        r.bind("s",        lambda e: self._run(self._send(self.atv.remote_control.down(),       "⬇ Down"))       if self.atv else None)
        r.bind("a",        lambda e: self._run(self._send(self.atv.remote_control.left(),       "⬅ Left"))       if self.atv else None)
        r.bind("d",        lambda e: self._run(self._send(self.atv.remote_control.right(),      "➡ Right"))      if self.atv else None)
        r.bind("<Return>", lambda e: self._run(self._send(self.atv.remote_control.select(),     "✅ Select"))     if self.atv else None)
        r.bind("b",        lambda e: self._run(self._send(self.atv.remote_control.menu(),       "◀ Back"))       if self.atv else None)
        r.bind("h",        lambda e: self._run(self._send(self.atv.remote_control.home(),       "🏠 Home"))       if self.atv else None)
        r.bind("q",        lambda e: self._quit())
        r.bind("<Escape>", lambda e: self._quit())
        r.protocol("WM_DELETE_WINDOW", self._quit)
        for key, (name, bundle_id, _) in enumerate(APPS, start=1):
            r.bind(str(key), lambda e, n=name, b=bundle_id: self._run(self._launch(n, b)))

    # ── Actions ───────────────────────────────────────────────────────────────

    def _sleep_atv(self):
        """Put the Apple TV to sleep using the Power interface (turn_off),
        falling back to remote_control.suspend() if power interface unavailable."""
        if not self.atv:
            self._set_status("⚠️ Not connected")
            return
        async def _do_sleep():
            try:
                await self.atv.power.turn_off()
                self._set_status("⏻ Apple TV sleeping…")
            except Exception:
                try:
                    await self.atv.remote_control.suspend()
                    self._set_status("⏻ Apple TV suspended")
                except Exception as e:
                    self._set_status(f"⚠️ Sleep failed: {e}")
        self._run(_do_sleep())

    def _launch_space_invaders(self):
        import sys, os
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "space_invaders.py")
        subprocess.Popen([sys.executable, script])
        self._set_status("🚀 Space Invaders launched!")

    def _quit(self):
        if self.atv:
            self._run(self._async_quit())
        else:
            self.root.destroy()

    async def _async_quit(self):
        try:
            self.atv.close()
        except Exception:
            pass
        self.root.after(0, self.root.destroy)


# ── Entry point ───────────────────────────────────────────────────────────────

# ── iPhone Web Remote ─────────────────────────────────────────────────────────

def _get_local_ip():
    """Return the Mac's LAN IP so the iPhone can reach it."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

IPHONE_PORT = 9876

IPHONE_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>🍎 Apple TV Remote</title>
<style>
  :root {
    --bg: #0d0d1a; --card: #16213e; --accent: #e94560;
    --green: #00b894; --blue: #1e3a8a; --text: #ffffff;
    --sub: #aaaaaa; --btn-r: 16px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
  body {
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", sans-serif;
    min-height: 100dvh; padding: env(safe-area-inset-top,20px) 16px env(safe-area-inset-bottom,20px);
    display: flex; flex-direction: column; align-items: center; gap: 14px;
  }
  h1 { font-size: 1.3em; letter-spacing: .03em; margin-top: 6px; }
  #status { font-size: .8em; color: var(--sub); min-height: 1.2em; text-align:center; }
  #nowplaying { font-size: .85em; color: #ff6666; text-align:center; min-height:1.2em; }

  .card {
    background: var(--card); border-radius: 20px; padding: 14px;
    width: 100%; max-width: 360px; display:flex; flex-direction:column; align-items:center; gap:10px;
  }
  .row { display:flex; gap:10px; justify-content:center; width:100%; }
  button {
    background: var(--blue); color: var(--text); border: none;
    border-radius: var(--btn-r); font-size: 1.1em; font-weight: 700;
    cursor: pointer; user-select: none;
    transition: transform .08s, opacity .08s;
    display:flex; align-items:center; justify-content:center;
  }
  button:active { transform: scale(.92); opacity: .8; }

  /* sizes */
  .btn-sq  { width: 72px; height: 72px; }
  .btn-wide{ flex:1; height: 56px; }
  .btn-full{ width:100%; height: 56px; }

  /* colours */
  .red    { background: var(--accent); }
  .green  { background: var(--green); }
  .dark   { background: #2d3561; }
  .gray   { background: #3a3a4a; }

  /* d-pad */
  .dpad { position:relative; width:200px; height:200px; }
  .dpad button {
    position:absolute; background:var(--blue);
    border-radius: 14px;
  }
  .dpad .up    { top:0;    left:50%; transform:translateX(-50%); width:60px; height:60px; }
  .dpad .down  { bottom:0; left:50%; transform:translateX(-50%); width:60px; height:60px; }
  .dpad .left  { left:0;   top:50%;  transform:translateY(-50%); width:60px; height:60px; }
  .dpad .right { right:0;  top:50%;  transform:translateY(-50%); width:60px; height:60px; }
  .dpad .dpad-up:active    { transform:translateX(-50%) scale(.9); }
  .dpad .dpad-down:active  { transform:translateX(-50%) scale(.9); }
  .dpad .dpad-left:active  { transform:translateY(-50%) scale(.9); }
  .dpad .dpad-right:active { transform:translateY(-50%) scale(.9); }
  .dpad .select {
    position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
    width:72px; height:72px; border-radius:50%; background:#334155; font-size:1.4em;
  }
  .section-label {
    font-size:.7em; text-transform:uppercase; letter-spacing:.08em;
    color:var(--sub); width:100%; text-align:left; padding-left:4px;
  }
  #apps-grid { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; width:100%; }
  #apps-grid button {
    flex: 0 0 calc(25% - 8px); height:48px; font-size:.75em; border-radius:12px;
    padding: 0 4px; text-align:center; word-break:break-word; line-height:1.2;
    background:#1e2d5a;
  }
</style>
</head>
<body>
<h1>🍎 Apple TV Remote</h1>
<div id="status">Loading…</div>
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
  <div class="row">
    <button class="btn-wide gray" onclick="cmd('volume_down')">🔉 Vol−</button>
    <button class="btn-wide gray" onclick="cmd('volume_up')">🔊 Vol+</button>
  </div>
</div>

<!-- D-pad -->
<div class="card">
  <div class="section-label">Navigate</div>
  <div class="dpad">
    <button class="up dpad-up"       onclick="cmd('up')">▲</button>
    <button class="down dpad-down"   onclick="cmd('down')">▼</button>
    <button class="left dpad-left"   onclick="cmd('left')">◀</button>
    <button class="right dpad-right" onclick="cmd('right')">▶</button>
    <button class="select"           onclick="cmd('select')">OK</button>
  </div>
</div>

<!-- System -->
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
</div>

<!-- Apps -->
<div class="card">
  <div class="section-label">Apps</div>
  <div id="apps-grid">
    <button class="btn-wide" style="background:#E50914" onclick="launch('com.netflix.Netflix')">🎬 Netflix</button>
    <button class="btn-wide" style="background:#113CCF" onclick="launch('com.disney.disneyplus')">🏰 Disney+</button>
    <button class="btn-wide" style="background:#00693E" onclick="launch('no.nrk.nrktvapp')">📺 NRK TV</button>
    <button class="btn-wide" style="background:#6A0DAD" onclick="launch('com.wbd.stream')">💜 HBO</button>
    <button class="btn-wide" style="background:#FF0000" onclick="launch('com.google.ios.youtube')">▶️ YouTube</button>
    <button class="btn-wide" style="background:#FF6600" onclick="launch('no.tv2.sumo')">📺 TV 2</button>
  </div>
</div>

<script>
async function cmd(action) {
  try {
    const r = await fetch('/x/do', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({action})
    });
    const d = await r.json();
    document.getElementById('status').textContent = d.status || action;
  } catch(e) { document.getElementById('status').textContent = '⚠️ ' + e; }
}
async function launch(bundle_id) {
  try {
    const r = await fetch('/x/open', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({bundle_id})
    });
    const d = await r.json();
    document.getElementById('status').textContent = d.status || bundle_id;
  } catch(e) { document.getElementById('status').textContent = '⚠️ ' + e; }
}

async function poll() {
  try {
    const r = await fetch('/x/now');
    const d = await r.json();
    document.getElementById('status').textContent = d.connected ? '✅ Connected' : '❌ Not connected';
    document.getElementById('nowplaying').textContent = d.now_playing || '';
  } catch(e) {}
}
poll();
setInterval(poll, 4000);
</script>
</body>
</html>
"""


def start_iphone_server(controller_ref):
    """Start a Flask server in a background thread for iPhone remote control."""
    flask_app = Flask(__name__)

    @flask_app.route("/")
    def index():
        return IPHONE_PAGE

    @flask_app.route("/x/do", methods=["POST"])
    def api_cmd():
        data   = flask_request.get_json(force=True)
        action = data.get("action", "")
        ctrl   = controller_ref[0]

        async def _do():
            rc = ctrl.atv.remote_control
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
            elif action == "sleep":
                try:    await ctrl.atv.power.turn_off()
                except Exception: await rc.suspend()

        if not ctrl or not ctrl.atv:
            return jsonify({"status": "⚠️ Not connected"})
        future = asyncio.run_coroutine_threadsafe(_do(), ctrl.loop)
        try:
            future.result(timeout=5)
            return jsonify({"status": f"✅ {action}"})
        except Exception as e:
            return jsonify({"status": f"❌ {e}"})

    @flask_app.route("/x/open", methods=["POST"])
    def api_launch():
        data      = flask_request.get_json(force=True)
        bundle_id = data.get("bundle_id", "")
        ctrl      = controller_ref[0]
        if not ctrl or not ctrl.atv:
            return jsonify({"status": "⚠️ Not connected"})
        future = asyncio.run_coroutine_threadsafe(
            ctrl.atv.apps.launch_app(bundle_id), ctrl.loop)
        try:
            future.result(timeout=8)
            return jsonify({"status": f"🚀 Launched {bundle_id}"})
        except Exception as e:
            return jsonify({"status": f"❌ {e}"})

    @flask_app.route("/x/now")
    def api_nowplaying():
        ctrl = controller_ref[0]
        if not ctrl or not ctrl.atv:
            return jsonify({"connected": False, "now_playing": ""})
        # Return the last cached value (non-blocking)
        np = ctrl._now_var.get() if hasattr(ctrl, "_now_var") else ""
        return jsonify({"connected": True, "now_playing": np})

    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    threading.Thread(
        target=lambda: flask_app.run(host="0.0.0.0", port=IPHONE_PORT, use_reloader=False),
        daemon=True
    ).start()


if __name__ == "__main__":
    root = tk.Tk()
    ctrl = AppleTVController(root)

    # Start iPhone web remote
    _ref = [ctrl]
    start_iphone_server(_ref)

    ip = _get_local_ip()
    print(f"\n📱 iPhone remote: http://{ip}:{IPHONE_PORT}\n")

    root.mainloop()

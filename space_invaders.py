"""
Space Invaders 🚀
Run on your Mac, AirPlay to Apple TV, control with Apple TV remote.

Apple TV Remote controls:
  Left / Right  — move ship
  OK (centre)   — shoot
  Menu          — pause
  Play/Pause    — pause
"""

import platform
_real = platform.mac_ver
def _patched_mac_ver():
    result = _real()
    return ("15.7.4", result[1], result[2])
platform.mac_ver = _patched_mac_ver

import tkinter as tk
import random
import time

# ── Constants ─────────────────────────────────────────────────────────────────
W, H        = 900, 700
SHIP_SPEED  = 18
BULLET_SPD  = 14
ALIEN_COLS  = 11
ALIEN_ROWS  = 5
ALIEN_W, ALIEN_H = 44, 32
ALIEN_GAP_X = 60
ALIEN_GAP_Y = 52
ALIEN_START_X = 60
ALIEN_START_Y = 80
ALIEN_DROP  = 20
ALIEN_SPEED_START = 1.2
BOMB_SPEED  = 6
BOMB_CHANCE = 0.003   # per alien per frame

BG_COL      = "#000000"
SHIP_COL    = "#00ff88"
BULLET_COL  = "#ffffff"
ALIEN_COLS_COLOURS = ["#ff4444", "#ff9900", "#ffff00", "#00ccff", "#cc44ff"]
BOMB_COL    = "#ff4444"
BARRIER_COL = "#00cc44"
HUD_COL     = "#00ff88"


class SpaceInvaders:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("🚀 Space Invaders")
        root.configure(bg=BG_COL)
        root.resizable(False, False)

        self.canvas = tk.Canvas(root, width=W, height=H, bg=BG_COL,
                                highlightthickness=0)
        self.canvas.pack()

        self._reset()
        self._bind_keys()
        root.after(50, self._loop)

    # ── Game state ────────────────────────────────────────────────────────────

    def _reset(self):
        self.ship_x     = W // 2
        self.ship_y     = H - 60
        self.bullets    = []   # list of [x, y]
        self.bombs      = []   # list of [x, y]
        self.aliens     = self._make_aliens()
        self.alien_dx   = ALIEN_SPEED_START
        self.score      = 0
        self.lives      = 3
        self.paused     = False
        self.game_over  = False
        self.won        = False
        self.barriers   = self._make_barriers()
        self.move_left  = False
        self.move_right = False
        self.shoot_held = False
        self.last_shot  = 0
        self.frame      = 0
        self.level      = 1

    def _make_aliens(self):
        aliens = []
        for row in range(ALIEN_ROWS):
            for col in range(ALIEN_COLS):
                x = ALIEN_START_X + col * ALIEN_GAP_X
                y = ALIEN_START_Y + row * ALIEN_GAP_Y
                colour = ALIEN_COLS_COLOURS[row % len(ALIEN_COLS_COLOURS)]
                aliens.append([x, y, colour, True])  # x, y, colour, alive
        return aliens

    def _make_barriers(self):
        barriers = []
        for i in range(4):
            bx = 120 + i * 200
            by = H - 140
            # each barrier = list of block [x,y,alive]
            for brow in range(4):
                for bcol in range(6):
                    barriers.append([bx + bcol*14, by + brow*10, True])
        return barriers

    # ── Input ─────────────────────────────────────────────────────────────────

    def _bind_keys(self):
        r = self.root
        # Arrow keys + WASD (Apple TV remote sends arrow key events over Bluetooth)
        r.bind("<Left>",       lambda e: setattr(self, "move_left",  True))
        r.bind("<Right>",      lambda e: setattr(self, "move_right", True))
        r.bind("<KeyRelease-Left>",  lambda e: setattr(self, "move_left",  False))
        r.bind("<KeyRelease-Right>", lambda e: setattr(self, "move_right", False))
        r.bind("a",            lambda e: setattr(self, "move_left",  True))
        r.bind("d",            lambda e: setattr(self, "move_right", True))
        r.bind("<KeyRelease-a>", lambda e: setattr(self, "move_left",  False))
        r.bind("<KeyRelease-d>", lambda e: setattr(self, "move_right", False))
        # Shoot — OK button on remote / space / up / return
        r.bind("<space>",      lambda e: self._shoot())
        r.bind("<Return>",     lambda e: self._shoot())
        r.bind("<Up>",         lambda e: self._shoot())
        r.bind("w",            lambda e: self._shoot())
        # Pause — Menu button on remote / P / Escape
        r.bind("p",            lambda e: self._toggle_pause())
        r.bind("<Escape>",     lambda e: self._toggle_pause())
        # Restart
        r.bind("r",            lambda e: self._restart())

    def _shoot(self):
        if self.game_over or self.paused:
            if self.game_over:
                self._restart()
            return
        now = time.time()
        if now - self.last_shot > 0.35:   # max ~3 shots/sec
            self.bullets.append([self.ship_x, self.ship_y - 20])
            self.last_shot = now

    def _toggle_pause(self):
        if self.game_over:
            self._restart()
            return
        self.paused = not self.paused

    def _restart(self):
        self._reset()

    # ── Game loop ─────────────────────────────────────────────────────────────

    def _loop(self):
        if not self.paused and not self.game_over:
            self._update()
        self._draw()
        self.root.after(16, self._loop)   # ~60 fps

    def _update(self):
        self.frame += 1

        # Move ship
        if self.move_left:
            self.ship_x = max(30, self.ship_x - SHIP_SPEED)
        if self.move_right:
            self.ship_x = min(W - 30, self.ship_x + SHIP_SPEED)

        # Move bullets
        self.bullets = [[x, y - BULLET_SPD] for x, y in self.bullets if y > 0]

        # Move bombs
        self.bombs = [[x, y + BOMB_SPEED] for x, y in self.bombs if y < H]

        # Move aliens
        alive = [a for a in self.aliens if a[3]]
        if not alive:
            self._next_level()
            return

        edge_hit = False
        for a in alive:
            a[0] += self.alien_dx
            if a[0] > W - 30 or a[0] < 20:
                edge_hit = True

        if edge_hit:
            self.alien_dx *= -1
            for a in alive:
                a[1] += ALIEN_DROP

        # Aliens drop bombs randomly
        for a in alive:
            if random.random() < BOMB_CHANCE * (1 + self.level * 0.3):
                self.bombs.append([a[0], a[1] + 16])

        # Bullet hits alien
        for bullet in self.bullets[:]:
            bx, by = bullet
            for alien in self.aliens:
                ax, ay, col, alive_flag = alien
                if alive_flag and abs(bx - ax) < ALIEN_W//2 and abs(by - ay) < ALIEN_H//2:
                    alien[3] = False
                    self.bullets.remove(bullet)
                    self.score += 10
                    break

        # Bullet hits barrier
        for bullet in self.bullets[:]:
            bx, by = bullet
            for bar in self.barriers:
                if bar[2] and abs(bx - bar[0]) < 8 and abs(by - bar[1]) < 6:
                    bar[2] = False
                    if bullet in self.bullets:
                        self.bullets.remove(bullet)
                    break

        # Bomb hits ship
        for bomb in self.bombs[:]:
            bx, by = bomb
            if abs(bx - self.ship_x) < 20 and abs(by - self.ship_y) < 20:
                self.bombs.remove(bomb)
                self.lives -= 1
                if self.lives <= 0:
                    self.game_over = True
                    self.won = False

        # Bomb hits barrier
        for bomb in self.bombs[:]:
            bx, by = bomb
            for bar in self.barriers:
                if bar[2] and abs(bx - bar[0]) < 8 and abs(by - bar[1]) < 6:
                    bar[2] = False
                    if bomb in self.bombs:
                        self.bombs.remove(bomb)
                    break

        # Aliens reach bottom
        for a in self.aliens:
            if a[3] and a[1] > H - 80:
                self.game_over = True
                self.won = False

    def _next_level(self):
        self.level += 1
        self.aliens   = self._make_aliens()
        self.barriers = self._make_barriers()
        self.bullets  = []
        self.bombs    = []
        self.alien_dx = ALIEN_SPEED_START + self.level * 0.4

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self):
        c = self.canvas
        c.delete("all")

        # Starfield (static seed for performance)
        random.seed(42)
        for _ in range(80):
            sx = random.randint(0, W)
            sy = random.randint(0, H)
            br = random.randint(100, 255)
            col = f"#{br:02x}{br:02x}{br:02x}"
            c.create_oval(sx, sy, sx+1, sy+1, fill=col, outline="")
        random.seed()

        # Barriers
        for bar in self.barriers:
            if bar[2]:
                c.create_rectangle(bar[0]-6, bar[1]-4, bar[0]+6, bar[1]+5,
                                   fill=BARRIER_COL, outline="")

        # Aliens
        for ax, ay, col, alive in self.aliens:
            if not alive:
                continue
            # Body
            c.create_rectangle(ax-16, ay-10, ax+16, ay+10, fill=col, outline="")
            # Eyes
            c.create_rectangle(ax-8, ay-5, ax-3, ay+2,  fill=BG_COL, outline="")
            c.create_rectangle(ax+3, ay-5, ax+8, ay+2,  fill=BG_COL, outline="")
            # Antennae
            c.create_line(ax-10, ay-10, ax-14, ay-18, fill=col, width=2)
            c.create_line(ax+10, ay-10, ax+14, ay-18, fill=col, width=2)
            # Legs
            c.create_line(ax-16, ay+10, ax-20, ay+18, fill=col, width=2)
            c.create_line(ax+16, ay+10, ax+20, ay+18, fill=col, width=2)

        # Ship
        sx, sy = self.ship_x, self.ship_y
        c.create_polygon(
            sx, sy-22,
            sx-22, sy+14,
            sx-10, sy+8,
            sx+10, sy+8,
            sx+22, sy+14,
            fill=SHIP_COL, outline="#00ff44",
        )
        # Engine glow
        c.create_oval(sx-6, sy+10, sx+6, sy+20, fill="#ff8800", outline="")

        # Bullets
        for bx, by in self.bullets:
            c.create_rectangle(bx-3, by-10, bx+3, by+2,
                                fill=BULLET_COL, outline="")

        # Bombs
        for bx, by in self.bombs:
            c.create_oval(bx-5, by-5, bx+5, by+5, fill=BOMB_COL, outline="")

        # HUD
        c.create_text(20, 20, text=f"SCORE  {self.score:05d}",
                      fill=HUD_COL, font=("Courier", 20, "bold"), anchor="nw")
        c.create_text(W//2, 20, text=f"LEVEL  {self.level}",
                      fill=HUD_COL, font=("Courier", 20, "bold"), anchor="n")
        lives_txt = "♥ " * self.lives
        c.create_text(W-20, 20, text=lives_txt,
                      fill="#ff4444", font=("Courier", 20, "bold"), anchor="ne")

        # Ground line
        c.create_line(0, H-30, W, H-30, fill="#003300", width=2)

        # Overlays
        if self.paused:
            self._overlay(c, "⏸  PAUSED", "Press P or Menu to continue")
        elif self.game_over and not self.won:
            self._overlay(c, "💀  GAME OVER",
                          f"Score: {self.score}   Press R or OK to restart")
        elif self.game_over and self.won:
            self._overlay(c, "🎉  YOU WIN!",
                          f"Score: {self.score}   Press R or OK to play again")

    def _overlay(self, c, title, subtitle):
        c.create_rectangle(W//2-300, H//2-80, W//2+300, H//2+80,
                           fill="#000000", outline=HUD_COL, width=3)
        c.create_text(W//2, H//2-25, text=title,
                      fill=HUD_COL, font=("Courier", 36, "bold"))
        c.create_text(W//2, H//2+30, text=subtitle,
                      fill="#aaaaaa", font=("Courier", 16))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.resizable(False, False)
    SpaceInvaders(root)
    root.mainloop()

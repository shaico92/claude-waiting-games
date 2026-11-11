#!/usr/bin/env python3
"""Knight vs Devils - a small terminal brawler to play while Claude Code works.

Move: A/D or Left/Right   Jump: W / Up / Space   Sword: J or F
Shield: K or S / Down     Pause: P               Quit: Q
"""
import curses, os, random, subprocess, sys, time

HOME = os.path.dirname(os.path.abspath(__file__))
SCORE_FILE = os.path.join(HOME, "highscore")
STATE = sys.argv[1] if len(sys.argv) > 1 else None        # file written by the hooks
CLAUDE_PANE = sys.argv[2] if len(sys.argv) > 2 else None  # tmux pane running Claude
FPS = 30
DT = 1.0 / FPS
KW, KH, MAX_HP = 3, 3, 5

KINDS = {
    "imp":   dict(w=3, h=2, hp=1, speed=11.0, dmg=1, windup=0.40, score=10, col=1,
                  walk=["'o'", "/^\\"], wind=["\\o/", " ^ "]),
    "devil": dict(w=3, h=3, hp=2, speed=7.0, dmg=1, windup=0.55, score=25, col=1,
                  walk=["^o^", "/W\\", "/ \\"], wind=["^o^", "\\W/", "/ \\"]),
    "brute": dict(w=5, h=4, hp=5, speed=4.0, dmg=2, windup=0.85, score=80, col=5,
                  walk=[" ^_^ ", "(o_o)", "/[W]\\", " / \\ "],
                  wind=["\\^_^/", "(o_o)", " [W] ", " / \\ "]),
}


def load_high():
    try:
        return int(open(SCORE_FILE).read().strip())
    except Exception:
        return 0


def save_high(n):
    try:
        open(SCORE_FILE, "w").write(str(n))
    except Exception:
        pass


def read_state():
    """Returns (mtime, text) of the hook state file, or None."""
    if not STATE:
        return None
    try:
        return (os.stat(STATE).st_mtime_ns, open(STATE).read().strip())
    except Exception:
        return None


class Game:
    def __init__(self, w):
        self.w = w
        self.x, self.y, self.vy = w / 2.0, 0.0, 0.0
        self.face = 1
        self.hp = MAX_HP
        self.invuln = 0.0
        self.atk_t = 0.0      # sword visible
        self.atk_cd = 0.0
        self.enemies, self.fire, self.hearts, self.sparks = [], [], [], []
        self.score = 0
        self.wave = 0
        self.queue = []
        self.spawn_t = 0.0
        self.inter = 2.0      # pause between waves
        self.dead = False

    # ---------- helpers
    def gap(self, e):
        """(horizontal gap between knight and enemy, side of enemy: +1 right / -1 left)"""
        if e["x"] + e["w"] / 2.0 >= self.x + KW / 2.0:
            return e["x"] - (self.x + KW), 1
        return self.x - (e["x"] + e["w"]), -1

    def hurt(self, dmg, away):
        if self.invuln > 0 or self.dead:
            return
        self.hp -= dmg
        self.invuln = 1.0
        self.x = min(max(0.0, self.x + away * 3), self.w - KW - 1)
        if self.hp <= 0:
            self.hp, self.dead = 0, True

    def next_wave(self):
        self.wave += 1
        pool = ["imp"] * 4
        if self.wave >= 2:
            pool += ["devil"] * (2 + self.wave)
        if self.wave >= 4:
            pool += ["brute"] * (self.wave - 3)
        self.queue = [random.choice(pool) for _ in range(2 + self.wave)]
        if self.wave >= 4 and self.wave % 2 == 0:
            self.queue.append("brute")
        self.spawn_t = 0.5

    def spawn(self, kind):
        k = KINDS[kind]
        side = random.choice([-1, 1])
        x = -k["w"] if side < 0 else self.w
        self.enemies.append(dict(kind=kind, x=float(x), w=k["w"], hp=k["hp"], state="walk",
                                 t=0.0, flash=0.0, fire_cd=random.uniform(1.5, 4.0)))

    def swing(self):
        if self.atk_cd > 0 or self.dead:
            return
        self.atk_cd, self.atk_t = 0.35, 0.18
        lo, hi = (self.x + 1, self.x + KW + 4) if self.face > 0 else (self.x - 4, self.x + KW - 1)
        for e in self.enemies:
            if e["x"] < hi and e["x"] + e["w"] > lo:
                e["hp"] -= 1
                e["flash"] = 0.15
                brute = e["kind"] == "brute"
                e["x"] += self.face * (1 if brute else 3)
                if not brute:
                    e["state"], e["t"] = "stun", 0.3
                self.sparks.append([e["x"] + e["w"] / 2.0, 1.5, 0.15, "*"])
        for f in self.fire:  # sword can also swat fireballs
            if lo <= f[0] <= hi and self.y < 2:
                f[2] = 0

    # ---------- one simulation step
    def step(self, mv, blocking):
        if self.dead:
            return
        self.invuln = max(0.0, self.invuln - DT)
        self.atk_t = max(0.0, self.atk_t - DT)
        self.atk_cd = max(0.0, self.atk_cd - DT)
        if mv and not blocking:
            self.face = mv
            self.x += mv * 18.0 * DT
        self.x = min(max(0.0, self.x), self.w - KW - 1)
        self.y += self.vy * DT
        self.vy -= 40.0 * DT
        if self.y <= 0:
            self.y, self.vy = 0.0, 0.0

        # waves
        if not self.queue and not self.enemies:
            self.inter -= DT
            if self.inter <= 0:
                self.next_wave()
                self.inter = 2.5
        elif self.queue:
            self.spawn_t -= DT
            if self.spawn_t <= 0 and len(self.enemies) < min(2 + self.wave // 2, 6):
                self.spawn(self.queue.pop())
                self.spawn_t = random.uniform(0.8, 2.2)

        # enemies
        for e in self.enemies:
            k = KINDS[e["kind"]]
            e["flash"] = max(0.0, e["flash"] - DT)
            e["fire_cd"] -= DT
            g, side = self.gap(e)
            if e["state"] == "walk":
                if g > 1.5:
                    e["x"] -= side * k["speed"] * DT
                    if e["kind"] == "devil" and g > 12 and e["fire_cd"] <= 0 and 0 <= e["x"] <= self.w - 4:
                        e["fire_cd"] = random.uniform(3.0, 6.0)
                        self.fire.append([e["x"] + (0 if side > 0 else e["w"]), -side * 22.0, 1])
                else:
                    e["state"], e["t"] = "windup", k["windup"]
            else:
                e["t"] -= DT
                if e["t"] <= 0:
                    if e["state"] == "windup":
                        if g <= 3 and self.y < 2:
                            if blocking and self.face == side:
                                e["state"], e["t"] = "stun", 0.8
                                e["x"] += side * 2
                                self.sparks.append([self.x + (KW if side > 0 else -1), 1.5, 0.2, "+"])
                            else:
                                self.hurt(k["dmg"], -side)
                                e["state"], e["t"] = "cool", 0.9
                        else:
                            e["state"], e["t"] = "cool", 0.5
                    else:
                        e["state"] = "walk"
        alive = []
        for e in self.enemies:
            if e["hp"] > 0:
                alive.append(e)
            else:
                self.score += KINDS[e["kind"]]["score"]
                if random.random() < 0.18 and self.hp < MAX_HP:
                    self.hearts.append([min(max(1.0, e["x"] + 1), self.w - 3), 8.0])
        self.enemies = alive

        # fireballs: [x, vx, alive]
        for f in self.fire:
            f[0] += f[1] * DT
            if f[2] and self.x - 0.5 <= f[0] <= self.x + KW - 0.5 and self.y < 1:
                from_side = -1 if f[1] > 0 else 1   # side it arrives from
                if blocking and self.face == from_side:
                    self.sparks.append([f[0], 0.5, 0.2, "+"])
                else:
                    self.hurt(1, -from_side)
                f[2] = 0
        self.fire = [f for f in self.fire if f[2] and -2 < f[0] < self.w + 2]

        # hearts: [x, ttl]
        for h in self.hearts:
            h[1] -= DT
            if self.x - 1 <= h[0] <= self.x + KW and self.y < 1:
                self.hp = min(MAX_HP, self.hp + 1)
                h[1] = 0
        self.hearts = [h for h in self.hearts if h[1] > 0]
        for s in self.sparks:
            s[2] -= DT
        self.sparks = [s for s in self.sparks if s[2] > 0]


def put(win, y, x, s, attr=0):
    h, w = win.getmaxyx()
    x = int(x)
    if x < 0:
        s, x = s[-x:], 0
    if 0 <= y < h and x < w - 1 and s:
        try:
            win.addstr(y, x, s[: w - 1 - x], attr)
        except curses.error:
            pass


def put_sprite(win, ground, x, y, rows, attr=0):
    """Draw rows so the last one sits `y` cells above the ground; spaces are transparent."""
    base = ground - int(round(y))
    for i, row in enumerate(rows):
        yy = base - (len(rows) - 1 - i)
        for j, ch in enumerate(row):
            if ch != " ":
                put(win, yy, int(round(x)) + j, ch, attr)


def knight_rows(g, blocking):
    """Returns (rows, x offset)."""
    r = g.face > 0
    if g.dead:
        return ["   ", "   ", "_o_"], 0
    if g.atk_t > 0:
        return ([" O    ", "/|===>", "/ \\   "], 0) if r else (["    O ", "<===|\\", "   / \\"], -3)
    if blocking:
        return ([" O ", "/|]", "/ \\"], 0) if r else ([" O ", "[|\\", "/ \\"], 0)
    return ([" O ", "/|/", "/ \\"], 0) if r else ([" O ", "\\|\\", "/ \\"], 0)


def main(scr):
    curses.curs_set(0)
    scr.nodelay(True)
    scr.keypad(True)
    col = lambda n: 0
    if curses.has_colors():
        curses.start_color()
        try:
            curses.use_default_colors()
            bg = -1
        except curses.error:
            bg = curses.COLOR_BLACK
        for i, c in enumerate([curses.COLOR_RED, curses.COLOR_CYAN, curses.COLOR_YELLOW,
                               curses.COLOR_GREEN, curses.COLOR_MAGENTA], 1):
            curses.init_pair(i, c, bg)
        col = curses.color_pair

    high = load_high()
    h, w = scr.getmaxyx()
    g = Game(w)
    paused = False
    banner = None            # None | "done" | "notify"
    seen = read_state()
    if seen and seen[1] in ("done", "notify"):
        banner = seen[1]
    last_key = {}
    move_until = {-1: 0.0, 1: 0.0}
    block_until = 0.0
    frame = 0

    def held(key, now, first, repeat):
        """Terminals send no key-up events, so emulate holding via key repeat."""
        d = repeat if now - last_key.get(key, 0) < 0.6 else first
        last_key[key] = now
        return now + d

    while True:
        t0 = time.time()
        if not (paused or banner):
            frame += 1
        h, w = scr.getmaxyx()
        g.w = w
        ground = h - 2

        st = read_state()
        if st != seen:
            seen = st
            if st and st[1] in ("done", "notify"):
                banner = st[1]
            elif st and st[1] == "run":
                banner, paused = None, False

        while True:
            k = scr.getch()
            if k == -1:
                break
            now = time.time()
            if k in (ord("q"), ord("Q")):
                return
            if banner:
                if k in (10, 13, curses.KEY_ENTER):
                    banner, paused = None, True
                    if CLAUDE_PANE:
                        subprocess.call(["tmux", "select-pane", "-t", CLAUDE_PANE])
                elif k in (ord("p"), ord("P")):
                    banner, paused = None, False
                continue
            if k in (ord("p"), ord("P")):
                paused = not paused
                continue
            if paused:
                if k in (ord(" "), 10, 13):
                    paused = False
                continue
            if g.dead:
                if k in (ord(" "), 10, 13):
                    g = Game(w)
                continue
            if k in (ord("a"), ord("A"), curses.KEY_LEFT):
                move_until[-1], move_until[1] = held("L", now, 0.22, 0.14), 0.0
            elif k in (ord("d"), ord("D"), curses.KEY_RIGHT):
                move_until[1], move_until[-1] = held("R", now, 0.22, 0.14), 0.0
            elif k in (ord("w"), ord("W"), ord(" "), curses.KEY_UP):
                if g.y == 0:
                    g.vy = 14.0
            elif k in (ord("j"), ord("J"), ord("f"), ord("F")):
                block_until = 0.0
                g.swing()
            elif k in (ord("k"), ord("K"), ord("s"), ord("S"), curses.KEY_DOWN):
                block_until = held("B", now, 0.5, 0.16)

        now = time.time()
        blocking = now < block_until and g.atk_t <= 0 and not g.dead
        if h < 10 or w < 50:
            scr.erase()
            put(scr, 0, 0, "Make this pane bigger (50x10 min)")
            scr.refresh()
            time.sleep(0.1)
            continue
        if not (paused or banner):
            mv = 1 if now < move_until[1] else (-1 if now < move_until[-1] else 0)
            was_dead = g.dead
            g.step(mv, blocking)
            if g.dead and not was_dead and g.score > high:
                high = g.score
                save_high(high)

        # ---------- draw
        scr.erase()
        put(scr, 0, 1, "HP ")
        put(scr, 0, 4, "#" * g.hp, col(1) | curses.A_BOLD)
        put(scr, 0, 4 + g.hp, "." * (MAX_HP - g.hp))
        put(scr, 0, 12, "wave %d   score %d   best %d" % (g.wave, g.score, max(high, g.score)))
        put(scr, ground + 1, 0, "=" * (w - 1), col(4))
        for hx, ttl in g.hearts:
            if ttl > 2 or frame % 6 < 3:
                put(scr, ground, hx, "<3", col(1) | curses.A_BOLD)
        for f in g.fire:
            put(scr, ground, f[0], "@" if frame % 4 < 2 else "*", col(3) | curses.A_BOLD)
        for e in g.enemies:
            k = KINDS[e["kind"]]
            rows = k["wind"] if e["state"] == "windup" else k["walk"]
            attr = curses.A_REVERSE if e["flash"] > 0 else col(k["col"]) | curses.A_BOLD
            put_sprite(scr, ground, e["x"], 0, rows, attr)
            top = ground - k["h"]
            if e["state"] == "windup":
                put(scr, top, e["x"] + e["w"] // 2, "!", col(3) | curses.A_BOLD)
            elif e["state"] == "stun":
                put(scr, top, e["x"] + e["w"] // 2, "~", col(3))
        if g.invuln <= 0 or frame % 4 < 2 or g.dead:
            rows, off = knight_rows(g, blocking)
            put_sprite(scr, ground, g.x + off, g.y, rows, col(2) | curses.A_BOLD)
        for sx, sy, _, ch in g.sparks:
            put(scr, ground - int(sy), sx, ch, col(3) | curses.A_BOLD)

        msg = None
        if banner == "done":
            msg = " PAUSED - Claude is waiting for your prompt.  Enter = go to Claude "
        elif banner == "notify":
            msg = " PAUSED - Claude needs you!  Enter = go to Claude "
        elif g.dead:
            msg = " YOU DIED - space to fight again, q to quit "
        elif paused:
            msg = " paused - space to resume "
        elif g.inter < 2.5 and not g.enemies and not g.queue:
            msg = " Wave %d incoming... " % (g.wave + 1)
        if msg:
            put(scr, max(1, h // 2 - 2), max(0, (w - len(msg)) // 2), msg, curses.A_REVERSE)
        if not banner:
            tip = "A/D move  W jump  J sword  K shield  P pause  Q quit"
            put(scr, 1, max(0, w - len(tip) - 2), tip, curses.A_DIM)
        scr.refresh()
        time.sleep(max(0, DT - (time.time() - t0)))


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass

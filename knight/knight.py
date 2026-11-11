#!/usr/bin/env python3
"""Knight vs Devils - a small terminal brawler to play while Claude Code works.

Move: A/D or Left/Right   Jump: W / Up / Space   Sword: J or F
Shield: K or S / Down     Pause: P               Quit: Q
Powers (cost mana):  Dash: U or E (1)   Sword beam: I or R (2)   Spin: L or G (3)
"""
import os, random, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import (curses, STATE, CLAUDE_PANE, ALIVE, read_state, heartbeat,  # noqa: E402
                    focus_claude, is_menu_key, pick_game, run)

HOME = os.path.dirname(os.path.abspath(__file__))
# kept outside the plugin folder, which is replaced on every plugin update
SCORE_FILE = os.path.join(os.path.expanduser("~"), ".claude", "knight-game", "highscore")
STATE = sys.argv[1] if len(sys.argv) > 1 else None        # file written by the hooks
CLAUDE_PANE = sys.argv[2] if len(sys.argv) > 2 else None  # tmux pane id, "wt" or "window"
ALIVE = STATE + ".alive" if STATE else None               # heartbeat the Windows hook checks
FPS = 30
DT = 1.0 / FPS
KW, KH, MAX_HP = 3, 3, 5
HEARTS_PER_WAVE = 2
# movement (cells / s, cells / s^2): accelerate to RUN, glide to a stop
RUN, ACCEL, TURN, FRICTION = 17.0, 110.0, 180.0, 60.0
# mana and powers
MAX_MP, MP_REGEN, MP_PER_KILL = 6, 2.5, 1       # MP_REGEN = seconds per point
DASH_COST, BEAM_COST, SPIN_COST = 1, 2, 3
DASH_TIME, DASH_SPEED = 0.18, 48.0
BEAM_SPEED, SPIN_RANGE = 30.0, 5.0
SWORD_REACH = 4
JUMP_V, GRAVITY = 14.0, 40.0
JUMP_TOP = JUMP_V ** 2 / (2 * GRAVITY)   # air-stab bounces never go higher than a jump
# combat
PARRY_WINDOW = 0.2   # shield pressed this soon before a hit lands = parry
COMBO_TIME = 2.5     # a kill within this many seconds of the last one keeps the combo
SPACING = 1.0        # cells enemies keep between each other when lining up
BOSS_EVERY = 5       # every 5th wave is a boss wave
# Smallest playable pane: HUD row + jump apex (knight top = ground-4) + ground line.
# A 40% Windows Terminal split of a non-maximized window is often only 8-9 rows.
MIN_W, MIN_H = 36, 7

# heavy: can't be staggered   fly: hovers at `alt`, the ground sword can't reach it
# guard: its shield stops sword and beam unless it is stunned   bomb: explodes at you
KINDS = {
    "imp":    dict(w=3, h=2, hp=1, speed=11.0, dmg=1, windup=0.40, score=10, col=1,
                   walk=["'o'", "/^\\"], wind=["\\o/", " ^ "]),
    "devil":  dict(w=3, h=3, hp=2, speed=7.0, dmg=1, windup=0.55, score=25, col=1,
                   walk=["^o^", "/W\\", "/ \\"], wind=["^o^", "\\W/", "/ \\"]),
    "brute":  dict(w=5, h=4, hp=5, speed=4.0, dmg=2, windup=0.85, score=80, col=5, heavy=True,
                   walk=[" ^_^ ", "(o_o)", "/[W]\\", " / \\ "],
                   wind=["\\^_^/", "(o_o)", " [W] ", " / \\ "]),
    "bat":    dict(w=3, h=1, hp=1, speed=9.0, dmg=1, windup=0.45, score=15, col=5, fly=True, alt=2,
                   walk=["/v\\"], walk2=["\\v/"], wind=["-v-"]),
    "guard":  dict(w=3, h=3, hp=2, speed=6.0, dmg=1, windup=0.60, score=35, col=1, guard=True,
                   walk=["^o^", "[W\\", "/ \\"], wind=["^o^", "[W/", "/ \\"],
                   open=["^o^", "/W\\", "/ \\"]),
    "bomber": dict(w=3, h=2, hp=1, speed=8.0, dmg=2, windup=1.0, score=20, col=3, bomb=True,
                   walk=["(*)", "/ \\"], wind=["(@)", "/ \\"]),
    "boss":   dict(w=7, h=5, hp=20, speed=3.5, dmg=2, windup=0.8, score=500, col=5,
                   heavy=True, boss=True,
                   walk=["  ^ ^  ", " (O O) ", "/[###]\\", " [###] ", " /   \\ "],
                   wind=["\\ ^ ^ /", " (O O) ", " [###] ", " [###] ", " /   \\ "],
                   charge=["  ^ ^  ", " (>_<) ", "=[###]=", " [###] ", " /   \\ "]),
}

# perk: (label, still worth offering?)
PERKS = {
    "hp":    ("+1 max HP",    lambda g: g.max_hp < 8),
    "heal":  ("Full heal",    lambda g: g.hp < g.max_hp),
    "reach": ("Longer sword", lambda g: g.reach < 8),
    "mana":  ("+2 max MP",    lambda g: g.max_mp < 10),
    "regen": ("Faster mana",  lambda g: g.regen > 1.2),
    "dash":  ("Free dash",    lambda g: g.dash_cost > 0),
    "beam":  ("Beam hits x2", lambda g: g.beam_dmg < 2),
    "spin":  ("Wider spin",   lambda g: g.spin_range < 9),
}

# the H screen: (text, color pair, is a heading). Lines fit a 36-column pane.
HELP = [
    ("CONTROLS", 0, True),
    ("A/D move    W jump    P pause", 0, False),
    ("J sword     K shield (hold it)", 0, False),
    ("W then J    stab down, bounces", 2, False),
    ("tap K just before a hit: PARRY", 2, False),
    ("  stuns, +1 MP, fireballs fly back", 0, False),
    ("U dash 1MP  I beam 2MP  L spin 3MP", 2, False),
    ("COMBO  kills <2.5s apart: x2-x4", 3, False),
    ("PERKS  1/2/3 after each wave", 3, False),
    ("M or Tab   switch to another game", 0, False),
    ("ENEMIES", 0, True),
    ("'o'   imp     fast, 1 hit", 1, False),
    ("^o^   devil   throws fireballs", 1, False),
    ("/v\\   bat     flies: W+J, I or L", 5, False),
    ("(*)   bomber  lit fuse: run!", 3, False),
    ("[W\\   guard   K or parry, then J", 1, False),
    ("(O O) boss    every 5th wave", 5, False),
    ("!  attack coming    !! big one", 3, False),
    ("~  stunned: hit it now", 3, False),
]


def load_high():
    try:
        return int(open(SCORE_FILE).read().strip())
    except Exception:
        return 0


def save_high(n):
    try:
        os.makedirs(os.path.dirname(SCORE_FILE), exist_ok=True)
        open(SCORE_FILE, "w").write(str(n))
    except Exception:
        pass


class Game:
    def __init__(self, w):
        self.w = w
        self.x, self.y, self.vx, self.vy = w / 2.0, 0.0, 0.0, 0.0
        self.face = 1
        # stats that perks raise
        self.max_hp, self.max_mp, self.regen = MAX_HP, MAX_MP, MP_REGEN
        self.reach, self.dash_cost, self.beam_dmg, self.spin_range = SWORD_REACH, DASH_COST, 1, SPIN_RANGE
        self.hp = self.max_hp
        self.mp, self.mp_t = self.max_mp, 0.0
        self.mp_flash = 0.0   # MP bar blinks when a power is too expensive
        self.invuln = 0.0
        self.atk_t = 0.0      # sword visible
        self.atk_cd = 0.0
        self.stab_t = 0.0     # downward air stab visible
        self.parry_t = 0.0    # > 0 just after a fresh shield press
        self.dash_t, self.dash_dir, self.dash_hit = 0.0, 1, set()
        self.spin_t = 0.0     # spin pose visible
        self.enemies, self.hearts, self.sparks = [], [], []
        self.fire = []        # [x, vx, alive, reflected by a parry]
        self.beams = []       # [x, vx, alive, ids of enemies already hit]
        self.heart_drops, self.kills_left = 0, 0
        self.score = 0
        self.combo, self.combo_t, self.best_combo = 0, 0.0, 0
        self.freeze = 0.0     # hit-stop: the world holds still for a few frames
        self.shake = 0.0      # screen shake
        self.wave = 0
        self.queue = []
        self.spawn_t = 0.0
        self.inter = 2.0      # pause between waves
        self.cleared = True   # this wave's clear-up (perk offer) already happened
        self.clear_t = 0.0    # "WAVE CLEAR" shown
        self.offer, self.perks = None, []
        self.dead, self.death_t = False, 0.0

    # ---------- helpers
    def gap(self, e):
        """(horizontal gap between knight and enemy, side of enemy: +1 right / -1 left)"""
        if e["x"] + e["w"] / 2.0 >= self.x + KW / 2.0:
            return e["x"] - (self.x + KW), 1
        return self.x - (e["x"] + e["w"]), -1

    def mult(self):
        """Score multiplier from the combo: 2 kills x2, 4 kills x3, 6+ kills x4."""
        return min(4, 1 + self.combo // 2)

    def popup(self, x, y, text, ttl=0.6):
        self.sparks.append([x - len(text) / 2.0, y, ttl, text])

    def burst(self, x, n, spread, chars="*+"):
        for _ in range(n):
            self.sparks.append([x + random.uniform(-spread, spread), random.uniform(0, 3),
                                random.uniform(0.25, 0.7), random.choice(chars)])

    def hurt(self, dmg, away):
        if self.invuln > 0 or self.dead:
            return False
        self.hp -= dmg
        self.invuln = 1.0
        self.vx = 0.0
        self.x = min(max(0.0, self.x + away * 3), self.w - KW - 1)
        self.combo, self.combo_t = 0, 0.0
        self.freeze = max(self.freeze, 0.08)
        if dmg >= 2:
            self.shake = max(self.shake, 0.3)
        if self.hp <= 0:
            self.hp, self.dead = 0, True
            self.burst(self.x + 1, 8, 3, "*+x")
        return True

    def next_wave(self):
        self.wave += 1
        w = self.wave
        pool = ["imp"] * 4
        if w >= 2:
            pool += ["devil"] * (2 + w)
        if w >= 3:
            pool += ["bat"] * (1 + w // 3)
        if w >= 4:
            pool += ["brute"] * (w - 3) + ["bomber"] * 2
        if w >= 6:
            pool += ["guard"] * (w - 5)
        if w % BOSS_EVERY == 0:
            # queue.pop() takes from the end: the boss comes first, helpers after
            self.queue = [random.choice(pool) for _ in range(1 + w // BOSS_EVERY)] + ["boss"]
        else:
            self.queue = [random.choice(pool) for _ in range(2 + w)]
            if w >= 4 and w % 2 == 0:
                self.queue.append("brute")
        self.spawn_t = 0.5
        self.cleared = False
        # exactly HEARTS_PER_WAVE hearts drop from this wave's kills
        self.heart_drops, self.kills_left = HEARTS_PER_WAVE, len(self.queue)

    def spawn(self, kind):
        k = KINDS[kind]
        side = random.choice([-1, 1])
        x = -k["w"] if side < 0 else self.w
        hp = k["hp"] + (5 * (self.wave // BOSS_EVERY - 1) if k.get("boss") and self.wave else 0)
        self.enemies.append(dict(kind=kind, x=float(x), w=k["w"], hp=hp, max_hp=hp, state="walk",
                                 t=0.0, flash=0.0, fire_cd=random.uniform(1.5, 4.0),
                                 alt=k.get("alt", 0), move="melee", ai_cd=random.uniform(1.5, 3.0),
                                 vx=0.0, hit_k=False))

    def hit(self, e, dmg, push, src="sword", stun=0.4):
        """Damage an enemy. False when a guard's shield stopped it."""
        k = KINDS[e["kind"]]
        cx = e["x"] + e["w"] / 2.0
        if k.get("guard") and src in ("sword", "beam") and e["state"] != "stun":
            e["x"] += push / 3.0
            self.sparks.append([cx, e["alt"] + 1.5, 0.15, "#"])
            return False
        e["hp"] -= dmg
        e["flash"] = 0.15
        if k.get("heavy"):
            e["x"] += push / 3.0
        else:
            e["x"] += push
            e["state"], e["t"] = "stun", stun
        self.sparks.append([cx, e["alt"] + 1.5, 0.15, "*"])
        return True

    def swing(self):
        if self.atk_cd > 0 or self.dead:
            return
        if self.y >= 1.0:  # in the air: stab straight down, bounce off what you hit
            self.atk_cd, self.stab_t = 0.3, 0.2
            lo, hi = self.x - 2, self.x + KW + 2
            landed = False
            for e in self.enemies:
                if e["x"] < hi and e["x"] + e["w"] > lo and e["alt"] <= self.y + 1.5:
                    landed = self.hit(e, 2, 0, "stab") or landed
            if landed:
                self.vy, self.freeze = 11.0, 0.05
            return
        self.atk_cd, self.atk_t = 0.35, 0.18
        r = self.reach
        lo, hi = (self.x + 1, self.x + KW + r) if self.face > 0 else (self.x - r, self.x + KW - 1)
        landed = False
        for e in self.enemies:
            if e["x"] < hi and e["x"] + e["w"] > lo and e["alt"] - self.y <= 1.5:
                landed = self.hit(e, 1, self.face * 3, "sword", 0.3) or landed
        if landed:
            self.freeze = 0.05
        for f in self.fire:  # sword can also swat fireballs
            if not f[3] and lo <= f[0] <= hi and self.y < 2:
                f[2] = 0

    # ---------- powers (cost mana)
    def pay(self, cost):
        if self.dead or self.dash_t > 0:
            return False
        if self.mp < cost:
            self.mp_flash = 0.4
            return False
        self.mp -= cost
        return True

    def dash(self):
        """Quick invulnerable dash the way you face; cuts every enemy it passes."""
        if self.pay(self.dash_cost):
            self.dash_t, self.dash_dir, self.dash_hit = DASH_TIME, self.face, set()
            self.invuln = max(self.invuln, DASH_TIME + 0.1)

    def beam(self):
        """Sword beam: flies the way you face and pierces every enemy on its path."""
        if self.pay(BEAM_COST):
            self.atk_t = 0.18
            x = self.x + KW if self.face > 0 else self.x - 3
            self.beams.append([x, self.face * BEAM_SPEED, 1, set()])

    def spin(self):
        """Spin slash: 2 damage to everything close on both sides, swats fireballs."""
        if not self.pay(SPIN_COST):
            return
        self.spin_t = 0.3
        for e in self.enemies:
            g, side = self.gap(e)
            if g <= self.spin_range:
                self.hit(e, 2, side * 4, "spin")
        for f in self.fire:
            if not f[3] and abs(f[0] - (self.x + KW / 2.0)) <= self.spin_range + 2:
                f[2] = 0
        for i in range(-2, 3):
            self.sparks.append([self.x + 1 + i * 2.5, 1.0 + (i % 2), 0.25, "*"])

    def shield_press(self):
        """A fresh shield press (not key repeat) opens the parry window."""
        self.parry_t = PARRY_WINDOW

    def parry(self, e, side):
        self.parry_t = 0.0
        e["state"], e["t"] = "stun", 1.6
        e["x"] += side * 4
        self.mp = min(self.max_mp, self.mp + 1)
        self.freeze = max(self.freeze, 0.1)
        self.popup(self.x + 1.5 + side * 2, 4, "PARRY")

    # ---------- perks between waves
    def roll_perks(self):
        ok = [p for p, (_, can) in PERKS.items() if can(self)]
        return random.sample(ok, min(3, len(ok))) or None

    def pick(self, i):
        if not self.offer or not 0 <= i < len(self.offer):
            return
        p = self.offer[i]
        if p == "hp":
            self.max_hp += 1
            self.hp += 1
        elif p == "heal":
            self.hp = self.max_hp
        elif p == "reach":
            self.reach += 2
        elif p == "mana":
            self.max_mp += 2
            self.mp += 2
        elif p == "regen":
            self.regen *= 0.7
        elif p == "dash":
            self.dash_cost = 0
        elif p == "beam":
            self.beam_dmg = 2
        elif p == "spin":
            self.spin_range += 2
        self.perks.append(p)
        self.offer = None
        self.popup(self.x + 1.5, 4, PERKS[p][0], 1.0)

    # ---------- enemy behaviour
    def queued(self, i, gaps):
        """True if a ground enemy in front of enemy i (closer to the knight, same side)
        leaves no room: enemies line up instead of stacking into one blob."""
        e = self.enemies[i]
        g, side = gaps[i]
        for j, o in enumerate(self.enemies):
            og, oside = gaps[j]
            if j == i or KINDS[o["kind"]].get("fly") or oside != side or (og, j) >= (g, i):
                continue
            edge = e["x"] - (o["x"] + o["w"]) if side > 0 else o["x"] - (e["x"] + e["w"])
            if edge < SPACING:
                return True
        return False

    def boss_move(self, e, g):
        """Pick a special attack. True if one started."""
        r = random.random()
        if g > 8:
            e["move"] = "charge" if r < 0.5 else "fan"
        elif g <= 6 and r < 0.6:
            e["move"] = "slam"
        else:
            e["ai_cd"] = 1.0
            return False
        e["state"], e["t"] = "windup", 0.7 if e["move"] == "fan" else 0.9
        e["ai_cd"] = random.uniform(3.0, 5.0)
        return True

    def explode(self, e):
        cx = e["x"] + e["w"] / 2.0
        e["hp"], e["exploded"] = 0, True
        self.shake = max(self.shake, 0.35)
        self.burst(cx, 12, 4, "*#@")
        g, side = self.gap(e)
        if g <= 3.5:
            self.hurt(KINDS["bomber"]["dmg"], -side)
        for o in self.enemies:
            ox = o["x"] + o["w"] / 2.0
            if o is not e and o["hp"] > 0 and abs(ox - cx) <= 4 + o["w"] / 2.0:
                self.hit(o, 2, 3 if ox > cx else -3, "boom")

    def strike(self, e, g, side, blocking):
        """An enemy's windup is over: the attack lands (or misses)."""
        k = KINDS[e["kind"]]
        mv = e["move"]
        if k.get("bomb"):
            self.explode(e)
            return
        if mv == "slam":  # shockwave along the ground: jump it
            cx = e["x"] + e["w"] / 2.0
            for i in range(-6, 7):
                self.sparks.append([cx + i * 2, 0, 0.3, "^"])
            self.shake = max(self.shake, 0.4)
            if self.y < 0.5 and g <= 12:
                self.hurt(k["dmg"], -side)
            e["state"], e["t"] = "cool", 1.0
        elif mv == "fan":  # three fireballs at different speeds
            x = e["x"] + (0 if side > 0 else e["w"])
            for v in (16.0, 22.0, 28.0):
                self.fire.append([x, -side * v, 1, 0])
            e["state"], e["t"] = "cool", 0.8
        elif mv == "charge":
            e["state"], e["vx"], e["hit_k"] = "charge", -side * 26.0, False
        elif g <= 3 and (self.y < 2 or k.get("fly")):
            if blocking and self.face == side:
                if self.parry_t > 0:
                    self.parry(e, side)
                else:
                    e["state"], e["t"] = "stun", 0.8
                    e["x"] += side * 2
                    self.sparks.append([self.x + (KW if side > 0 else -1), 1.5, 0.2, "+"])
            else:
                self.hurt(k["dmg"], -side)
                e["state"], e["t"] = "cool", 0.9
        else:
            e["state"], e["t"] = "cool", 0.5

    def charge_step(self, e, blocking):
        e["x"] += e["vx"] * DT
        if not e["hit_k"] and self.gap(e)[0] <= 0:
            e["hit_k"] = True
            side = 1 if e["vx"] < 0 else -1   # the side it comes from
            if blocking and self.face == side:
                if self.parry_t > 0:
                    self.parry(e, side)
                    return
                self.x = min(max(0.0, self.x - side * 3), self.w - KW - 1)
                self.sparks.append([self.x + (KW if side > 0 else -1), 1.5, 0.2, "+"])
                self.shake = max(self.shake, 0.2)
            else:
                self.hurt(KINDS[e["kind"]]["dmg"], -side)
        passed = (e["x"] + e["w"] < self.x - 6) if e["vx"] < 0 else (e["x"] > self.x + KW + 6)
        wall = e["x"] <= 0 or e["x"] + e["w"] >= self.w - 1
        if passed or wall:
            e["x"] = min(max(0.0, e["x"]), self.w - e["w"] - 1.0)
            e["state"], e["t"] = "cool", 1.4
            if wall:
                self.shake = max(self.shake, 0.25)

    # ---------- one simulation step
    def step(self, mv, blocking):
        self.shake = max(0.0, self.shake - DT)
        for s in self.sparks:
            s[2] -= DT
        self.sparks = [s for s in self.sparks if s[2] > 0]
        if self.dead:
            self.death_t += DT
            return
        if self.freeze > 0:
            self.freeze -= DT
            return
        self.invuln = max(0.0, self.invuln - DT)
        self.atk_t = max(0.0, self.atk_t - DT)
        self.atk_cd = max(0.0, self.atk_cd - DT)
        self.stab_t = max(0.0, self.stab_t - DT)
        self.spin_t = max(0.0, self.spin_t - DT)
        self.parry_t = max(0.0, self.parry_t - DT)
        self.mp_flash = max(0.0, self.mp_flash - DT)
        self.clear_t = max(0.0, self.clear_t - DT)
        if self.combo_t > 0:
            self.combo_t -= DT
            if self.combo_t <= 0:
                self.combo = 0
        if self.mp < self.max_mp:
            self.mp_t += DT
            if self.mp_t >= self.regen:
                self.mp, self.mp_t = self.mp + 1, 0.0
        else:
            self.mp_t = 0.0

        # movement: ease the speed toward the target instead of jumping to it
        if self.dash_t > 0:
            self.dash_t -= DT
            self.x += self.dash_dir * DASH_SPEED * DT
            self.vx = self.dash_dir * RUN
            for e in self.enemies:
                if id(e) not in self.dash_hit and e["alt"] <= 1 and self.gap(e)[0] <= 0.5:
                    self.dash_hit.add(id(e))
                    self.hit(e, 1, self.dash_dir * 2, "dash")
        else:
            target = 0.0
            if mv and not blocking:
                self.face = mv
                target = mv * RUN
            if target:
                a = ACCEL if self.vx * target >= 0 else TURN
            else:
                a = FRICTION * (2 if blocking else 1)
            dv = target - self.vx
            self.vx += max(-a * DT, min(a * DT, dv))
            self.x += self.vx * DT
        lim = self.w - KW - 1
        if self.x <= 0 or self.x >= lim:
            self.x, self.vx = min(max(0.0, self.x), lim), 0.0
            self.dash_t = min(self.dash_t, 0.0)
        self.y += self.vy * DT
        self.vy -= GRAVITY * DT
        if self.y > JUMP_TOP:  # the HUD row is right above a jump in a short pane
            self.y, self.vy = JUMP_TOP, min(self.vy, 0.0)
        if self.y <= 0:
            self.y, self.vy = 0.0, 0.0

        # waves; a cleared wave offers perks, and the next one waits for the pick
        if not self.queue and not self.enemies:
            if not self.cleared:
                self.cleared, self.clear_t = True, 1.5
                self.offer = self.roll_perks()
                for _ in range(10):
                    self.sparks.append([random.uniform(2, self.w - 3), random.uniform(1, 4),
                                        random.uniform(0.3, 0.9), random.choice("*+")])
            if not self.offer:
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
        gaps = [self.gap(e) for e in self.enemies]
        for i, e in enumerate(self.enemies):
            if e["hp"] <= 0:
                continue  # blown up by a bomber this frame
            k = KINDS[e["kind"]]
            e["flash"] = max(0.0, e["flash"] - DT)
            e["fire_cd"] -= DT
            e["ai_cd"] -= DT
            g, side = self.gap(e)
            if e["state"] == "walk":
                if k.get("boss") and e["ai_cd"] <= 0 and self.boss_move(e, g):
                    continue
                if g > 1.5:
                    if k.get("fly") or not self.queued(i, gaps):
                        e["x"] -= side * k["speed"] * DT
                    if e["kind"] == "devil" and g > 12 and e["fire_cd"] <= 0 and 0 <= e["x"] <= self.w - 4:
                        e["fire_cd"] = random.uniform(3.0, 6.0)
                        self.fire.append([e["x"] + (0 if side > 0 else e["w"]), -side * 22.0, 1, 0])
                else:
                    e["state"], e["t"], e["move"] = "windup", k["windup"], "melee"
            elif e["state"] == "charge":
                self.charge_step(e, blocking)
            else:
                e["t"] -= DT
                if e["t"] <= 0:
                    if e["state"] == "windup":
                        self.strike(e, g, side, blocking)
                    else:
                        e["state"] = "walk"
        # sword beams: pierce, beam_dmg to each enemy once
        for b in self.beams:
            b[0] += b[1] * DT
            for e in self.enemies:
                if id(e) not in b[3] and e["x"] - 1 <= b[0] <= e["x"] + e["w"]:
                    b[3].add(id(e))
                    self.hit(e, self.beam_dmg, (1 if b[1] > 0 else -1) * 2, "beam")
            for f in self.fire:
                if not f[3] and abs(f[0] - b[0]) < 1.5:
                    f[2] = 0
        self.beams = [b for b in self.beams if -4 < b[0] < self.w + 2]

        alive = []
        for e in self.enemies:
            if e["hp"] > 0:
                alive.append(e)
                continue
            k = KINDS[e["kind"]]
            cx = e["x"] + e["w"] / 2.0
            if not e.get("exploded"):  # a bomber that blew itself up scores nothing
                self.combo = self.combo + 1 if self.combo_t > 0 else 1
                self.combo_t = COMBO_TIME
                self.best_combo = max(self.best_combo, self.combo)
                m = self.mult()
                self.score += k["score"] * m
                self.mp = min(self.max_mp, self.mp + MP_PER_KILL)
                if m > 1:
                    self.popup(cx, e["alt"] + 3, "x%d" % m, 0.5)
            if k.get("boss"):
                self.burst(cx, 16, 5, "*+#")
                self.shake = max(self.shake, 0.5)
            # spread the wave's hearts over its kills: the last kills always pay out
            if self.heart_drops and random.random() < self.heart_drops / max(1, self.kills_left):
                self.heart_drops -= 1
                self.hearts.append([min(max(1.0, e["x"] + 1), self.w - 3), 8.0])
            self.kills_left = max(0, self.kills_left - 1)
        self.enemies = alive

        # fireballs: [x, vx, alive, reflected]
        for f in self.fire:
            f[0] += f[1] * DT
            if not f[2]:
                continue
            if f[3]:  # parried back: burns the first ground enemy it meets
                for e in self.enemies:
                    if e["alt"] <= 1 and e["x"] - 0.5 <= f[0] <= e["x"] + e["w"]:
                        self.hit(e, 1, (1 if f[1] > 0 else -1) * 2, "fire")
                        f[2] = 0
                        break
                continue
            if self.x - 0.5 <= f[0] <= self.x + KW - 0.5 and self.y < 1:
                from_side = -1 if f[1] > 0 else 1   # side it arrives from
                if blocking and self.face == from_side:
                    if self.parry_t > 0:
                        f[1], f[3] = -f[1] * 1.2, 1
                        f[0] = self.x + (KW if from_side > 0 else -1)
                        self.parry_t = 0.0
                        self.mp = min(self.max_mp, self.mp + 1)
                        self.freeze = max(self.freeze, 0.06)
                        self.popup(self.x + 1.5 + from_side * 2, 4, "PARRY")
                        continue
                    self.sparks.append([f[0], 0.5, 0.2, "+"])
                else:
                    self.hurt(1, -from_side)
                f[2] = 0
        self.fire = [f for f in self.fire if f[2] and -2 < f[0] < self.w + 2]

        # hearts: [x, ttl]; at full health one turns into mana and points
        for h in self.hearts:
            h[1] -= DT
            if self.x - 1 <= h[0] <= self.x + KW and self.y < 1:
                if self.hp < self.max_hp:
                    self.hp += 1
                else:
                    self.mp = min(self.max_mp, self.mp + 1)
                    self.score += 10
                    self.popup(h[0] + 1, 3, "+MP")
                h[1] = 0
        self.hearts = [h for h in self.hearts if h[1] > 0]


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


_MIRROR = str.maketrans("()[]/\\<>", ")(][\\/><")


def mirror(rows):
    return [r[::-1].translate(_MIRROR) for r in rows]


def knight_rows(g, blocking):
    """Returns (rows, x offset)."""
    r = g.face > 0
    if g.dead:  # stagger, kneel, fall
        if g.death_t < 0.2:
            return ["\\O/", " | ", "/ \\"], 0
        if g.death_t < 0.45:
            return ["   ", " O ", "/|\\"], 0
        return ["   ", "   ", "_o_"], 0
    if g.spin_t > 0:
        return (["\\O/", "-|-", "/ \\"] if int(g.spin_t * 20) % 2 else [" O ", "\\|/", "/ \\"]), 0
    if g.stab_t > 0:
        return [" O ", "/|\\", "/V\\"], 0
    if g.dash_t > 0:
        return ([" O ", "=|>", "/ /"], 0) if r else ([" O ", "<|=", "\\ \\"], 0)
    if g.atk_t > 0:  # the drawn blade grows with the "Longer sword" perk
        n = g.reach - 1
        if r:
            return [" O ", "/|" + "=" * n + ">", "/ \\"], 0
        return [" " * (n + 1) + "O", "<" + "=" * n + "|\\", " " * n + "/ \\"], -n
    if blocking:
        return ([" O ", "/|]", "/ \\"], 0) if r else ([" O ", "[|\\", "/ \\"], 0)
    return ([" O ", "/|/", "/ \\"], 0) if r else ([" O ", "\\|\\", "/ \\"], 0)


def enemy_rows(g, e, frame):
    k = KINDS[e["kind"]]
    if e["state"] == "charge":
        return k["charge"]
    if e["state"] == "windup":
        rows = k["wind"]
    elif k.get("guard") and e["state"] == "stun":
        rows = k["open"]  # shield down: hit it now
    elif "walk2" in k and frame % 8 < 4:
        rows = k["walk2"]
    else:
        rows = k["walk"]
    if k.get("guard") and g.gap(e)[1] < 0:
        rows = mirror(rows)  # left of the knight: the shield faces right
    return rows


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
    help_page = None         # None, or the page of the H screen being shown
    banner = None            # None | "done" | "notify"
    seen = read_state()
    if seen and seen[1] == "quit":  # the session ended before the game got going
        return
    if seen and seen[1] in ("done", "notify"):
        banner = seen[1]
    last_key = {}
    move_until = {-1: 0.0, 1: 0.0}
    block_until = 0.0
    frame = 0
    frame_all = 1  # counts paused frames too (for the safety repaint)
    last_size = None
    repaint_until = time.time() + 1.5  # new WT panes grow just after start

    def held(key, now, first, repeat):
        """Terminals send no key-up events, so emulate holding via key repeat."""
        d = repeat if now - last_key.get(key, 0) < 0.6 else first
        last_key[key] = now
        return now + d

    while True:
        t0 = time.time()
        if not (paused or banner or help_page is not None):
            frame += 1
        if int(t0) != int(t0 - DT):
            heartbeat()
        # Windows: the VT screen re-measures the pane in erase(). WT can reflow a
        # pane on its own, so resend everything after a resize and every 5 s.
        if os.name == "nt":
            if scr.getmaxyx() != last_size:
                last_size = scr.getmaxyx()
                repaint_until = t0 + 0.5
            if (t0 < repaint_until and frame_all % 5 == 0) or frame_all % (FPS * 5) == 0:
                scr.clearok(True)
            frame_all += 1
        h, w = scr.getmaxyx()
        g.w = w
        ground = h - 2
        per_page = max(1, h - 2)          # rows 1 .. h-2; the footer takes the last row
        pages = -(-len(HELP) // per_page)
        if help_page is not None:
            help_page = min(help_page, pages - 1)  # the pane may have been resized

        st = read_state()
        if st != seen:
            seen = st
            if st and st[1] == "quit":
                return
            if st and st[1] in ("done", "notify"):
                banner, help_page = st[1], None
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
                    focus_claude()
                elif k in (ord("p"), ord("P")):
                    banner, paused = None, False
                continue
            if help_page is not None:  # H / space / Enter: next page; past the last, or Esc: close
                if k == 27 or (k in (ord("h"), ord("H"), ord("?"), ord(" "), 10, 13)
                               and help_page + 1 >= pages):
                    help_page = None
                elif k in (ord("h"), ord("H"), ord("?"), ord(" "), 10, 13):
                    help_page += 1
                continue
            if is_menu_key(k):
                choice = pick_game(scr, "knight")
                if choice == "quit":
                    return None
                if choice and choice != "knight":
                    return choice
                scr.clearok(True)
                continue
            if k in (ord("h"), ord("H"), ord("?")):
                help_page = 0
                continue
            if k in (ord("p"), ord("P")):
                paused = not paused
                continue
            if paused:
                if k in (ord(" "), 10, 13):
                    paused = False
                continue
            if g.dead:  # a short beat first, so mashing jump doesn't skip the death
                if k in (ord(" "), 10, 13) and g.death_t > 0.8:
                    g = Game(w)
                continue
            if g.offer and k in (ord("1"), ord("2"), ord("3")):
                g.pick(k - ord("1"))
                continue
            # first press holds a bit longer than before so the gap until the
            # OS key-repeat kicks in is bridged by the glide, not a stop
            if k in (ord("a"), ord("A"), curses.KEY_LEFT):
                move_until[-1], move_until[1] = held("L", now, 0.30, 0.12), 0.0
            elif k in (ord("d"), ord("D"), curses.KEY_RIGHT):
                move_until[1], move_until[-1] = held("R", now, 0.30, 0.12), 0.0
            elif k in (ord("u"), ord("U"), ord("e"), ord("E")):
                block_until = 0.0
                g.dash()
            elif k in (ord("i"), ord("I"), ord("r"), ord("R")):
                block_until = 0.0
                g.beam()
            elif k in (ord("l"), ord("L"), ord("g"), ord("G")):
                block_until = 0.0
                g.spin()
            elif k in (ord("w"), ord("W"), ord(" "), curses.KEY_UP):
                if g.y == 0:
                    g.vy = JUMP_V
            elif k in (ord("j"), ord("J"), ord("f"), ord("F")):
                block_until = 0.0
                g.swing()
            elif k in (ord("k"), ord("K"), ord("s"), ord("S"), curses.KEY_DOWN):
                if now - last_key.get("B", 0) >= 0.6:  # a fresh press, not key repeat
                    g.shield_press()
                block_until = held("B", now, 0.5, 0.16)

        now = time.time()
        blocking = now < block_until and g.atk_t <= 0 and not g.dead
        if h < MIN_H or w < MIN_W:
            scr.erase()
            put(scr, 0, 0, "Pane is %dx%d - need %dx%d" % (w, h, MIN_W, MIN_H))
            put(scr, 1, 0, "Make it bigger, or q to quit")
            scr.refresh()
            time.sleep(0.1)
            continue
        if not (paused or banner or help_page is not None):
            mv = 1 if now < move_until[1] else (-1 if now < move_until[-1] else 0)
            was_dead = g.dead
            g.step(mv, blocking)
            if g.dead and not was_dead and g.score > high:
                high = g.score
                save_high(high)

        # ---------- draw
        ox = (1 if frame % 2 else -1) if g.shake > 0 else 0   # screen shake
        scr.erase()
        put(scr, 0, 1, "HP ")
        put(scr, 0, 4, "#" * g.hp, col(1) | curses.A_BOLD)
        put(scr, 0, 4 + g.hp, "." * (g.max_hp - g.hp))
        mx = 5 + g.max_hp
        if g.mp_flash <= 0 or frame % 4 < 2:
            put(scr, 0, mx, "MP ")
            put(scr, 0, mx + 3, "*" * g.mp, col(2) | curses.A_BOLD)
            put(scr, 0, mx + 3 + g.mp, "." * (g.max_mp - g.mp))
        info = "wave %d  score %d" % (g.wave, g.score)
        sx = mx + 4 + g.max_mp
        put(scr, 0, sx, info)
        sx += len(info)
        if g.mult() > 1:
            put(scr, 0, sx + 1, "x%d" % g.mult(), col(3) | curses.A_BOLD)
            sx += 3
        put(scr, 0, sx + 2, "best %d" % max(high, g.score))
        put(scr, ground + 1, 0, "=" * (w - 1), col(4))
        for hx, ttl in g.hearts:
            if ttl > 2 or frame % 6 < 3:
                put(scr, ground, hx + ox, "<3", col(1) | curses.A_BOLD)
        for f in g.fire:
            put(scr, ground, f[0] + ox, "@" if frame % 4 < 2 else "*",
                col(2 if f[3] else 3) | curses.A_BOLD)
        for b in g.beams:
            put(scr, ground - 1, b[0] + ox, ")=>" if b[1] > 0 else "<=(", col(2) | curses.A_BOLD)
        boss = None
        for e in g.enemies:
            k = KINDS[e["kind"]]
            if k.get("boss"):
                boss = e
            lit = k.get("bomb") and e["state"] == "windup" and frame % 4 < 2
            attr = curses.A_REVERSE if e["flash"] > 0 or lit else col(k["col"]) | curses.A_BOLD
            put_sprite(scr, ground, e["x"] + ox, e["alt"], enemy_rows(g, e, frame), attr)
            top = ground - int(e["alt"]) - k["h"]
            mark = None
            if e["state"] == "windup":
                mark = "!!" if e["move"] in ("slam", "charge") else "!"
            elif e["state"] == "stun":
                mark = "~"
            if mark:
                put(scr, max(1, top), e["x"] + ox + e["w"] // 2, mark, col(3) | curses.A_BOLD)
        if g.invuln <= 0 or frame % 4 < 2 or g.dead:
            rows, off = knight_rows(g, blocking)
            put_sprite(scr, ground, g.x + off + ox, g.y, rows, col(2) | curses.A_BOLD)
        for sx_, sy, _, ch in g.sparks:
            put(scr, ground - int(sy), sx_ + ox, ch, col(3) | curses.A_BOLD)

        if boss and h >= 9:  # boss health bar on row 1 (the tip line's row)
            n = 20
            fill = max(0, int(round(n * boss["hp"] / float(boss["max_hp"]))))
            bar = "BOSS [" + "#" * fill + "." * (n - fill) + "]"
            put(scr, 1, max(0, (w - len(bar)) // 2), bar, col(5) | curses.A_BOLD)

        menu = g.offer and not (banner or paused or g.dead)
        if menu:  # perk pick between waves
            y0 = max(1, h // 2 - 2)
            title = " Wave %d clear! Pick a perk: " % g.wave
            put(scr, y0, max(0, (w - len(title)) // 2), title, curses.A_REVERSE)
            for i, p in enumerate(g.offer):
                line = " %d  %-13s" % (i + 1, PERKS[p][0])
                put(scr, y0 + 1 + i, max(0, (w - len(title)) // 2 + 2), line, col(3) | curses.A_BOLD)

        msg = None
        go = "  P = keep playing " if CLAUDE_PANE == "window" else "  Enter = go to Claude "
        if banner == "done":
            msg = " PAUSED - Claude is waiting for your prompt." + go
        elif banner == "notify":
            msg = " PAUSED - Claude needs you!" + go
        elif g.dead:
            if g.death_t > 0.8:
                msg = " YOU DIED  wave %d  best combo %d " % (g.wave, g.best_combo)
                sub = " space = fight again, q = quit "
                put(scr, max(1, h // 2 - 2) + 1, max(0, (w - len(sub)) // 2), sub, curses.A_REVERSE)
        elif paused:
            msg = " paused - space to resume, H = help "
        elif menu:
            pass
        elif g.clear_t > 0:
            msg = " WAVE %d CLEAR " % g.wave
        elif g.inter < 2.5 and not g.enemies and not g.queue:
            msg = " %s %d incoming... " % ("BOSS wave" if (g.wave + 1) % BOSS_EVERY == 0 else "Wave",
                                            g.wave + 1)
            if g.wave == 0:
                msg = " Wave 1 incoming - H = how to play "
        if msg:
            put(scr, max(1, h // 2 - 2), max(0, (w - len(msg)) // 2), msg, curses.A_REVERSE)
        if not (banner or menu or boss) and h >= 10:  # in a short pane row 1 is needed for the jump
            tip = "A/D move W jump J sword K shield | U dash I beam L spin | H help M games P Q"
            put(scr, 1, max(0, w - len(tip) - 2), tip, curses.A_DIM)
        if help_page is not None:  # the H screen covers everything below the HUD
            for y in range(1, h):
                put(scr, y, 0, " " * (w - 1))
            x0 = max(1, (w - 34) // 2)
            for i, (text, c, head) in enumerate(HELP[help_page * per_page:(help_page + 1) * per_page]):
                attr = curses.A_REVERSE if head else (col(c) | curses.A_BOLD if c else 0)
                put(scr, 1 + i, x0, (" %s " % text) if head else text, attr)
            more = "H next, Esc close  %d/%d" % (help_page + 1, pages) if pages > 1 else "H or Esc: close"
            put(scr, h - 1, x0, more, curses.A_DIM)
        scr.refresh()
        time.sleep(max(0, DT - (time.time() - t0)))


if __name__ == "__main__":
    run("knight")

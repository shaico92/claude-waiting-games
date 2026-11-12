#!/usr/bin/env python3
"""Knight vs Devils - a small terminal brawler to play while Claude Code works.

Move: A/D or Left/Right   Jump: W / Up / Space   Sword: J or F
Shield: K or S / Down     Pause: P               Quit: Q
Weapon: T (sword / spear / hammer)   Combo finisher: X (after a 6-kill combo)
Powers (cost mana):  Dash: U or E (1)   Sword beam: I or R (2)   Spin: L or G (3)
"""
import json, os, random, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import (curses, HookSession, put, load_int, save_int, run,  # noqa: E402
                    key_repeat_timing, KEYS)

# kept outside the plugin folder, which is replaced on every plugin update
SCORE_FILE = os.path.join(os.path.expanduser("~"), ".claude", "knight-game", "highscore")
# the run in progress, saved at each wave start; dying deletes it
RUN_FILE = os.path.join(os.path.expanduser("~"), ".claude", "knight-game", "run.json")
RUN_VERSION = 1
RUN_KEYS = ("score", "best_combo", "hp", "max_hp", "mp", "max_mp", "regen", "reach",
            "dash_refund", "beam_dmg", "spin_range", "perks", "weapon")
FPS = 30
DT = 1.0 / FPS
KW, KH, MAX_HP = 3, 3, 5
HEARTS_PER_WAVE = 2
# powerups dropped by kills: kind -> (glyph, color pair, name). One per wave, two on boss waves.
POWERUPS = {
    "aura":  ("(S)", 4, "SHIELD"),   # absorbs the next hit
    "rage":  ("(R)", 1, "RAGE"),     # +1 sword/beam damage, faster swings
    "haste": ("(H)", 3, "HASTE"),    # run faster, mana refills twice as fast
    "mana":  ("(M)", 5, "MANA"),     # all MP back at once
}
SCENE_WAVES = 3      # the scene changes every 3 waves
SCENE_T = 1.4        # curtain wipe between scenes (seconds)
SCENE_MSG_T = 3.5    # title + hint stay up this long
HAZARD_WARN, HAZARD_LIVE = 1.0, 0.45   # a hazard shows its warning, then strikes
POWER_TIME, POWER_TTL = 8.0, 12.0    # effect length / how long a drop waits to be picked up
# movement (cells / s, cells / s^2): accelerate to RUN, glide to a stop
RUN, ACCEL, TURN, FRICTION = 17.0, 110.0, 180.0, 60.0
# mana and powers
MAX_MP, MP_REGEN, MP_PER_KILL = 6, 2.5, 1       # MP_REGEN = seconds per point
DASH_COST, BEAM_COST, SPIN_COST = 1, 2, 3
DASH_TIME, DASH_SPEED = 0.18, 48.0
DASH_CD = 0.6            # between dashes: the dash can't be chained into endless invulnerability
BEAM_SPEED, SPIN_RANGE = 30.0, 5.0
SWORD_REACH = 4
RUN_STEP = 2.5        # cells walked per leg-cycle step
SWING_T = 0.18        # sword visible
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
                   walk=["'o'", "/^\\"], wind=["\\o/", " ^ "], step="\\^/"),
    "devil":  dict(w=3, h=3, hp=2, speed=7.0, dmg=1, windup=0.55, score=25, col=1,
                   walk=["^o^", "/W\\", "/ \\"], wind=["^o^", "\\W/", "/ \\"], step="| |"),
    "brute":  dict(w=5, h=4, hp=5, speed=4.0, dmg=2, windup=0.85, score=80, col=5, heavy=True,
                   walk=[" ^_^ ", "(o_o)", "/[W]\\", " / \\ "], step=" | | ",
                   wind=["\\^_^/", "(o_o)", " [W] ", " / \\ "]),
    "bat":    dict(w=3, h=1, hp=1, speed=9.0, dmg=1, windup=0.45, score=15, col=5, fly=True, alt=2,
                   walk=["/v\\"], walk2=["\\v/"], wind=["-v-"]),
    "guard":  dict(w=3, h=3, hp=2, speed=6.0, dmg=1, windup=0.60, score=35, col=1, guard=True,
                   walk=["^o^", "[W\\", "/ \\"], wind=["^o^", "[W/", "/ \\"], step="| |",
                   open=["^o^", "/W\\", "/ \\"]),
    "bomber": dict(w=3, h=2, hp=1, speed=8.0, dmg=2, windup=1.0, score=20, col=3, bomb=True,
                   walk=["(*)", "/ \\"], wind=["(@)", "/ \\"], step="| |"),
    # scene enemies: spider (cave) drops from the ceiling, roller (frost) rolls along the
    # ground - jump it, fimp (lava) leaves flames behind it
    "spider": dict(w=4, h=2, hp=2, speed=8.0, dmg=1, windup=0.40, score=30, col=5,
                   walk=["(oo)", "/\\/\\"], wind=["(OO)", "\\//\\"], step="|/\\|"),
    "roller": dict(w=3, h=2, hp=1, speed=0.0, dmg=1, windup=0.40, score=15, col=2,
                   walk=["(@)", "`-'"], wind=["(@)", "`-'"],
                   roll=[["(@)", "`-'"], ["(*)", ".-."]]),
    "fimp":   dict(w=3, h=2, hp=1, speed=10.0, dmg=1, windup=0.40, score=20, col=1,
                   walk=["~o~", "/^\\"], wind=["\\o/", " ^ "], step="\\^/"),
    "boss":   dict(w=7, h=5, hp=20, speed=3.5, dmg=2, windup=0.8, score=500, col=5,
                   heavy=True, boss=True,
                   walk=["  ^ ^  ", " (O O) ", "/[###]\\", " [###] ", " /   \\ "],
                   step=" |   | ",
                   wind=["\\ ^ ^ /", " (O O) ", " [###] ", " [###] ", " /   \\ "],
                   charge=["  ^ ^  ", " (>_<) ", "=[###]=", " [###] ", " /   \\ "]),
}

# Weapons (T swaps). reach None = the sword's own reach (grows with the perk).
#   sword:  quick, balanced        spear: long reach, slower        hammer: short, slow, hits for 2,
#                                                                    breaks guard shields, staggers brutes
WEAPONS = {
    "sword":  dict(label="SWD", cd=0.35, reach=None, bonus=0, dmg=1, src="sword", stun=0.3, blade="=", tip=">"),
    "spear":  dict(label="SPR", cd=0.50, reach=None, bonus=3, dmg=1, src="sword", stun=0.3, blade="-", tip="}"),
    "hammer": dict(label="HMR", cd=0.70, reach=3, bonus=0, dmg=2, src="hammer", stun=0.9, blade="=", tip="#"),
}
WEAPON_ORDER = ["sword", "spear", "hammer"]
_TIP_LEFT = {">": "<", "}": "{", "#": "#"}
FINISHER_COMBO, FINISHER_DMG, FINISHER_T = 6, 3, 0.4   # a finisher is earned every 6 kills of combo
FLAME_TTL, FLAME_EVERY = 3.0, 4.0                       # fire imp: a flame every 4 cells, burns 3 s

# Scenes. Each one is a look (backdrop, weather, ground) plus a mechanic that suits it and
# a nudge to who attacks and which powerup drops, so the stages play differently:
#   cave:  stalactites fall (they crush enemies too - lure them)  bats, spiders  shield drops
#   frost: ice, you slide (dash and haste matter)                  guards, rollers haste drops
#   lava:  geysers erupt (jump them)                               bombers, fire imps mana drops
# backdrop layer: (rows above the ground, characters, density, parallax, color pair)
SCENES = [
    dict(name="MEADOW", hint="a quiet start", ground="=", gcol=4, hazard=None, ice=False,
         back=[(9, "~", 0.10, 0.05, 2), (6, "^", 0.14, 0.15, 4)], weather=None,
         extra=[], boon={"rage": 1}),
    dict(name="CAVE", hint="stalactites fall - lure enemies under them", ground="=#", gcol=5,
         hazard="drip", ice=False,
         back=[(9, "v", 0.16, 0.05, 5), (6, "^", 0.10, 0.15, 5)], weather="drip",
         extra=[("bat", 2, 2), ("spider", 4, 2)], boon={"aura": 2}),
    dict(name="FROST", hint="the ice is slippery - dash and haste help", ground="~-", gcol=2,
         hazard=None, ice=True,
         back=[(9, "*", 0.05, 0.05, 2), (6, "A", 0.12, 0.15, 2)], weather="snow",
         extra=[("guard", 4, 1), ("roller", 7, 3)], boon={"haste": 3}),
    dict(name="LAVA", hint="geysers erupt - jump them", ground="=^", gcol=1,
         hazard="geyser", ice=False,
         back=[(9, "^", 0.10, 0.05, 1), (6, "A", 0.12, 0.15, 3)], weather="embers",
         extra=[("bomber", 3, 2), ("fimp", 10, 3)], boon={"mana": 2}),
]
# One boss per scene (the scene that is on when it spawns). All of them keep the classic charge,
# fan of fireballs and ground slam, and add one signature move:
#   summon: calls imps to its side         quake: stalactites rain on the knight's spot
#   slide:  a long ice slide to the wall,  erupt: a line of geysers marching at the knight
#           then it sits stunned
BOSSES = [
    dict(name="DEVIL KING", col=5, hp=20, move="summon", horns="^ ^", body="###",
         hint="it calls imps - cut them down fast"),
    dict(name="CAVE TYRANT", col=3, hp=20, move="quake", horns="Y Y", body="%%%",
         hint="move! stalactites fall where you stand"),
    dict(name="FROST WARDEN", col=2, hp=18, move="slide", horns="* *", body="***",
         hint="dodge the slide, then hit it at the wall"),
    dict(name="MAGMA GOLEM", col=1, hp=24, move="erupt", horns="A A", body="@@@",
         hint="geysers march at you - jump them"),
]
BOSS_MOVES = ("slam", "charge", "slide", "quake", "erupt", "summon")   # these show "!!"
SUMMON_CAP = 7       # no summoning past this many enemies on screen
_BACK = {}   # (scene index, layer) -> a long random strip, built once


def scene_of(wave):
    return ((max(1, wave) - 1) // SCENE_WAVES) % len(SCENES)


def backdrop_strip(si, li):
    if (si, li) not in _BACK:
        rnd = random.Random(si * 31 + li)
        ch, dens = SCENES[si]["back"][li][1:3]
        _BACK[(si, li)] = "".join(ch if rnd.random() < dens else " " for _ in range(400))
    return _BACK[(si, li)]


# perk: (label, still worth offering?)
PERKS = {
    "hp":    ("+1 max HP",    lambda g: g.max_hp < 8),
    "heal":  ("Full heal",    lambda g: g.hp < g.max_hp),
    "reach": ("Longer sword", lambda g: g.reach < 8),
    "mana":  ("+2 max MP",    lambda g: g.max_mp < 10),
    "regen": ("Faster mana",  lambda g: g.regen > 1.2),
    "dash":  ("Cheap dash",   lambda g: not g.dash_refund),   # a dash that kills refunds its MP
    "beam":  ("Beam hits x2", lambda g: g.beam_dmg < 2),
    "spin":  ("Wider spin",   lambda g: g.spin_range < 9),
}

# held-key ids (common.KEYS): lowercase letter, or the curses arrow code
RIGHT_KEYS = (ord("d"), 261)
LEFT_KEYS = (ord("a"), 260)
SHIELD_KEYS = (ord("k"), ord("s"), 258)

# the H screen: (text, color pair, is a heading). Lines fit a 36-column pane.
HELP = [
    ("CONTROLS", 0, True),
    ("A/D move    W jump    P pause", 0, False),
    ("J sword     K shield (hold it)", 0, False),
    ("W then J    stab down, bounces", 2, False),
    ("tap K just before a hit: PARRY", 2, False),
    ("  stuns, +1 MP, fireballs fly back", 0, False),
    ("U dash 1MP  I beam 2MP  L spin 3MP", 2, False),
    ("T weapon: sword spear hammer", 2, False),
    ("  spear reaches far, hammer breaks", 0, False),
    ("  guards and staggers brutes", 0, False),
    ("X finisher after a 6-kill combo", 2, False),
    ("COMBO  kills <2.5s apart: x2-x4", 3, False),
    ("PERKS  1/2/3 after each wave", 3, False),
    ("M or Tab   switch to another game", 0, False),
    ("SAVED  each wave; dying starts over", 3, False),
    ("POWERUPS  kills drop them: walk in", 0, True),
    ("(S) shield  absorbs one hit", 4, False),
    ("(R) rage    2x damage, fast swings", 1, False),
    ("(H) haste   run + mana faster", 3, False),
    ("(M) mana    all MP back", 5, False),
    ("SCENES  change every 3 waves", 0, True),
    ("cave: stalactites (crush foes too)", 5, False),
    ("frost: ice, you slide", 2, False),
    ("lava: geysers - jump them", 1, False),
    ("ENEMIES", 0, True),
    ("'o'   imp     fast, 1 hit", 1, False),
    ("^o^   devil   throws fireballs", 1, False),
    ("/v\\   bat     flies: W+J, I or L", 5, False),
    ("(*)   bomber  lit fuse: run!", 3, False),
    ("[W\\   guard   K or parry, then J", 1, False),
    ("(oo)  spider  drops in (cave)", 5, False),
    ("(@)   roller  jump it (frost)", 2, False),
    ("~o~   fire imp  leaves flames", 1, False),
    ("E     elite   2x HP, powerup drop", 3, False),
    ("(O O) boss    every 5th wave,", 5, False),
    ("       a new one per scene", 5, False),
    ("!  attack coming    !! big one", 3, False),
    ("~  stunned: hit it now", 3, False),
]


def load_high():
    return load_int(SCORE_FILE)


def save_high(n):
    save_int(SCORE_FILE, n)


def load_run():
    """The saved run as a dict, or None (no save, unreadable, or from another version)."""
    try:
        with open(RUN_FILE, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("version") == RUN_VERSION and int(d["wave"]) >= 1 and all(k in d for k in RUN_KEYS):
            return d
    except Exception:
        pass
    return None


def save_run(d):
    try:
        os.makedirs(os.path.dirname(RUN_FILE), exist_ok=True)
        tmp = RUN_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, RUN_FILE)   # never leave a half-written save behind
    except Exception:
        pass


def clear_run():
    try:
        os.remove(RUN_FILE)
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
        self.dash_cd, self.dash_refund, self.dash_refunded = 0.0, False, False
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
        # animation clocks (look only, never change the rules)
        self.run_d = 0.0      # distance walked: drives the leg cycle
        self.age = 0.0        # idle breathing
        self.land_t = 0.0     # landing crouch
        self.hurt_t = 0.0     # flinch pose after a hit
        self.ghosts = []      # dash afterimages: [x, y, ttl, face]
        self.powerups = []    # drops lying around: [x, ttl, kind]
        self.power_drops = 0  # still to drop from this wave's kills
        self.aura, self.rage_t, self.haste_t = 0, 0.0, 0.0
        self.scene, self.prev_scene = 0, 0
        self.scene_t, self.scene_msg_t = 0.0, 0.0   # curtain wipe / title banner clocks
        self.hazards = []     # [x, t, kind]: t counts down to the strike, then -HAZARD_LIVE
        self.haz_t = 4.0
        self.boss_msg_t, self.boss_variant = 0.0, 0   # intro banner for a freshly arrived boss
        self.h = 16           # pane height (main() keeps it current): spiders drop from near the top
        self.weapon = "sword"
        self.flames = []      # fire imp trail: [x, ttl]
        self.fin_ready, self.fin_next, self.fin_t = False, FINISHER_COMBO, 0.0
        self.resumed = False  # this run came back from the save file

    # ---------- the saved run
    def snapshot(self, wave):
        """What lasts between waves; `wave` is the wave to play next."""
        d = {k: getattr(self, k) for k in RUN_KEYS}
        d["perks"] = list(self.perks)
        d.update(version=RUN_VERSION, wave=wave)
        return d

    def restore(self, d):
        """Back to the start of wave d["wave"], with the saved stats. Bad values fall back to defaults."""
        try:
            self.max_hp, self.max_mp = max(1, int(d["max_hp"])), max(1, int(d["max_mp"]))
            self.hp = min(max(1, int(d["hp"])), self.max_hp)
            self.mp = min(max(0, int(d["mp"])), self.max_mp)
            self.regen, self.reach = float(d["regen"]), int(d["reach"])
            self.dash_refund, self.beam_dmg = bool(d["dash_refund"]), int(d["beam_dmg"])
            self.spin_range = int(d["spin_range"])
            self.score, self.best_combo = int(d["score"]), int(d["best_combo"])
            self.perks = [p for p in d["perks"] if p in PERKS]
            self.weapon = d["weapon"] if d["weapon"] in WEAPONS else "sword"
            wave = max(1, int(d["wave"]))
        except Exception:
            self.__init__(self.w)
            return False
        # step() calls next_wave() after the usual pause; same scene, so no curtain wipe
        self.wave = wave - 1
        self.scene = self.prev_scene = scene_of(wave)
        self.cleared, self.offer, self.inter = True, None, 2.4
        self.resumed = True
        return True

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
        if self.aura > 0:   # the shield powerup soaks this hit
            self.aura -= 1
            self.invuln = 0.8
            self.freeze = max(self.freeze, 0.05)
            self.burst(self.x + 1, 6, 2, "o*")
            self.popup(self.x + 1.5, 4, "BLOCKED")
            return False
        self.hp -= dmg
        self.hurt_t = 0.25
        self.invuln = 1.0
        self.vx = 0.0
        self.x = min(max(0.0, self.x + away * 3), self.w - KW - 1)
        self.combo, self.combo_t = 0, 0.0
        self.fin_ready, self.fin_next = False, FINISHER_COMBO
        self.freeze = max(self.freeze, 0.08)
        if dmg >= 2:
            self.shake = max(self.shake, 0.3)
        if self.hp <= 0:
            self.hp, self.dead = 0, True
            clear_run()   # dying ends the run: the next game starts at wave 1
            self.burst(self.x + 1, 8, 3, "*+x")
        return True

    def step_hazards(self):
        """Cave stalactites and lava geysers: a warning, then a strike. They hurt enemies too."""
        kind = SCENES[self.scene]["hazard"]
        fighting = (self.enemies or self.queue) and not self.offer and self.scene_t <= 0
        if kind and fighting:
            self.haz_t -= DT
            if self.haz_t <= 0:
                self.haz_t = max(2.0, random.uniform(3.0, 5.0) - self.wave * 0.1)
                # aim near the knight so the warning matters, but not right on top of it
                x = self.x + 1 + random.choice([-1, 1]) * random.uniform(2, 9)
                self.hazards.append([min(max(2.0, x), self.w - 4.0), HAZARD_WARN, kind])
        for hz in self.hazards:
            before = hz[1]
            hz[1] -= DT
            if before > 0 >= hz[1]:     # the strike lands this frame
                self.burst(hz[0], 6, 1.5, "*^" if hz[2] == "geyser" else "*.")
                self.shake = max(self.shake, 0.2)
                height = 1.0 if hz[2] == "geyser" else 3.0   # a geyser can be jumped over
                lo, hi = hz[0] - 1.5, hz[0] + 1.5
                if self.x < hi and self.x + KW > lo and self.y < height:
                    self.hurt(1, 1 if self.x + 1 >= hz[0] else -1)
                for e in self.enemies:
                    if e["x"] < hi and e["x"] + e["w"] > lo and e["alt"] < height + 1:
                        self.hit(e, 2, 0, "hazard")
        self.hazards = [hz for hz in self.hazards if hz[1] > -HAZARD_LIVE]

    def pick_power(self):
        """A drop that is useful right now: no second shield, no mana at a full bar."""
        w = {"rage": 2, "haste": 2}
        for kind, extra in SCENES[self.scene]["boon"].items():
            w[kind] = w.get(kind, 0) + extra
        if self.aura == 0:
            w["aura"] = w.get("aura", 0) + 3
        else:
            w.pop("aura", None)
        if self.mp <= self.max_mp - 3:
            w["mana"] = w.get("mana", 0) + 3
        else:
            w.pop("mana", None)
        return random.choices(list(w), list(w.values()))[0]

    def take_power(self, kind):
        if kind == "aura":
            self.aura = 1
        elif kind == "rage":
            self.rage_t = POWER_TIME
        elif kind == "haste":
            self.haste_t = POWER_TIME
        else:
            self.mp, self.mp_t = self.max_mp, 0.0
        self.score += 10
        self.popup(self.x + 1.5, 4, POWERUPS[kind][2] + "!", 0.8)

    def next_wave(self):
        self.wave += 1
        w = self.wave
        si = scene_of(w)
        if si != self.scene:   # new stage: curtain wipe, title, and the old hazards go away
            self.prev_scene, self.scene = self.scene, si
            self.scene_t, self.scene_msg_t = SCENE_T, SCENE_MSG_T
            self.hazards, self.haz_t, self.flames = [], 4.0, []
        pool = ["imp"] * 4
        if w >= 2:
            pool += ["devil"] * (2 + w)
        if w >= 3:
            pool += ["bat"] * (1 + w // 3)
        if w >= 4:
            pool += ["brute"] * (w - 3) + ["bomber"] * 2
        if w >= 6:
            pool += ["guard"] * (w - 5)
        for kind, min_wave, n in SCENES[self.scene]["extra"]:
            if w >= min_wave:
                pool += [kind] * n
        if w % BOSS_EVERY == 0:
            # queue.pop() takes from the end: the boss comes first, helpers after
            self.queue = [random.choice(pool) for _ in range(1 + w // BOSS_EVERY)] + ["boss"]
        else:
            self.queue = [random.choice(pool) for _ in range(2 + w)]
            if w >= 4 and w % 2 == 0:
                self.queue.append("brute")
        if w % BOSS_EVERY == 3:   # the wave before the boss gap starts: an elite mini-boss
            self.queue.insert(len(self.queue) // 2, "elite")
        self.spawn_t = 0.5
        self.cleared = False
        # exactly HEARTS_PER_WAVE hearts drop from this wave's kills
        self.heart_drops, self.kills_left = HEARTS_PER_WAVE, len(self.queue)
        self.power_drops = 1 + (w % BOSS_EVERY == 0)

    def spawn(self, kind):
        elite = kind == "elite"      # an elite is a brute with double HP, a gold look and a reward
        if elite:
            kind = "brute"
        k = KINDS[kind]
        side = random.choice([-1, 1])
        x = -k["w"] if side < 0 else self.w
        base = BOSSES[self.scene]["hp"] if k.get("boss") else k["hp"]
        hp = base + (5 * (self.wave // BOSS_EVERY - 1) if k.get("boss") and self.wave else 0)
        if elite:
            hp *= 2
        if k.get("boss"):
            self.boss_msg_t, self.boss_variant = 2.5, self.scene
        e = dict(kind=kind, x=float(x), w=k["w"], hp=hp, max_hp=hp, state="walk",
                 t=0.0, flash=0.0, fire_cd=random.uniform(1.5, 4.0),
                 alt=k.get("alt", 0), move="melee", ai_cd=random.uniform(1.5, 3.0),
                 vx=0.0, hit_k=False, variant=self.scene)
        if elite:
            e["elite"] = True
        elif kind == "spider":   # lowers itself from the ceiling next to the knight
            e["x"] = min(max(1.0, self.x + random.choice([-1, 1]) * random.uniform(6, 12)), self.w - 6.0)
            e["alt"], e["state"] = max(3.0, min(8.0, self.h - 7.0)), "drop"
        elif kind == "roller":   # crosses the whole screen along the ground
            e["state"], e["vx"] = "roll", 15.0 if side < 0 else -15.0
        self.enemies.append(e)

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
        if k.get("heavy") and not (src == "hammer" and not k.get("boss")):
            e["x"] += push / 3.0
        elif e["state"] in ("drop", "roll"):
            pass
        else:
            e["x"] += push
            e["state"], e["t"] = "stun", stun
        self.sparks.append([cx, e["alt"] + 1.5, 0.15, "*"])
        return True

    def swing(self):
        if self.atk_cd > 0 or self.dead:
            return
        if self.y >= 1.0:  # in the air: stab straight down, bounce off what you hit
            self.atk_cd, self.stab_t = (0.2 if self.rage_t > 0 else 0.3), 0.2
            lo, hi = self.x - 2, self.x + KW + 2
            landed = False
            for e in self.enemies:
                if e["x"] < hi and e["x"] + e["w"] > lo and e["alt"] <= self.y + 1.5:
                    landed = self.hit(e, 2 + (self.rage_t > 0), 0, "stab") or landed
            if landed:
                self.vy, self.freeze = 11.0, 0.05
            return
        wp = WEAPONS[self.weapon]
        self.atk_cd, self.atk_t = wp["cd"] * (0.57 if self.rage_t > 0 else 1.0), SWING_T
        r = self.weapon_reach()
        lo, hi = (self.x + 1, self.x + KW + r) if self.face > 0 else (self.x - r, self.x + KW - 1)
        landed = False
        for e in self.enemies:
            if e["x"] < hi and e["x"] + e["w"] > lo and e["alt"] - self.y <= 1.5:
                landed = self.hit(e, wp["dmg"] + (self.rage_t > 0), self.face * 3, wp["src"], wp["stun"]) or landed
        if landed:
            self.freeze = 0.05
        for f in self.fire:  # sword can also swat fireballs
            if not f[3] and lo <= f[0] <= hi and self.y < 2:
                f[2] = 0

    def weapon_reach(self):
        wp = WEAPONS[self.weapon]
        return (wp["reach"] or self.reach) + wp["bonus"]

    def swap_weapon(self):
        if self.dead or self.atk_t > 0:
            return
        i = WEAPON_ORDER.index(self.weapon)
        self.weapon = WEAPON_ORDER[(i + 1) % len(WEAPON_ORDER)]
        self.atk_cd = max(self.atk_cd, 0.15)
        self.popup(self.x + 1.5, 4, self.weapon.upper(), 0.6)

    def finisher(self):
        """Combo finisher: a free slash across the whole screen. Earned every 6 kills of combo."""
        if not self.fin_ready or self.dead or self.dash_t > 0:
            return False
        self.fin_ready = False
        self.fin_t, self.spin_t = FINISHER_T, 0.3
        self.invuln = max(self.invuln, 0.6)
        for e in self.enemies:
            side = self.gap(e)[1]
            self.hit(e, FINISHER_DMG + (self.rage_t > 0), side * 3, "spin")
        for f in self.fire:
            f[2] = 0
        self.freeze = max(self.freeze, 0.12)
        self.shake = max(self.shake, 0.45)
        for i in range(12):
            self.sparks.append([random.uniform(1, self.w - 3), random.uniform(0, 3), random.uniform(0.3, 0.6), "*"])
        return True

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
        if self.dash_cd > 0:
            return
        if self.pay(self.dash_cost):
            self.dash_t, self.dash_dir, self.dash_hit = DASH_TIME, self.face, set()
            self.dash_cd, self.dash_refunded = DASH_CD, False
            self.invuln = max(self.invuln, DASH_TIME + 0.1)

    def beam(self):
        """Sword beam: flies the way you face and pierces every enemy on its path."""
        if self.pay(BEAM_COST):
            self.atk_t = SWING_T
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
            self.dash_refund = True
        elif p == "beam":
            self.beam_dmg = 2
        elif p == "spin":
            self.spin_range += 2
        self.perks.append(p)
        self.offer = None
        save_run(self.snapshot(self.wave + 1))   # keep the perk; the cleared wave isn't replayed
        self.popup(self.x + 1.5, 4, PERKS[p][0], 1.0)

    # ---------- enemy behaviour
    def queued(self, i, gaps):
        """True if a ground enemy in front of enemy i (closer to the knight, same side)
        leaves no room: enemies line up instead of stacking into one blob."""
        e = self.enemies[i]
        g, side = gaps[i]
        for j, o in enumerate(self.enemies[:len(gaps)]):   # imps a boss just summoned have no gap yet
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
        sig = BOSSES[e.get("variant", 0)]["move"]   # this boss's signature move
        if g > 8:
            e["move"] = "charge" if r < 0.3 else ("fan" if r < 0.6 else sig)
        elif g <= 6 and r < 0.7:
            e["move"] = "slam" if r < 0.3 else sig
        else:
            e["ai_cd"] = 1.0
            return False
        e["state"], e["t"] = "windup", {"fan": 0.7, "quake": 1.0, "slide": 1.0}.get(e["move"], 0.9)
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
        elif mv == "summon":  # imps pour in on both sides of the boss
            for dx in (-4.0, e["w"] + 1.0):
                if len(self.enemies) < SUMMON_CAP:
                    self.spawn("imp")
                    imp = self.enemies[-1]
                    imp["x"] = min(max(0.0, e["x"] + dx), self.w - 4.0)
                    self.burst(imp["x"] + 1, 4, 1, "*^")
            e["state"], e["t"] = "cool", 1.0
        elif mv == "quake":  # three of five stalactite slots over the knight, one by one
            cx = self.x + KW / 2.0
            for i, d in enumerate(random.sample((-10, -5, 0, 5, 10), 3)):
                x = min(max(2.0, cx + d), self.w - 4.0)
                self.hazards.append([x, HAZARD_WARN + i * 0.15, "drip"])
            self.shake = max(self.shake, 0.3)
            e["state"], e["t"] = "cool", 1.4
        elif mv == "erupt":  # a line of geysers marching from the boss toward the knight
            bx = e["x"] + e["w"] / 2.0
            for i in range(4):
                x = min(max(2.0, bx - side * (6 + 5 * i)), self.w - 4.0)
                self.hazards.append([x, 0.5 + i * 0.25, "geyser"])
            self.shake = max(self.shake, 0.3)
            e["state"], e["t"] = "cool", 1.4
        elif mv == "slide":  # like a charge, but it only stops at the wall - then it sits stunned
            e["state"], e["vx"], e["hit_k"] = "charge", -side * 34.0, False
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
        sliding = e["move"] == "slide"
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
        if (passed and not sliding) or wall:
            e["x"] = min(max(0.0, e["x"]), self.w - e["w"] - 1.0)
            e["state"], e["t"] = "cool", 1.4
            if sliding and wall:     # crashed into the wall: a long opening to hit it
                e["state"], e["t"] = "stun", 2.4
                self.burst(e["x"] + e["w"] / 2.0, 8, 3, "*#")
                self.popup(e["x"] + e["w"] / 2.0, 5, "CRASH", 0.9)
            if wall:
                self.shake = max(self.shake, 0.4 if sliding else 0.25)

    # ---------- one simulation step
    def step(self, mv, blocking, speed=1.0):
        """speed < 1 walks slower: a key press not yet confirmed as a hold."""
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
        self.dash_cd = max(0.0, self.dash_cd - DT)
        self.atk_t = max(0.0, self.atk_t - DT)
        self.atk_cd = max(0.0, self.atk_cd - DT)
        self.stab_t = max(0.0, self.stab_t - DT)
        self.spin_t = max(0.0, self.spin_t - DT)
        self.parry_t = max(0.0, self.parry_t - DT)
        self.mp_flash = max(0.0, self.mp_flash - DT)
        self.scene_t = max(0.0, self.scene_t - DT)
        self.fin_t = max(0.0, self.fin_t - DT)
        self.boss_msg_t = max(0.0, self.boss_msg_t - DT)
        self.scene_msg_t = max(0.0, self.scene_msg_t - DT)
        self.rage_t = max(0.0, self.rage_t - DT)
        self.haste_t = max(0.0, self.haste_t - DT)
        self.land_t = max(0.0, self.land_t - DT)
        self.hurt_t = max(0.0, self.hurt_t - DT)
        self.age += DT
        for gh in self.ghosts:
            gh[2] -= DT
        self.ghosts = [gh for gh in self.ghosts if gh[2] > 0]
        self.clear_t = max(0.0, self.clear_t - DT)
        if self.combo_t > 0:
            self.combo_t -= DT
            if self.combo_t <= 0:
                self.combo = 0
                self.fin_ready, self.fin_next = False, FINISHER_COMBO   # a broken combo loses it
        if self.mp < self.max_mp:
            self.mp_t += DT * (2 if self.haste_t > 0 else 1)
            if self.mp_t >= self.regen:
                self.mp, self.mp_t = self.mp + 1, 0.0
        else:
            self.mp_t = 0.0

        # movement: ease the speed toward the target instead of jumping to it
        if self.dash_t > 0:
            self.dash_t -= DT
            self.x += self.dash_dir * DASH_SPEED * DT
            self.vx = self.dash_dir * RUN
            self.ghosts.append([self.x, self.y, 0.2, self.dash_dir])
            for e in self.enemies:
                if id(e) not in self.dash_hit and e["alt"] <= 1 and self.gap(e)[0] <= 0.5:
                    self.dash_hit.add(id(e))
                    self.hit(e, 1, self.dash_dir * 2, "dash")
                    if self.dash_refund and e["hp"] <= 0 and not self.dash_refunded:
                        self.dash_refunded = True   # once per dash
                        self.mp = min(self.max_mp, self.mp + self.dash_cost)
        else:
            target = 0.0
            if mv and not blocking:
                self.face = mv
                target = mv * RUN * speed * (1.35 if self.haste_t > 0 else 1)
            if target:
                a = ACCEL if self.vx * target >= 0 else TURN
                if SCENES[self.scene]["ice"]:
                    a *= 0.45 if self.vx * target >= 0 else 0.3   # slow to start, slower to turn
            else:
                a = FRICTION * (2 if blocking else 1)
                if SCENES[self.scene]["ice"]:
                    a *= 0.2   # glides a long way
            dv = target - self.vx
            self.vx += max(-a * DT, min(a * DT, dv))
            self.x += self.vx * DT
            if self.y <= 0:
                before = self.run_d
                self.run_d += abs(self.vx) * DT
                if abs(self.vx) > 6 and int(before / RUN_STEP) != int(self.run_d / RUN_STEP) \
                        and not blocking:   # a puff of dust at each footfall
                    self.sparks.append([self.x + 1 - self.face * 1.5, 0.0, 0.22, "."])
        lim = self.w - KW - 1
        if self.x <= 0 or self.x >= lim:
            self.x, self.vx = min(max(0.0, self.x), lim), 0.0
            self.dash_t = min(self.dash_t, 0.0)
        air_vy = self.vy
        was_air = self.y > 0
        self.y += self.vy * DT
        self.vy -= GRAVITY * DT
        if self.y > JUMP_TOP:  # the HUD row is right above a jump in a short pane
            self.y, self.vy = JUMP_TOP, min(self.vy, 0.0)
        if self.y <= 0:
            if was_air and air_vy < -6:   # landing: crouch and kick up dust
                self.land_t = 0.12
                for dx in (-1.0, 3.0):
                    self.sparks.append([self.x + dx, 0.0, 0.25, "."])
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
                    self.resumed = False
                    save_run(self.snapshot(self.wave))
        elif self.queue:
            self.spawn_t -= DT
            if self.spawn_t <= 0 and len(self.enemies) < min(2 + self.wave // 2, 6):
                self.spawn(self.queue.pop())
                self.spawn_t = random.uniform(0.8, 2.2)

        # enemies
        gaps = [self.gap(e) for e in self.enemies]
        for i, e in enumerate(list(self.enemies)):   # a boss may add imps mid-loop
            if e["hp"] <= 0:
                continue  # blown up by a bomber this frame
            k = KINDS[e["kind"]]
            e["flash"] = max(0.0, e["flash"] - DT)
            e["fire_cd"] -= DT
            e["ai_cd"] -= DT
            g, side = self.gap(e)
            if e["state"] == "drop":     # spider lowering itself on its thread
                e["alt"] -= 12.0 * DT
                if e["alt"] <= 0:
                    e["alt"], e["state"] = 0, "walk"
                    self.burst(e["x"] + 2, 3, 1.5, ".")
                    if g <= 1 and self.y < 1.5:   # it landed on you
                        self.hurt(k["dmg"], -side)
                continue
            if e["state"] == "roll":     # snowball: jump it, block it or cut it down
                e["x"] += e["vx"] * DT
                if not e["hit_k"] and self.x < e["x"] + e["w"] and self.x + KW > e["x"] and self.y < 1:
                    e["hit_k"] = True
                    from_side = 1 if e["vx"] < 0 else -1
                    if blocking and self.face == from_side:
                        e["hp"], e["exploded"] = 0, True
                        self.burst(e["x"] + 1, 5, 1.5, "*o")
                        self.mp = min(self.max_mp, self.mp + 1)
                    else:
                        self.hurt(k["dmg"], -from_side)
                if e["x"] < -e["w"] - 3 or e["x"] > self.w + 3:
                    e["hp"], e["exploded"] = 0, True   # rolled off the screen
                continue
            if e["state"] == "walk":
                if k.get("boss") and e["ai_cd"] <= 0 and self.boss_move(e, g):
                    continue
                if e["kind"] == "fimp" and g > 1.5:   # leaves a burning trail
                    e["trail"] = e.get("trail", 0.0) + k["speed"] * DT
                    if e["trail"] >= FLAME_EVERY and len(self.flames) < 6 and 0 <= e["x"] <= self.w - 4:
                        e["trail"] = 0.0
                        self.flames.append([e["x"] + 1, FLAME_TTL])
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
                    self.hit(e, self.beam_dmg + (self.rage_t > 0), (1 if b[1] > 0 else -1) * 2, "beam")
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
                if self.combo >= self.fin_next:
                    self.fin_ready, self.fin_next = True, self.fin_next + FINISHER_COMBO
                    self.popup(self.x + 1.5, 5, "FINISHER! X", 1.0)
                m = self.mult()
                self.score += k["score"] * m * (3 if e.get("elite") else 1)
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
            if e.get("elite"):   # an elite always pays out a powerup
                self.powerups.append([min(max(1.0, e["x"] + 1), self.w - 4), POWER_TTL, self.pick_power()])
                self.popup(cx, 5, "ELITE!", 0.8)
            if self.power_drops and random.random() < self.power_drops / max(1, self.kills_left):
                self.power_drops -= 1
                self.powerups.append([min(max(1.0, e["x"] + 1), self.w - 4), POWER_TTL, self.pick_power()])
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

        # powerups: [x, ttl, kind]
        for pu in self.powerups:
            pu[1] -= DT
            if self.x - 2 <= pu[0] <= self.x + KW and self.y < 2:
                self.take_power(pu[2])
                pu[1] = 0
        self.powerups = [pu for pu in self.powerups if pu[1] > 0]
        self.step_hazards()
        for fl in self.flames:
            fl[1] -= DT
            if self.x < fl[0] + 1.5 and self.x + KW > fl[0] - 0.5 and self.y < 1:
                self.hurt(1, 1 if self.x + 1 >= fl[0] else -1)
        self.flames = [fl for fl in self.flames if fl[1] > 0]


def col_of(n):
    return curses.color_pair(n) if curses.has_colors() else 0


def draw_scene(scr, g, si, ground, w, frame, x0, x1):
    """Backdrop, weather and ground of scene `si` in columns x0 .. x1 (the wipe splits two)."""
    if x1 <= x0:
        return
    sc = SCENES[si]
    for li, (dy, _, _, par, c) in enumerate(sc["back"]):
        row = ground - dy
        if 2 <= row <= ground - 5:   # only above the fighting space
            off = int(g.x * par) % 200
            put(scr, row, x0, backdrop_strip(si, li)[off + x0: off + x1], col_of(c) | curses.A_DIM)
    wx = sc["weather"]
    if wx and ground >= 8:
        for i in range(max(6, (x1 - x0) // 4)):
            cx = x0 + (i * 37) % (x1 - x0)
            span = ground - 3
            if wx == "snow":
                ry = 2 + int(frame * 0.25 + i * 5) % span
                ch, c = ("." if i % 2 else "*"), 2
                cx = x0 + (cx - x0 + int(frame * 0.05 + ry * 0.3)) % (x1 - x0)
            elif wx == "embers":
                ry = ground - 1 - int(frame * 0.3 + i * 5) % span
                ch, c = ("'" if i % 2 else "`"), 1
            else:   # drip: short falling streaks
                ry = 2 + int(frame * 0.5 + i * 7) % span
                ch, c = ":", 5
            if 2 <= ry <= ground - 1:
                put(scr, ry, cx, ch, col_of(c) | curses.A_DIM)
    pat = sc["ground"]
    put(scr, ground + 1, x0, (pat * (w // len(pat) + 2))[x0: x1], col_of(sc["gcol"]))


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
        n = g.weapon_reach() - 1
        wp = WEAPONS[g.weapon]
        if g.atk_t < SWING_T * 0.55:  # recovery: the blade is drawn back
            n = max(1, n // 2)
        if r:
            return [" O ", "/|" + wp["blade"] * n + wp["tip"], "/ \\"], 0
        return [" " * (n + 1) + "O", _TIP_LEFT[wp["tip"]] + wp["blade"] * n + "|\\", " " * n + "/ \\"], -n
    if g.hurt_t > 0:  # flinch
        return ([" x ", "\\|/", "/ \\"], 0)
    if g.y > 0:  # in the air: arms up on the way up, legs tucked on the way down
        if g.vy > 3:
            return (["\\O/", " | ", "/ \\"], 0)
        if g.vy < -3:
            return ([" O ", "\\|/", "| |"], 0)
    elif g.land_t > 0 and not blocking:  # landing crouch
        return ([" O ", "/_\\"], 0)
    legs = "/ \\"
    if abs(g.vx) > 2.5:  # run cycle: stride, pass, stride, pass
        legs = ("/ \\", " | ", "\\ /", " | ")[int(g.run_d / RUN_STEP) % 4]
    elif blocking is False and int(g.age * 2) % 6 == 5:  # idle: a slow breath
        return ([" o ", "/|/", legs], 0) if r else ([" o ", "\\|\\", legs], 0)
    if blocking:
        return ([" O ", "/|]", legs], 0) if r else ([" O ", "[|\\", legs], 0)
    return ([" O ", "/|/", legs], 0) if r else ([" O ", "\\|\\", legs], 0)


def enemy_rows(g, e, frame):
    k = KINDS[e["kind"]]
    if e["state"] == "roll":
        return k["roll"][int(e["x"] / 1.5) % 2]
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
        if "step" in k and e["state"] == "walk" and int(e["x"] / 1.2) % 2:
            rows = rows[:-1] + [k["step"]]  # legs swap as it moves
    if k.get("guard") and g.gap(e)[1] < 0:
        rows = mirror(rows)  # left of the knight: the shield faces right
    if k.get("boss"):   # each boss has its own horns and belly
        b = BOSSES[e.get("variant", 0)]
        rows = [r.replace("^ ^", b["horns"]).replace("###", b["body"]) for r in rows]
    return rows


def enemy_col(e):
    k = KINDS[e["kind"]]
    if e.get("elite"):
        return 3
    return BOSSES[e.get("variant", 0)]["col"] if k.get("boss") else k["col"]


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
    run_save = load_run()
    if run_save:
        g.restore(run_save)
    paused = False
    help_page = None         # None, or the page of the H screen being shown
    ses = HookSession("knight")   # Claude's state: banners, Q, M menu, Enter = go to Claude
    if ses.quit:  # the session ended before the game got going
        return None
    last_key = {}
    move_until = {-1: 0.0, 1: 0.0}
    walk_speed = 1.0         # < 1 until the key repeat confirms the key is held
    block_until = 0.0
    jump_buf = 0.0           # a jump pressed just before landing still counts
    delay, interval = key_repeat_timing()
    first = delay + 0.08                      # bridges the gap until the OS starts repeating
    repeat = min(0.25, max(0.12, interval * 3 + 0.04))   # a held key keeps the knight going
    frame = 0
    frame_all = 1  # counts paused frames too (for the safety repaint)
    last_size = None
    repaint_until = time.time() + 1.5  # new WT panes grow just after start

    def held(key, now, first, repeat):
        """Terminals send no key-up events, so emulate holding via key repeat.
        Returns (when the hold lapses, True once the key is seen repeating)."""
        rep_ = now - last_key.get(key, 0) < first + 0.1
        last_key[key] = now
        return now + (repeat if rep_ else first), rep_

    while True:
        t0 = time.time()
        if not (paused or ses.banner or help_page is not None):
            frame += 1
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
        g.w, g.h = w, h
        ground = h - 2
        per_page = max(1, h - 2)          # rows 1 .. h-2; the footer takes the last row
        pages = -(-len(HELP) // per_page)
        if help_page is not None:
            help_page = min(help_page, pages - 1)  # the pane may have been resized

        ev = ses.poll()
        if ev == "quit":
            return None
        if ev == "pause":
            help_page = None
        elif ev == "run":
            paused = False

        while True:
            k = scr.getch()
            if k == -1:
                break
            now = time.time()
            act = ses.key(scr, k)
            if act == "quit":
                return None
            if act == "switch":
                return ses.next
            if act in ("pause", "play"):
                paused = act == "pause"
            if act:
                continue
            if help_page is not None:  # H / space / Enter: next page; past the last, or Esc: close
                if k == 27 or (k in (ord("h"), ord("H"), ord("?"), ord(" "), 10, 13)
                               and help_page + 1 >= pages):
                    help_page = None
                elif k in (ord("h"), ord("H"), ord("?"), ord(" "), 10, 13):
                    help_page += 1
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
            # the first press keeps going for the OS repeat delay, at walking pace;
            # once the repeats arrive the knight runs and keeps running until they stop
            if k in (ord("a"), ord("A"), curses.KEY_LEFT):
                move_until[-1], rep_ = held("L", now, first, repeat)
                move_until[1], walk_speed = 0.0, (1.0 if rep_ else 0.55)
            elif k in (ord("d"), ord("D"), curses.KEY_RIGHT):
                move_until[1], rep_ = held("R", now, first, repeat)
                move_until[-1], walk_speed = 0.0, (1.0 if rep_ else 0.55)
            elif k in (ord("t"), ord("T")):
                g.swap_weapon()
            elif k in (ord("x"), ord("X")):
                block_until = 0.0
                g.finisher()
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
                else:
                    jump_buf = now + 0.12
            elif k in (ord("j"), ord("J"), ord("f"), ord("F")):
                block_until = 0.0
                g.swing()
            elif k in (ord("k"), ord("K"), ord("s"), ord("S"), curses.KEY_DOWN):
                if now - last_key.get("B", 0) >= 0.6:  # a fresh press, not key repeat
                    g.shield_press()
                block_until = held("B", now, max(0.5, first), 0.16)[0]

        now = time.time()
        # real key-ups known (Windows console, WT win32-input-mode): read what is held, so
        # running survives a stab or a jump. Otherwise: the key-repeat emulation above.
        right, left = KEYS.since(RIGHT_KEYS), KEYS.since(LEFT_KEYS)
        if KEYS.real:
            shield_on = KEYS.since(SHIELD_KEYS) is not None
        else:
            shield_on = now < block_until
        blocking = shield_on and g.atk_t <= 0 and not g.dead
        if h < MIN_H or w < MIN_W:
            scr.erase()
            put(scr, 0, 0, "Pane is %dx%d - need %dx%d" % (w, h, MIN_W, MIN_H))
            put(scr, 1, 0, "Make it bigger, or q to quit")
            scr.refresh()
            time.sleep(0.1)
            continue
        if not (paused or ses.banner or help_page is not None):
            if KEYS.real:
                mv = 1 if right and (not left or right >= left) else (-1 if left else 0)
                walk_speed = 1.0
            else:
                mv = 1 if now < move_until[1] else (-1 if now < move_until[-1] else 0)
            if now < jump_buf and g.y == 0 and not g.dead:
                g.vy, jump_buf = JUMP_V, 0.0
            was_dead = g.dead
            g.step(mv, blocking, walk_speed)
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
        info = "[%s] wave %d  score %d" % (WEAPONS[g.weapon]["label"], g.wave, g.score)
        sx = mx + 4 + g.max_mp
        put(scr, 0, sx, info)
        sx += len(info)
        if g.mult() > 1:
            put(scr, 0, sx + 1, "x%d" % g.mult(), col(3) | curses.A_BOLD)
            sx += 3
        if g.fin_ready and frame % 6 < 4:
            put(scr, 0, sx + 1, "X!", col(2) | curses.A_BOLD | curses.A_REVERSE)
            sx += 3
        put(scr, 0, sx + 2, "best %d" % max(high, g.score))
        cut = int(w * (1 - g.scene_t / SCENE_T)) if g.scene_t > 0 else w
        draw_scene(scr, g, g.scene, ground, w, frame, 0, min(cut, w - 1))
        if g.scene_t > 0:       # curtain wipe: old scene on the right, a bright edge between
            draw_scene(scr, g, g.prev_scene, ground, w, frame, cut, w - 1)
            for yy in range(2, ground + 2):
                put(scr, yy, cut, "|", col(3) | curses.A_BOLD)
        for hx_, ht, hk in g.hazards:   # warnings and strikes
            if hk == "drip":
                if ht > 0:
                    put(scr, 2, hx_ - 1, "vVv" if frame % 4 < 2 else "v!v", col(3) | curses.A_BOLD)
                    if ht < 0.5:
                        put(scr, 3, hx_, "|", col(3))
                else:
                    for yy in range(2, ground + 1):
                        put(scr, yy, hx_, "|", col(5) | curses.A_BOLD)
            else:
                if ht > 0:
                    put(scr, ground, hx_ - 1, "^^^" if frame % 4 < 2 else ".^.", col(3) | curses.A_BOLD)
                else:
                    for dy in range(0, 4):
                        put(scr, ground - dy, hx_ - 1, "AAA" if dy == 0 else " A ", col(1) | curses.A_BOLD)
        for gx, gy, gt, gf in g.ghosts:   # dash afterimages fade out behind the knight
            if gt < 0.12 or frame % 2:
                put_sprite(scr, ground, gx + ox, gy,
                           [" O ", "=|>", "/ /"] if gf > 0 else [" O ", "<|=", "\\ \\"], col(2) | curses.A_DIM)
        for hx, ttl in g.hearts:
            if ttl > 2 or frame % 6 < 3:
                put(scr, ground - (1 if frame % 16 < 4 else 0), hx + ox, "<3", col(1) | curses.A_BOLD)
        for fx, ftl in g.flames:   # a fire imp's trail
            if ftl > 0.8 or frame % 4 < 2:
                put(scr, ground, fx + ox, "/\\" if frame % 6 < 3 else "\\/", col(1) | curses.A_BOLD)
                put(scr, ground - 1, fx + ox, "^" if frame % 4 < 2 else "'", col(3) | curses.A_BOLD)
        for px, pttl, pk in g.powerups:
            if pttl > 3 or frame % 4 < 2:
                put(scr, ground - (1 if frame % 20 < 10 else 0), px + ox, POWERUPS[pk][0],
                    col(POWERUPS[pk][1]) | curses.A_BOLD)
        for f in g.fire:
            put(scr, ground, f[0] - (2 if f[1] > 0 else -2) + ox, "-", col(2 if f[3] else 3) | curses.A_DIM)
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
            attr = curses.A_REVERSE if e["flash"] > 0 or lit else col(enemy_col(e)) | curses.A_BOLD
            put_sprite(scr, ground, e["x"] + ox, e["alt"], enemy_rows(g, e, frame), attr)
            top = ground - int(e["alt"]) - k["h"]
            mark = None
            if e["state"] == "windup":
                mark = "!!" if e["move"] in BOSS_MOVES else "!"
            elif e["state"] == "stun":
                mark = "~"
            elif e.get("elite"):
                mark = "E"
            if e["state"] == "drop":   # the spider's thread, from the top of the pane
                for yy in range(2, max(2, top)):
                    put(scr, yy, e["x"] + ox + e["w"] // 2, "|", col(5) | curses.A_DIM)
            if mark:
                put(scr, max(1, top), e["x"] + ox + e["w"] // 2, mark, col(3) | curses.A_BOLD)
        if g.invuln <= 0 or frame % 4 < 2 or g.dead:
            rows, off = knight_rows(g, blocking)
            put_sprite(scr, ground, g.x + off + ox, g.y, rows, col(2) | curses.A_BOLD)
        if g.fin_t > 0:   # the finisher: two crescents race to the edges
            prog = 1 - g.fin_t / FINISHER_T
            cx_ = int(g.x + 1)
            for yy in range(1, ground + 1):
                put(scr, yy, cx_ + int(prog * (w - cx_)), ")", col(2) | curses.A_BOLD)
                put(scr, yy, cx_ - int(prog * cx_), "(", col(2) | curses.A_BOLD)
        if not g.dead:
            mid = ground - int(round(g.y)) - 1
            if g.aura:   # shield powerup: brackets around the knight
                put(scr, mid, g.x - 1 + ox, "(", col(4) | curses.A_BOLD)
                put(scr, mid, g.x + KW + ox, ")", col(4) | curses.A_BOLD)
            tags = [("RAGE", g.rage_t, 1), ("HASTE", g.haste_t, 3)]
            tx = g.x + ox
            for name, left, c in tags:
                if left > 0 and (left > 2 or frame % 4 < 2):
                    label = "%s %d" % (name, int(left) + 1)
                    put(scr, max(1, mid - 2), tx, label, col(c) | curses.A_BOLD)
                    tx += len(label) + 1
        for sx_, sy, _, ch in g.sparks:
            put(scr, ground - int(sy), sx_ + ox, ch, col(3) | curses.A_BOLD)

        if boss and h >= 9:  # boss health bar on row 1 (the tip line's row)
            name = BOSSES[boss.get("variant", 0)]["name"]
            n = max(8, min(20, w - len(name) - 6))
            fill = max(0, int(round(n * boss["hp"] / float(boss["max_hp"]))))
            bar = name + " [" + "#" * fill + "." * (n - fill) + "]"
            put(scr, 1, max(0, (w - len(bar)) // 2), bar, col(5) | curses.A_BOLD)

        menu = g.offer and not (ses.banner or paused or g.dead)
        if menu:  # perk pick between waves
            y0 = max(1, h // 2 - 2)
            title = " Wave %d clear! Pick a perk: " % g.wave
            put(scr, y0, max(0, (w - len(title)) // 2), title, curses.A_REVERSE)
            for i, p in enumerate(g.offer):
                line = " %d  %-13s" % (i + 1, PERKS[p][0])
                put(scr, y0 + 1 + i, max(0, (w - len(title)) // 2 + 2), line, col(3) | curses.A_BOLD)

        msg = None
        if ses.banner:
            msg = ses.banner_msg()
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
            if g.resumed:
                msg = " Run resumed - wave %d incoming " % (g.wave + 1)
        if g.scene_msg_t > 0 and not (ses.banner or paused or g.dead or menu):
            title = " ~ %s ~ " % SCENES[g.scene]["name"]
            put(scr, max(1, h // 2 - 3), max(0, (w - len(title)) // 2), title, curses.A_REVERSE | curses.A_BOLD)
            hint = " %s " % SCENES[g.scene]["hint"]
            put(scr, max(1, h // 2 - 2), max(0, (w - len(hint)) // 2), hint, col(3) | curses.A_BOLD)
        elif msg:
            put(scr, max(1, h // 2 - 2), max(0, (w - len(msg)) // 2), msg, curses.A_REVERSE)
        if g.boss_msg_t > 0 and not (ses.banner or paused or g.dead or menu):
            bb = BOSSES[g.boss_variant]
            title = " !! %s !! " % bb["name"]
            put(scr, max(1, h // 2 - 1), max(0, (w - len(title)) // 2), title, col(bb["col"]) | curses.A_REVERSE | curses.A_BOLD)
            hint = " %s " % bb["hint"]
            put(scr, max(1, h // 2), max(0, (w - len(hint)) // 2), hint, col(3) | curses.A_BOLD)
        if not (ses.banner or menu or boss) and h >= 10:  # in a short pane row 1 is needed for the jump
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

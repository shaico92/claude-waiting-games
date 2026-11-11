#!/usr/bin/env python3
"""Tiny terminal dino runner to play while Claude Code is working.
Space/Up/W = jump, P = pause, M = switch game, Q = quit."""
import os, random, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import (curses, DATA, CLAUDE_PANE, read_state, heartbeat,  # noqa: E402
                    focus_claude, is_menu_key, pick_game, run)

SCORE_FILE = os.path.join(DATA, "dino-highscore")
FPS = 30
DINO_X = 6
DINO = [" @>", " /\\"]  # top row, bottom row


def load_high():
    try:
        return int(open(SCORE_FILE).read().strip())
    except Exception:
        return 0


def save_high(n):
    try:
        os.makedirs(DATA, exist_ok=True)
        open(SCORE_FILE, "w").write(str(n))
    except Exception:
        pass


def put(win, y, x, s, attr=0):
    h, w = win.getmaxyx()
    if 0 <= y < h and x < w - 1:
        if x < 0:
            s, x = s[-x:], 0
        try:
            win.addstr(y, x, s[: max(0, w - 1 - x)], attr)
        except curses.error:
            pass


def main(scr):
    """Returns the name of a game to switch to, or None to quit."""
    curses.curs_set(0)
    scr.nodelay(True)
    scr.keypad(True)
    scr.clear()
    high = load_high()

    def reset():
        return dict(y=0.0, vy=0.0, obs=[], gap=30.0, score=0.0, speed=0.55, dead=False)

    g = reset()
    paused = False
    banner = None  # None | "done" | "notify"
    seen = read_state()
    if seen and seen[1] == "quit":
        return None
    if seen and seen[1] in ("done", "notify"):
        banner = seen[1]

    while True:
        t0 = time.time()
        if int(t0) != int(t0 - 1.0 / FPS):
            heartbeat()
        h, w = scr.getmaxyx()
        ground = h - 2

        st = read_state()
        if st != seen:
            seen = st
            if st and st[1] == "quit":
                return None
            if st and st[1] in ("done", "notify"):
                banner = st[1]
            elif st and st[1] == "run":
                banner, paused = None, False

        while True:
            k = scr.getch()
            if k == -1:
                break
            if k in (ord("q"), ord("Q")):
                return None
            if is_menu_key(k):
                choice = pick_game(scr, "dino")
                if choice == "quit":
                    return None
                if choice and choice != "dino":
                    return choice
                scr.clear()
                paused = True
                continue
            if banner:
                if k in (10, 13, curses.KEY_ENTER):
                    banner, paused = None, True
                    focus_claude()
                elif k in (ord("p"), ord("P")):
                    banner, paused = None, False
                continue
            if k in (ord("p"), ord("P")):
                paused = not paused
            elif k in (ord(" "), curses.KEY_UP, ord("w"), ord("W")):
                if paused:
                    paused = False
                elif g["dead"]:
                    g = reset()
                elif g["y"] == 0:
                    g["vy"] = 0.9

        if not (paused or banner or g["dead"]):
            g["y"] += g["vy"]
            g["vy"] -= 0.11
            if g["y"] <= 0:
                g["y"], g["vy"] = 0.0, 0.0
            g["speed"] = min(1.3, 0.55 + g["score"] / 900.0)
            for o in g["obs"]:
                o[0] -= g["speed"]
            g["obs"] = [o for o in g["obs"] if o[0] + o[1] > 0]
            g["gap"] -= g["speed"]
            if g["gap"] <= 0:
                g["obs"].append([float(w), random.choice([1, 1, 2, 3]), random.choice([1, 2, 2])])
                g["gap"] = random.uniform(22, 45) + g["speed"] * 10
            g["score"] += g["speed"] / 3
            for x, ow, oh in g["obs"]:
                if x < DINO_X + 3 and x + ow > DINO_X + 1 and g["y"] < oh - 0.3:
                    g["dead"] = True
                    if int(g["score"]) > high:
                        high = int(g["score"])
                        save_high(high)

        scr.erase()
        put(scr, 0, 1, "score %d   best %d" % (g["score"], max(high, int(g["score"]))))
        put(scr, ground + 1, 0, "=" * (w - 1))
        dy = ground - int(round(g["y"]))
        put(scr, dy - 1, DINO_X, DINO[0], curses.A_BOLD)
        put(scr, dy, DINO_X, DINO[1], curses.A_BOLD)
        for x, ow, oh in g["obs"]:
            for r in range(oh):
                put(scr, ground - r, int(x), "#" * ow)
        go = "  P = keep playing " if CLAUDE_PANE == "window" else "  Enter = go to Claude "
        msg = None
        if banner == "done":
            msg = " PAUSED - Claude is waiting for your prompt." + go
        elif banner == "notify":
            msg = " PAUSED - Claude needs you!" + go
        elif g["dead"]:
            msg = " GAME OVER - space to retry, M other game, Q quit "
        elif paused:
            msg = " paused - space to resume "
        if msg:
            put(scr, max(1, h // 2 - 1), max(0, (w - len(msg)) // 2), msg, curses.A_REVERSE)
        else:
            tip = "space jump  P pause  M games  Q quit"
            put(scr, 0, max(0, w - len(tip) - 2), tip, curses.A_DIM)
        scr.refresh()
        time.sleep(max(0, 1.0 / FPS - (time.time() - t0)))


if __name__ == "__main__":
    run("dino")

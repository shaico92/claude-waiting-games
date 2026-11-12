#!/usr/bin/env python3
"""Tiny terminal dino runner to play while Claude Code is working.
Space/Up/W = jump, P = pause, M = switch game, Q = quit."""
import os, random, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import curses, DATA, HookSession, put, load_int, save_int, run  # noqa: E402

SCORE_FILE = os.path.join(DATA, "dino-highscore")
FPS = 30
DINO_X = 6
DINO = [" @>", " /\\"]  # top row, bottom row




def main(scr):
    """Returns the name of a game to switch to, or None to quit."""
    curses.curs_set(0)
    scr.nodelay(True)
    scr.keypad(True)
    scr.clear()
    high = load_int(SCORE_FILE)

    def reset():
        return dict(y=0.0, vy=0.0, obs=[], gap=30.0, score=0.0, speed=0.55, dead=False)

    g = reset()
    paused = False
    ses = HookSession("dino")  # Claude's state: banners, Q, M menu, Enter = go to Claude
    if ses.quit:
        return None

    while True:
        t0 = time.time()
        h, w = scr.getmaxyx()
        ground = h - 2

        ev = ses.poll()
        if ev == "quit":
            return None
        if ev == "run":
            paused = False

        while True:
            k = scr.getch()
            if k == -1:
                break
            act = ses.key(scr, k)
            if act == "quit":
                return None
            if act == "switch":
                return ses.next
            if act in ("back", "pause"):
                paused = True
            elif act == "play":
                paused = False
            if act:
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

        if not (paused or ses.banner or g["dead"]):
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
                        save_int(SCORE_FILE, high)

        scr.erase()
        put(scr, 0, 1, "score %d   best %d" % (g["score"], max(high, int(g["score"]))))
        put(scr, ground + 1, 0, "=" * (w - 1))
        dy = ground - int(round(g["y"]))
        put(scr, dy - 1, DINO_X, DINO[0], curses.A_BOLD)
        put(scr, dy, DINO_X, DINO[1], curses.A_BOLD)
        for x, ow, oh in g["obs"]:
            for r in range(oh):
                put(scr, ground - r, int(x), "#" * ow)
        msg = ses.banner_msg()
        if not msg and g["dead"]:
            msg = " GAME OVER - space to retry, M other game, Q quit "
        elif not msg and paused:
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

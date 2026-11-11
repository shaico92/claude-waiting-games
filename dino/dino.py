#!/usr/bin/env python3
"""Tiny terminal dino runner to play while Claude Code is working.
Space/Up = jump, p = pause, q = quit."""
import curses, os, random, subprocess, sys, time

HOME = os.path.dirname(os.path.abspath(__file__))
SCORE_FILE = os.path.join(HOME, "highscore")
FLAG = sys.argv[1] if len(sys.argv) > 1 else None        # file the hooks write to
CLAUDE_PANE = sys.argv[2] if len(sys.argv) > 2 else None  # tmux pane running Claude
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
        open(SCORE_FILE, "w").write(str(n))
    except Exception:
        pass


def read_flag():
    if not FLAG:
        return None
    try:
        return open(FLAG).read().strip() or None
    except Exception:
        return None


def clear_flag():
    try:
        os.remove(FLAG)
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
    curses.curs_set(0)
    scr.nodelay(True)
    scr.keypad(True)
    high = load_high()

    def reset():
        return dict(y=0.0, vy=0.0, obs=[], gap=30.0, score=0.0, speed=0.55, dead=False)

    g = reset()
    paused = False
    banner = None  # None | "done" | "notify"

    while True:
        t0 = time.time()
        h, w = scr.getmaxyx()
        ground = h - 2

        flag = read_flag()
        if flag in ("done", "notify"):
            banner = flag

        keys = []
        while True:
            k = scr.getch()
            if k == -1:
                break
            keys.append(k)
        for k in keys:
            if k in (ord("q"), ord("Q")):
                return
            if banner:
                if k in (10, 13, curses.KEY_ENTER):
                    if banner == "done":
                        return  # pane closes, focus goes back to Claude
                    clear_flag()
                    banner = None
                    paused = True
                    if CLAUDE_PANE:
                        subprocess.call(["tmux", "select-pane", "-t", CLAUDE_PANE])
                continue
            if k in (ord("p"), ord("P")):
                paused = not paused
            elif k in (ord(" "), curses.KEY_UP, ord("w")):
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
        msg = None
        if banner == "done":
            msg = " Claude is done!  Enter = back to Claude "
        elif banner == "notify":
            msg = " Claude needs you!  Enter = switch to Claude "
        elif g["dead"]:
            msg = " GAME OVER - space to retry, q to quit "
        elif paused:
            msg = " paused - space to resume "
        if msg:
            put(scr, max(1, h // 2 - 1), max(0, (w - len(msg)) // 2), msg, curses.A_REVERSE)
        else:
            put(scr, 0, max(0, w - 34), "space=jump  p=pause  q=quit")
        scr.refresh()
        time.sleep(max(0, 1.0 / FPS - (time.time() - t0)))


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    finally:
        if FLAG:
            clear_flag()

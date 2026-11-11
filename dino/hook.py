#!/usr/bin/env python3
"""Claude Code hook: opens/updates the dino game in a tmux pane.
usage: hook.py start|notify|stop   (never prints, never fails the hook)"""
import os, subprocess, sys, tempfile

HOME = os.path.dirname(os.path.abspath(__file__))


def tmux(*a):
    return subprocess.run(["tmux", *a], capture_output=True, text=True)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    pane = os.environ.get("TMUX_PANE")
    if not os.environ.get("TMUX") or not pane:
        return  # not in tmux: do nothing
    base = os.path.join(tempfile.gettempdir(), "claude-dino-" + pane.lstrip("%"))
    flag, panefile = base + ".flag", base + ".pane"

    game = None
    try:
        game = open(panefile).read().strip()
    except Exception:
        pass
    alive = bool(game) and game in tmux("list-panes", "-a", "-F", "#{pane_id}").stdout.split()

    if action == "start":
        try:
            os.remove(flag)
        except Exception:
            pass
        if alive:
            tmux("select-pane", "-t", game)
            return
        r = tmux("split-window", "-v", "-l", "12", "-t", pane, "-P", "-F", "#{pane_id}",
                 sys.executable, os.path.join(HOME, "dino.py"), flag, pane)
        if r.returncode == 0:
            open(panefile, "w").write(r.stdout.strip())
    elif action in ("notify", "stop") and alive:
        open(flag, "w").write("done" if action == "stop" else "notify")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

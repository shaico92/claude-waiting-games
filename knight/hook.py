#!/usr/bin/env python3
"""Claude Code hook for the knight game (tmux only).
usage: hook.py start|notify|stop   - never prints, never fails the hook
  start  (you sent a prompt)      open the game or resume it, and focus it
  notify (Claude needs an answer) pause with a banner
  stop   (Claude is waiting)      pause with a banner"""
import os, subprocess, sys, tempfile

HOME = os.path.dirname(os.path.abspath(__file__))


def tmux(*a):
    return subprocess.run(["tmux", *a], capture_output=True, text=True)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    pane = os.environ.get("TMUX_PANE")
    if not os.environ.get("TMUX") or not pane:
        return
    base = os.path.join(tempfile.gettempdir(), "claude-knight-" + pane.lstrip("%"))
    state, panefile = base + ".state", base + ".pane"
    game = None
    try:
        game = open(panefile).read().strip()
    except Exception:
        pass
    alive = bool(game) and game in tmux("list-panes", "-a", "-F", "#{pane_id}").stdout.split()

    if action == "start":
        open(state, "w").write("run")
        if alive:
            tmux("select-pane", "-t", game)
            return
        r = tmux("split-window", "-v", "-l", "16", "-t", pane, "-P", "-F", "#{pane_id}",
                 sys.executable, os.path.join(HOME, "knight.py"), state, pane)
        if r.returncode == 0:
            open(panefile, "w").write(r.stdout.strip())
    elif action in ("notify", "stop") and alive:
        open(state, "w").write("done" if action == "stop" else "notify")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

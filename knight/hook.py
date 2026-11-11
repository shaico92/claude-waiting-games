#!/usr/bin/env python3
"""Claude Code hook for the knight game (tmux, or Windows Terminal on Windows).
usage: hook.py start|notify|stop   - never prints, never fails the hook
  start  (you sent a prompt)      open the game or resume it, and focus it
  notify (Claude needs an answer) pause with a banner
  stop   (Claude is waiting)      pause with a banner"""
import json, os, shutil, subprocess, sys, tempfile, time

HOME = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HOME, "knight.py")


def tmux(*a):
    return subprocess.run(["tmux", *a], capture_output=True, text=True)


def run_tmux(action, pane):
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
                 sys.executable, GAME, state, pane)
        if r.returncode == 0:
            open(panefile, "w").write(r.stdout.strip())
    elif action in ("notify", "stop") and alive:
        open(state, "w").write("done" if action == "stop" else "notify")


def run_wt(action):
    """Windows Terminal has no pane ids, so the game pane is found by a heartbeat file
    it touches every second, and focus moves by direction (the game sits below Claude)."""
    wt = shutil.which("wt")
    if not wt:
        return
    key = os.environ["WT_SESSION"]
    try:
        key = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}").get("session_id") or key
    except Exception:
        pass
    state = os.path.join(tempfile.gettempdir(), "claude-knight-wt-" + key + ".state")
    try:
        alive = time.time() - os.stat(state + ".alive").st_mtime < 3
    except Exception:
        alive = False

    def wt_run(*a):
        subprocess.Popen([wt, "-w", "0", *a], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if action == "start":
        open(state, "w").write("run")
        if alive:
            wt_run("move-focus", "down")
        else:
            wt_run("split-pane", "-H", "-s", "0.4", "--title", "Knight vs Devils",
                   sys.executable, GAME, state, "wt")
    elif action in ("notify", "stop") and alive:
        open(state, "w").write("done" if action == "stop" else "notify")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    pane = os.environ.get("TMUX_PANE")
    if os.environ.get("TMUX") and pane:
        run_tmux(action, pane)
    elif os.name == "nt" and os.environ.get("WT_SESSION"):
        run_wt(action)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

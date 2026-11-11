#!/usr/bin/env python3
"""Claude Code hook for the knight game.
usage: hook.py start|notify|stop|end   - never prints, never fails the hook
  start  (you sent a prompt)      open the game or resume it
  notify (Claude needs an answer) pause with a banner
  stop   (Claude is waiting)      pause with a banner
  end    (session closed)         close the game

Where the game opens, first match wins:
  tmux              a pane below Claude (macOS, Linux, WSL)
  Windows Terminal  a split pane below Claude (Windows, or WSL inside Windows Terminal)
  window            its own terminal window - the VS Code extension, VS Code's terminal,
                    and any other terminal (Windows console, WSL, Linux desktop, macOS)"""
import json, os, platform, shutil, subprocess, sys, tempfile, time

HOME = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HOME, "knight.py")
TITLE = "Knight vs Devils"
IS_WSL = sys.platform.startswith("linux") and (
    "WSL_DISTRO_NAME" in os.environ or "microsoft" in platform.release().lower())
QUIET = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def spawn(cmd, **kw):
    """Start a program that outlives this hook."""
    if os.name == "nt":
        flags = kw.pop("creationflags", 0) | 0x00000200  # CREATE_NEW_PROCESS_GROUP
        try:  # leave Claude's job object, if any, so the game survives the hook
            return subprocess.Popen(cmd, creationflags=flags | 0x01000000, **QUIET, **kw)
        except OSError:
            return subprocess.Popen(cmd, creationflags=flags, **QUIET, **kw)
    return subprocess.Popen(cmd, start_new_session=True, **QUIET, **kw)


def in_vscode():
    """The VS Code extension (and VS Code's own terminal) has no pane we can split."""
    e = os.environ
    return ("vscode" in e.get("CLAUDE_CODE_ENTRYPOINT", "").lower()
            or e.get("TERM_PROGRAM") == "vscode"
            or "VSCODE_PID" in e or "VSCODE_IPC_HOOK" in e or "VSCODE_IPC_HOOK_CLI" in e)


def wt_exe():
    return shutil.which("wt.exe" if IS_WSL else "wt")


WT_TERMINAL_GUID = "{E12CFF52-A866-4C77-9A90-F570A7AA2C6B}"  # Windows Terminal's handoff class


def wt_is_default():
    """Windows Terminal set as the default terminal: consoles opened from the Start menu,
    Run box or WSL launcher land in it too, but without WT_SESSION. The window the
    prompt was just typed in is then the most recently used one, so "-w 0" finds it."""
    try:
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Console\%%Startup") as k:
                return winreg.QueryValueEx(k, "DelegationTerminal")[0].upper() == WT_TERMINAL_GUID
        if IS_WSL:
            reg = shutil.which("reg.exe") or "/mnt/c/Windows/System32/reg.exe"
            out = subprocess.run([reg, "query", r"HKCU\Console\%%Startup", "/v", "DelegationTerminal"],
                                 capture_output=True, text=True, timeout=3).stdout
            return WT_TERMINAL_GUID in out.upper()
    except Exception:
        pass
    return False


def game_cmd(state, mode):
    """The command line that runs the game, as seen from Windows when we are in WSL."""
    cmd = [sys.executable, GAME, state, mode]
    if IS_WSL:
        cmd = ["wsl.exe", "-d", os.environ.get("WSL_DISTRO_NAME", ""), "--"] + cmd
        if not cmd[2]:
            del cmd[1:3]
    return cmd


# ---------------------------------------------------------------- tmux
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
    elif alive:
        open(state, "w").write({"stop": "done", "notify": "notify", "end": "quit"}.get(action, "run"))


# ------------------------------------------- Windows Terminal split / own window
# Neither has pane ids we can query, so the game touches "<state>.alive" every second
# and the hook treats a fresh heartbeat as "the game is open".
def session_key(data):
    return (data.get("session_id") or os.environ.get("WT_SESSION") or "default").replace(os.sep, "_")


def run_heartbeat(action, data, mode):
    state = os.path.join(tempfile.gettempdir(), "claude-knight-%s-%s.state" % (mode, session_key(data)))
    try:
        alive = time.time() - os.stat(state + ".alive").st_mtime < 3
    except Exception:
        alive = False

    if action != "start":
        # also while the game is still starting (a quick answer can beat a new window):
        # it reads the state file on startup and opens paused
        if alive or os.path.exists(state):
            open(state, "w").write({"stop": "done", "notify": "notify", "end": "quit"}.get(action, "run"))
        return
    open(state, "w").write("run")
    if mode == "wt":
        wt = wt_exe()
        if alive:
            spawn([wt, "-w", "0", "move-focus", "down"])
        else:
            spawn([wt, "-w", "0", "split-pane", "-H", "-s", "0.4", "--title", TITLE]
                  + game_cmd(state, "wt"))
    elif not alive:
        open_window(state)


def open_window(state):
    cmd = game_cmd(state, "window")
    if os.name == "nt" or IS_WSL:
        wt = wt_exe()
        if wt:  # one named Windows Terminal window, reused across sessions
            spawn([wt, "-w", "claude-knight", "new-tab", "--title", TITLE] + cmd)
        elif os.name == "nt":
            spawn(cmd, creationflags=0x00000010)  # CREATE_NEW_CONSOLE
        else:
            spawn(["cmd.exe", "/c", "start", '"%s"' % TITLE] + cmd, cwd="/mnt/c" if os.path.isdir("/mnt/c") else None)
        return
    if sys.platform == "darwin":
        line = " ".join("'%s'" % a.replace("'", "'\\''") for a in cmd)
        spawn(["osascript", "-e", 'tell application "Terminal" to do script "%s"' % line.replace('"', '\\"'),
               "-e", 'tell application "Terminal" to activate'])
        return
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return  # no desktop to open a window on (ssh, server): run knight.py by hand
    terms = [
        ("x-terminal-emulator", ["-T", TITLE, "-e"]),
        ("gnome-terminal", ["--title", TITLE, "--"]),
        ("konsole", ["-p", "tabtitle=" + TITLE, "-e"]),
        ("xfce4-terminal", ["-T", TITLE, "-x"]),
        ("kitty", ["--title", TITLE]),
        ("alacritty", ["-t", TITLE, "-e"]),
        ("wezterm", ["start", "--"]),
        ("foot", ["-T", TITLE]),
        ("xterm", ["-T", TITLE, "-e"]),
    ]
    for name, args in terms:
        exe = shutil.which(name)
        if exe:
            spawn([exe] + args + cmd)
            return


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    data = {}
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "{}")
    except Exception:
        pass
    pane = os.environ.get("TMUX_PANE")
    if os.environ.get("TMUX") and pane and shutil.which("tmux"):
        run_tmux(action, pane)
    elif not in_vscode() and wt_exe() and (os.environ.get("WT_SESSION") or wt_is_default()):
        run_heartbeat(action, data, "wt")
    else:
        run_heartbeat(action, data, "window")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

#!/usr/bin/env python3
"""Claude Code hook for the waiting games (knight, dino - switch with M in game).
usage: hook.py start|notify|stop|end   - never prints, never fails the hook
  start  (you sent a prompt)      open the game or resume it
  notify (Claude needs an answer) pause with a banner
  stop   (Claude is waiting)      pause with a banner
  end    (session closed)         close the game

Where the game opens, first match wins:
  tmux              a pane below Claude (macOS, Linux, WSL)
  Windows Terminal  a split pane below Claude (Windows, or WSL inside Windows Terminal)
  vscode            a terminal in VS Code's panel, made by the companion extension in vscode/
                    (the VS Code extension, or `claude` in VS Code's terminal)
  window            its own terminal window - the desktop app, VS Code without the companion
                    extension, and any other terminal (Windows console, Linux desktop, macOS)"""
import json, os, platform, shutil, subprocess, sys, tempfile, time

HOME = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOME)
try:  # Windows: find the Claude window, bring it back. Optional: the game works without it.
    import winhost
except Exception:
    winhost = None
try:  # the companion VS Code extension (vscode/): game as a terminal in VS Code's panel
    import vscodebridge
except Exception:
    vscodebridge = None
GAME = os.path.join(HOME, "games.py")
TITLE = "Waiting games"
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


def entrypoint():
    return os.environ.get("CLAUDE_CODE_ENTRYPOINT", "").lower()


def host():
    """Where this Claude Code is running. Only a real terminal has a pane to split.
      terminal         a terminal running `claude` (WT, tmux, WSL, Terminal.app, ...)
      vscode-terminal  `claude` typed in VS Code's integrated terminal
      vscode           the VS Code extension (sets CLAUDE_CODE_ENTRYPOINT=claude-vscode)
      desktop          the Claude desktop app's Code tab, or any other non-terminal host
                       (anything that sets an entrypoint other than "cli")"""
    e, ep = os.environ, entrypoint()
    if "vscode" in ep:
        return "vscode"
    if ep not in ("", "cli"):
        return "desktop"
    if (e.get("TERM_PROGRAM") == "vscode" or "VSCODE_PID" in e
            or "VSCODE_IPC_HOOK" in e or "VSCODE_IPC_HOOK_CLI" in e):
        return "vscode-terminal"
    return "terminal"


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
    if mode == "window":
        try:
            save_host_window(state)
        except Exception:
            pass
    if mode == "wt":
        wt = wt_exe()
        if alive:
            spawn([wt, "-w", "0", "move-focus", "down"])
        else:
            spawn([wt, "-w", "0", "split-pane", "-H", "-s", "0.4", "--title", TITLE]
                  + game_cmd(state, "wt"))
    elif mode == "vscode":  # a terminal in VS Code's panel, made by the companion extension
        ext = vscode_extension(data)
        sent = ext and vscodebridge.send(ext, {
            "type": "show" if alive else "open", "state": state, "name": TITLE, "cwd": HOME,
            "cmd": [sys.executable, GAME, state, "vscode"]})
        if not sent and not alive:  # the extension went away since choose_mode()
            open_window(state)
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
    mode = choose_mode(data)
    log(action, data, mode)
    if mode == "window" and host() in ("vscode", "vscode-terminal"):
        _append("         no live Waiting Games VS Code extension for this window: "
                "separate window (install it with: python3 install.py vscode)")
    if mode == "tmux":
        run_tmux(action, os.environ["TMUX_PANE"])
    else:
        run_heartbeat(action, data, mode)


def choose_mode(data=None):
    """tmux | wt | vscode | window, from where Claude Code runs. The Windows Terminal split
    needs a terminal to split: a hook from the desktop app or the VS Code extension must
    never split whichever Windows Terminal window happens to be the most recent one.
    In VS Code the game goes into the panel if the companion extension is running."""
    kind, e = host(), os.environ
    if kind in ("terminal", "vscode-terminal") and e.get("TMUX") and e.get("TMUX_PANE") \
            and shutil.which("tmux"):
        return "tmux"
    if kind == "terminal" and wt_exe():
        # WT_SESSION is set inside Windows Terminal. Without it the console may still
        # have been handed to WT as the default terminal - but only trust that for a
        # plain CLI, whose entrypoint is exactly "cli".
        if e.get("WT_SESSION") or (entrypoint() == "cli" and wt_is_default()):
            return "wt"
    if kind in ("vscode", "vscode-terminal") and vscode_extension(data):
        return "vscode"
    return "window"


def vscode_extension(data):
    """pid of the live companion extension for this Claude, or None."""
    return vscodebridge.find_extension((data or {}).get("cwd")) if vscodebridge else None


# ------------------------------------------------------------------ diagnostics
LOG = os.path.join(tempfile.gettempdir(), "claude-games-hook.log")


def ancestors():
    """Names of the processes above this one (Windows only): python <- claude <- Code ..."""
    return ["%s(%d)" % (name, pid) for pid, name in winhost.process_chain()] if winhost else []


def _append(line):
    try:
        with open(LOG, encoding="utf-8") as f:
            lines = f.read().splitlines()[-199:]
    except OSError:
        lines = []
    try:
        with open(LOG, "w", encoding="utf-8") as f:
            f.write("\n".join(lines + [line.rstrip()]) + "\n")
    except OSError:
        pass


def log(action, data, mode):
    """One line per hook call in %TEMP%/claude-games-hook.log, so "the game didn't open"
    can be answered from facts: which host the hook saw and which way it chose."""
    try:
        e = os.environ
        _append("%s %-6s mode=%-6s host=%s entry=%s term=%s wt=%s tmux=%s session=%s chain=%s" % (
            time.strftime("%H:%M:%S"), action, mode, host(), entrypoint() or "-",
            e.get("TERM_PROGRAM", "-"), "y" if e.get("WT_SESSION") else "n",
            "y" if e.get("TMUX") else "n", (data.get("session_id") or "-")[:8],
            " < ".join(ancestors()) or "-"))
    except Exception:
        pass


def save_host_window(state):
    """Remember which window the prompt was typed in, so Enter in the game can go back."""
    if not winhost:
        return
    hwnd, how = winhost.find_host_window()
    if hwnd:
        with open(state + ".host", "w") as f:
            f.write(str(int(hwnd)))
    _append("         host window: %s%s" % (how, " exe=" + winhost.exe_name(hwnd) if hwnd else ""))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass

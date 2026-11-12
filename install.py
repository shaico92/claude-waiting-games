#!/usr/bin/env python3
"""Install / uninstall the waiting games WITHOUT the plugin system (old Claude Code, or
no access to GitHub). Prefer the plugin - see README.md.
  python3 install.py               install
  python3 install.py uninstall     remove
  python3 install.py terminal       Windows only: just make Windows Terminal the default
  python3 install.py terminal-undo  Windows only: put the old default terminal back
On Windows, install also makes Windows Terminal the default terminal (cmd, python,
anything that opens a console opens in Windows Terminal); uninstall undoes it."""
import json, os, shutil, sys

SRC = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.claude")
DEST = os.path.join(CLAUDE, "waiting-games", "app")
SETTINGS = os.path.join(CLAUDE, "settings.json")
MARKS = ("waiting-games/app/hook.py", "knight-game/hook.py", "knight-game/hooks/run.sh",
         "dino-game/hook.py")  # also removes the older knight/dino installs
EVENTS = {"UserPromptSubmit": "start", "Notification": "notify", "Stop": "stop", "SessionEnd": "end"}
FILES = ("hook.py", "games.py", "common.py", "winhost.py", os.path.join("hooks", "run.sh"),
         os.path.join("knight", "knight.py"), os.path.join("dino", "dino.py"))


# Windows Terminal's console/terminal handoff classes (from its AppxManifest). Setting
# them under HKCU\Console\%%Startup is what Settings > Default terminal application does.
CONSOLE_KEY = os.environ.get("KNIGHT_CONSOLE_KEY", r"Console\%%Startup")  # override = tests
WT_DELEGATION = {"DelegationConsole": "{2EACA947-7F5F-4CFA-BA87-8F7FBEEFBE69}",
                 "DelegationTerminal": "{E12CFF52-A866-4C77-9A90-F570A7AA2C6B}"}
TERMINAL_BACKUP = os.path.join(CLAUDE, "waiting-games-terminal-backup.json")


def default_terminal(use_wt):
    """Make Windows Terminal the default terminal, or restore what was there before."""
    if os.name != "nt":
        return
    import winreg
    if use_wt:
        if not shutil.which("wt"):
            print("Windows Terminal not found - install it first: winget install Microsoft.WindowsTerminal")
            return
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, CONSOLE_KEY)
        if not os.path.exists(TERMINAL_BACKUP):  # remember the original only once
            old = {}
            for name in WT_DELEGATION:
                try:
                    old[name] = winreg.QueryValueEx(key, name)[0]
                except OSError:
                    old[name] = None
            with open(TERMINAL_BACKUP, "w") as f:
                json.dump(old, f)
        for name, guid in WT_DELEGATION.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, guid)
        print("Windows Terminal is now the default terminal (typing cmd opens it).")
        return
    try:
        with open(TERMINAL_BACKUP) as f:
            old = json.load(f)
    except (OSError, ValueError):
        return  # we never changed it
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, CONSOLE_KEY)
    for name, value in old.items():
        if value is None:
            try:
                winreg.DeleteValue(key, name)
            except OSError:
                pass
        else:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
    os.remove(TERMINAL_BACKUP)
    print("Default terminal restored.")


def command(root, arg):
    """Same command as hooks/hooks.json: runs in bash/sh and in PowerShell (which Claude
    Code uses for hooks on Windows when Git Bash is missing)."""
    return ('echo `# <#` >/dev/null; sh "%s/hooks/run.sh" %s; exit 0 #> > $null; '
            "foreach ($p in 'python','py','python3') { if (Get-Command $p -ErrorAction SilentlyContinue) { "
            '$input | & $p "%s/hook.py" %s; if ($LASTEXITCODE -eq 0) { break } } }') % (root, arg, root, arg)


arg = sys.argv[1] if len(sys.argv) > 1 else ""
os.makedirs(CLAUDE, exist_ok=True)
if arg in ("terminal", "terminal-undo"):
    default_terminal(arg == "terminal")
    sys.exit(0)
uninstall = arg == "uninstall"
settings = {}
if os.path.exists(SETTINGS):
    with open(SETTINGS) as f:
        settings = json.load(f)
    shutil.copy(SETTINGS, SETTINGS + ".knight-backup")
hooks = settings.setdefault("hooks", {})

for ev in EVENTS:  # drop any earlier game hooks
    kept = [g for g in hooks.get(ev, [])
            if not any(m in h.get("command", "").replace("\\", "/")
                       for h in g.get("hooks", []) for m in MARKS)]
    if kept:
        hooks[ev] = kept
    else:
        hooks.pop(ev, None)

if uninstall:  # keep the high score file
    for name in FILES:
        try:
            os.remove(os.path.join(DEST, name))
        except OSError:
            pass
    for d in [os.path.join(DEST, x) for x in ("hooks", "knight", "dino")] + [DEST]:
        try:
            os.rmdir(d)  # only if empty: the high score stays
        except OSError:
            pass
else:
    for d in ("hooks", "knight", "dino"):
        os.makedirs(os.path.join(DEST, d), exist_ok=True)
    for name in FILES:
        shutil.copy(os.path.join(SRC, name), os.path.join(DEST, name))
    root = DEST.replace("\\", "/")  # forward slashes work in sh and PowerShell
    for ev, arg in EVENTS.items():
        hooks.setdefault(ev, []).append({"hooks": [{
            "type": "command", "command": command(root, arg), "timeout": 10}]})
if not hooks:
    settings.pop("hooks", None)
with open(SETTINGS, "w") as f:
    json.dump(settings, f, indent=2)
default_terminal(not uninstall)
print("Removed." if uninstall else
      "Installed. Restart Claude Code and send a prompt. (Using the plugin too? Then run "
      "`install.py uninstall`, or the game opens twice.)")

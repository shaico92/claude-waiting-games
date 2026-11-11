#!/usr/bin/env python3
"""Install / uninstall the knight game WITHOUT the plugin system (old Claude Code, or
no access to GitHub). Prefer the plugin - see README.md.
  python3 install.py            install
  python3 install.py uninstall  remove"""
import json, os, shutil, sys

SRC = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.claude")
DEST = os.path.join(CLAUDE, "knight-game")
SETTINGS = os.path.join(CLAUDE, "settings.json")
MARKS = ("knight-game/hook.py", "knight-game/hooks/run.sh", "dino-game/hook.py")  # also replaces dino
EVENTS = {"UserPromptSubmit": "start", "Notification": "notify", "Stop": "stop", "SessionEnd": "end"}
FILES = ("knight.py", "hook.py", os.path.join("hooks", "run.sh"))


def command(root, arg):
    """Same command as hooks/hooks.json: runs in bash/sh and in PowerShell (which Claude
    Code uses for hooks on Windows when Git Bash is missing)."""
    return ('echo `# <#` >/dev/null; sh "%s/hooks/run.sh" %s; exit 0 #> > $null; '
            "foreach ($p in 'python','py','python3') { if (Get-Command $p -ErrorAction SilentlyContinue) { "
            '$input | & $p "%s/hook.py" %s; if ($LASTEXITCODE -eq 0) { break } } }') % (root, arg, root, arg)


uninstall = len(sys.argv) > 1 and sys.argv[1] == "uninstall"
os.makedirs(CLAUDE, exist_ok=True)
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
else:
    os.makedirs(os.path.join(DEST, "hooks"), exist_ok=True)
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
print("Removed." if uninstall else
      "Installed. Restart Claude Code and send a prompt. (Using the plugin too? Then run "
      "`install.py uninstall`, or the game opens twice.)")

#!/usr/bin/env python3
"""Install / uninstall the Claude Code knight game.
  python3 install.py            install
  python3 install.py uninstall  remove"""
import json, os, shutil, sys

SRC = os.path.dirname(os.path.abspath(__file__))
CLAUDE = os.path.expanduser("~/.claude")
DEST = os.path.join(CLAUDE, "knight-game")
SETTINGS = os.path.join(CLAUDE, "settings.json")
MARKS = ("knight-game/hook.py", "dino-game/hook.py")  # also replaces the dino game
EVENTS = {"UserPromptSubmit": "start", "Notification": "notify", "Stop": "stop"}

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

if uninstall:
    shutil.rmtree(DEST, ignore_errors=True)
else:
    os.makedirs(DEST, exist_ok=True)
    for name in ("knight.py", "hook.py"):
        shutil.copy(os.path.join(SRC, name), os.path.join(DEST, name))
    # forward slashes work in both cmd and Git Bash, and keep MARKS matching on Windows
    py = sys.executable.replace("\\", "/")
    hook = os.path.join(DEST, "hook.py").replace("\\", "/")
    for ev, arg in EVENTS.items():
        hooks.setdefault(ev, []).append({"hooks": [{
            "type": "command",
            "command": '"%s" "%s" %s' % (py, hook, arg),
            "timeout": 5}]})
if not hooks:
    settings.pop("hooks", None)
with open(SETTINGS, "w") as f:
    json.dump(settings, f, indent=2)
if uninstall:
    print("Removed.")
elif os.name == "nt":
    print("Installed. Open Windows Terminal, run `claude` in it, and send a prompt.")
else:
    print("Installed. Start tmux, run `claude` inside it, and send a prompt.")

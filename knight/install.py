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
            if not any(m in h.get("command", "") for h in g.get("hooks", []) for m in MARKS)]
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
    for ev, arg in EVENTS.items():
        hooks.setdefault(ev, []).append({"hooks": [{
            "type": "command",
            "command": 'python3 "%s" %s' % (os.path.join(DEST, "hook.py"), arg),
            "timeout": 5}]})
if not hooks:
    settings.pop("hooks", None)
with open(SETTINGS, "w") as f:
    json.dump(settings, f, indent=2)
print("Removed." if uninstall else
      "Installed. Start tmux, run `claude` inside it, and send a prompt.")

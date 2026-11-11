# Claude Code dino game

A little jump-over-the-cactus game that pops up in a tmux pane while Claude Code is working.

## Needs
- macOS or Linux (or WSL), Python 3, tmux
- Claude Code started **inside tmux**

## Install
    python3 install.py
Then restart Claude Code. Remove with `python3 install.py uninstall`.
(Your settings.json is backed up to settings.json.dino-backup first.)

## Play
- Send a prompt: the game opens below Claude and takes focus.
- Space / Up = jump, p = pause, q = quit.
- When Claude finishes, a banner appears; Enter closes the game and returns you to Claude.
- If Claude needs a permission answer, a banner appears; Enter jumps to Claude and pauses the game.
  Switch back with your tmux prefix + arrow key.

Try the game alone: `python3 dino.py`

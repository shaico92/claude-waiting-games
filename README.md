# Claude Code waiting games

Small terminal games that open in a tmux pane under [Claude Code](https://claude.com/claude-code)
while it is working, driven by Claude Code hooks - like the offline dinosaur in Chrome.

| Game | What it is |
|---|---|
| [`knight/`](knight) | Knight vs Devils: move, jump, sword and shield against waves of devils. Pauses when Claude waits for your prompt and resumes on the next one. |
| [`dino/`](dino) | Jump-over-the-cactus runner. Closes when Claude is done. |

## Needs
macOS / Linux / WSL, Python 3, tmux, and Claude Code started inside tmux.

## Install one
    cd knight        # or: cd dino
    python3 install.py

Then restart Claude Code inside tmux and send a prompt. The installer copies the game to
`~/.claude/` and adds `UserPromptSubmit`, `Notification` and `Stop` hooks to
`~/.claude/settings.json` (a backup is saved first). Installing the knight game replaces
the dino hooks. Remove with `python3 install.py uninstall`.

Each game also runs standalone: `python3 knight/knight.py` or `python3 dino/dino.py`.

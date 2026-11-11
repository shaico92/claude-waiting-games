# Claude Code waiting games

Small terminal games that open next to [Claude Code](https://claude.com/claude-code)
while it is working, driven by Claude Code hooks - like the offline dinosaur in Chrome.

| Game | What it is |
|---|---|
| [`knight/`](knight) | Knight vs Devils: move, jump, sword and shield against waves of devils. Pauses when Claude waits for your prompt and resumes on the next one. |
| [`dino/`](dino) | Jump-over-the-cactus runner. Closes when Claude is done. |

## Knight - install as a plugin (Windows 10/11, Linux, WSL, macOS, VS Code)
    /plugin install knight-game --marketplace shaico92/testingProjects

Needs only Python 3. It opens in a tmux pane, a Windows Terminal split, or its own
window (VS Code extension, other terminals). Details in [`knight/`](knight).

## Dino - manual install (macOS / Linux / WSL, inside tmux)
    cd dino
    python3 install.py

Then restart Claude Code inside tmux and send a prompt. Installing dino replaces the
knight game's manual hooks (and the other way round). Remove with
`python3 install.py uninstall`.

Each game also runs standalone: `python3 knight/knight.py` or `python3 dino/dino.py`.

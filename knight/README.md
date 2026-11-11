# Knight vs Devils - a Claude Code waiting game

A 2D terminal brawler that opens under Claude Code while it works and pauses
whenever Claude is waiting for your prompt.

## Needs
macOS / Linux / WSL, Python 3, tmux, and Claude Code started **inside tmux**.

## Install
    python3 install.py
Restart Claude Code. This replaces the dino game's hooks if you installed it.
Remove with `python3 install.py uninstall` (settings.json is backed up first).

## Controls
| Key | Action |
|---|---|
| A / D or Left / Right | move |
| W, Up or Space | jump (over fireballs) |
| J or F | sword |
| K, S or Down (hold) | shield - blocks hits and fireballs from the side you face |
| P | pause / resume |
| Q | quit |

## How it flows
- Send a prompt: the game opens (or resumes) and takes focus.
- Claude finishes: the game pauses. Enter jumps back to Claude; your fight is kept
  and resumes on your next prompt. (P keeps playing anyway.)
- Claude asks for permission: the game pauses with a banner; Enter jumps to Claude.

## Enemies
- Imps: fast, one hit.
- Devils: two hits, throw fireballs from range.
- Brutes (wave 4+): five hits, hit for 2, can't be staggered - block them, then strike.
A "!" over an enemy means it is about to strike. Hearts (<3) heal you.

Try it alone: `python3 knight.py`

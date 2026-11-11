# Dino Run - a Claude Code waiting game

Jump over the cactuses for as long as you can. Part of the
[Claude Code waiting games](..) plugin - see there to install.

## Play
| Key | Action |
|---|---|
| Space, Up or W | jump |
| P | pause / resume |
| M or Tab | switch to another game |
| Q | quit |

It pauses when Claude finishes or asks you something (Enter jumps back to Claude) and
resumes on your next prompt. Best score is kept in `~/.claude/waiting-games/dino-highscore`.

Try it alone: `python3 dino/dino.py` from the repo root.

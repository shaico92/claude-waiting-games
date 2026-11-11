# Knight vs Devils - a Claude Code waiting game

A 2D terminal brawler that opens under Claude Code while it works and pauses
whenever Claude is waiting for your prompt.

## Install (plugin)
From any terminal (PowerShell, bash, WSL):

    claude plugin marketplace add shaico92/testingProjects
    claude plugin install knight-game@waiting-games

or inside Claude Code: `/plugin install knight-game --marketplace shaico92/testingProjects`
(type exactly that - nothing after it). Restart Claude Code and send a prompt.
Remove with `claude plugin uninstall knight-game`; update with `claude plugin update knight-game`.

Needs **Python 3** on the PATH (`python3`, `python` or `py`) - nothing else.
Used `install.py` before? Run `python install.py uninstall` first, or the game opens twice.
WSL and Windows are separate installs: run the two commands in each one you use.

## Setting up a new PC
**Windows 10 / 11** (PowerShell):

    winget install Python.Python.3.13
    winget install Git.Git
    winget install Microsoft.WindowsTerminal
    irm https://claude.ai/install.ps1 | iex

Then make Windows Terminal the default terminal, so `cmd`, `python` and anything else
that opens a console - including the game's own window - opens in Windows Terminal:

    $k = 'HKCU:\Console\%%Startup'; if (!(Test-Path $k)) { New-Item $k | Out-Null }
    Set-ItemProperty $k DelegationConsole '{2EACA947-7F5F-4CFA-BA87-8F7FBEEFBE69}'
    Set-ItemProperty $k DelegationTerminal '{E12CFF52-A866-4C77-9A90-F570A7AA2C6B}'

(Same as Windows Terminal > Settings > Startup > Default terminal application >
Windows Terminal. Works on Windows 11 and on Windows 10 22H2; to undo, set both values
to `{00000000-0000-0000-0000-000000000000}`, which means "let Windows decide".
`python install.py terminal` / `terminal-undo` does the same from a clone of this repo.)

Open a **new** Windows Terminal and run the two `claude plugin` commands above.

**Linux / WSL** (Ubuntu/Debian; Fedora: `dnf`):

    sudo apt install -y python3 git tmux
    curl -fsSL https://claude.ai/install.sh | bash

then the two `claude plugin` commands. Run `claude` inside `tmux` (or, in WSL, inside
Windows Terminal) for a split pane.

**VS Code**: set up the OS as above, then install the Claude Code extension. Plugins
are per user, so the extension picks up the game; it opens in its own window.

## Where it opens
| You run Claude Code in | The game opens |
|---|---|
| tmux (Linux, macOS, WSL) | a pane below Claude; Enter jumps back to Claude |
| Windows Terminal (Windows 10/11, or WSL inside it) | a split pane below Claude; Enter jumps back |
| a Start-menu / Run window (cmd, PowerShell, WSL) with Windows Terminal as the default terminal | a split pane below Claude, same as above |
| VS Code (the Claude extension, or `claude` in VS Code's terminal) | its own Windows Terminal / terminal window |
| any other terminal (Windows console, Linux desktop, macOS Terminal) | its own window |

A WSL or cmd window opened *before* Windows Terminal became the default terminal is an
old console that can't be split: close it and open a new one.

The game pauses when Claude finishes or asks you something, resumes on your next
prompt, and closes when the Claude session ends. In its own window there is no pane to
jump back to: click Claude (P keeps playing).

On Windows 10 without Windows Terminal the window is a classic console (still works);
`winget install Microsoft.WindowsTerminal` gives the split pane. On a Linux server with
no desktop (ssh) there is nowhere to open a window: use tmux.

Windows Terminal can't target a pane by id, so focus moves by direction: if you rearrange
panes, Enter may not land on Claude (just click it).

### Without the plugin system
    python3 install.py        # Windows: python install.py
copies the game to `~/.claude/knight-game` and adds the same hooks to
`~/.claude/settings.json` (backed up first). On Windows it also makes Windows Terminal
the default terminal (the old setting is saved and put back on uninstall).
Remove with `python3 install.py uninstall`.

## Controls
| Key | Action |
|---|---|
| A / D or Left / Right | move |
| W, Up or Space | jump (over fireballs) |
| J or F | sword - in the air it's a **downward stab** (2 damage, bounces you off) |
| K, S or Down (hold) | shield - blocks hits and fireballs from the side you face. Press it just before a hit lands to **parry**: a long stun, +1 MP, and fireballs fly back |
| 1 / 2 / 3 | pick a perk after a wave |
| U or E | **dash** (1 MP) - quick, invulnerable, cuts enemies you pass |
| I or R | **sword beam** (2 MP) - flies the way you face, pierces every enemy |
| L or G | **spin** (3 MP) - 2 damage to everything close on both sides, swats fireballs |
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
- Bats (wave 3+): fly at head height - the ground sword passes under them. Jump and
  stab, or use the beam or spin.
- Brutes (wave 4+): five hits, hit for 2, can't be staggered - block them, then strike.
- Bombers (wave 4+): walk up and light a fuse - back off, the shield won't help. The
  blast hurts other enemies too. Hitting one resets its fuse.
- Shield devils (wave 6+): their shield stops the sword and the beam. Block or parry
  them (the shield drops while they are stunned), or use spin, dash or an air stab.
- **Boss** every 5th wave: charges (block or dash through it), throws a fan of
  fireballs, and slams the ground (jump it). "!!" means a big attack is coming.

Enemies line up behind each other instead of stacking into one blob. A "!" over an
enemy means it is about to strike, "~" means it is stunned. Hearts (<3) heal you -
every wave drops exactly two; at full health one gives +1 MP instead.

## Combo
Kills less than 2.5 s apart build a combo: 2 kills score x2, 4 kills x3, 6+ kills x4.
Getting hit resets it.

## Perks
After each wave, pick one of three with 1 / 2 / 3 (the next wave waits for you):
+1 max HP, full heal, longer sword, +2 max MP, faster mana, free dash, double-damage
beam, wider spin. Perks last until you die.

## Mana
The MP bar (next to HP) holds 6 points. It refills one point every 2.5 s and one per
kill. A power you can't afford makes the bar blink.

Try it alone: `python3 knight.py` (Windows: `python knight.py`)

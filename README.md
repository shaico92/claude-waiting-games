# Claude Code waiting games

Small terminal games that open next to [Claude Code](https://claude.com/claude-code)
while it works, pause when Claude is waiting for you, and close when the session
ends - like the offline dinosaur in Chrome. One Claude Code plugin, two games:

| Game | What it is |
|---|---|
| [Knight vs Devils](knight) | sword, shield, parries and spells against waves of devils, brutes and a boss |
| [Dino Run](dino) | jump the cactuses for as long as you can |

**Switch games any time:** press **M** (or Tab) in a game to open the game menu, pick
one with Up/Down + Enter (or its number). Esc goes back. The plugin starts the game
you played last. Runs on Windows 10/11, Linux, WSL, macOS and in the VS Code extension.

## Install
From any terminal (PowerShell, bash, WSL):

    claude plugin marketplace add shaico92/claude-waiting-games
    claude plugin install waiting-games@claude-waiting-games

or inside Claude Code: `/plugin install waiting-games --marketplace shaico92/claude-waiting-games`
(type exactly that - nothing after it). Restart Claude Code and send a prompt.
Remove with `claude plugin uninstall waiting-games`; update with `claude plugin update waiting-games`.

Needs **Python 3** on the PATH (`python3`, `python` or `py`) - nothing else.
Had the older `knight-game` plugin (from shaico92/testingProjects)? Remove it first:
`claude plugin uninstall knight-game` and `claude plugin marketplace remove waiting-games`.
Used an `install.py` before? Run `python3 install.py uninstall` first, or a game opens twice.
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
`python3 install.py terminal` / `terminal-undo` does the same from a clone of this repo.)

Open a **new** Windows Terminal and run the two `claude plugin` commands above.

**Linux / WSL** (Ubuntu/Debian; Fedora: `dnf`):

    sudo apt install -y python3 git tmux
    curl -fsSL https://claude.ai/install.sh | bash

then the two `claude plugin` commands. Run `claude` inside `tmux` (or, in WSL, inside
Windows Terminal) for a split pane.

**VS Code** and the **Claude desktop app**: set up the OS as above, install the plugin,
and restart the app or the extension (or run `/reload-plugins`). Plugins are per user, so
both pick up the games; the game opens in its own window (see below).

## Where it opens
| You run Claude Code in | The game opens |
|---|---|
| tmux (Linux, macOS, WSL) | a pane below Claude; Enter jumps back to Claude |
| Windows Terminal (Windows 10/11, or WSL inside it) | a split pane below Claude; Enter jumps back |
| a Start-menu / Run window (cmd, PowerShell, WSL) with Windows Terminal as the default terminal | a split pane below Claude, same as above |
| VS Code (the Claude extension, or `claude` in VS Code's terminal) | its own Windows Terminal / terminal window; Enter jumps back to VS Code (Windows) |
| the Claude desktop app (Code tab, local sessions) | its own Windows Terminal / terminal window; Enter jumps back to the app (Windows) |
| any other terminal (Windows console, Linux desktop, macOS Terminal) | its own window |

The hook tells these apart by the `CLAUDE_CODE_ENTRYPOINT` Claude Code sets (`cli` for a
terminal, `claude-vscode` for the extension, anything else - the desktop app - is treated
as "no terminal to split"), so a prompt in the app or in VS Code never splits an unrelated
Windows Terminal window.

A WSL or cmd window opened *before* Windows Terminal became the default terminal is an
old console that can't be split: close it and open a new one.

The game pauses when Claude finishes or asks you something, resumes on your next
prompt, and closes when the Claude session ends. In its own window on Windows, Enter
brings the window you sent the prompt from back to the front; on macOS and Linux there is
no way to find it, so click Claude (P keeps playing).

### If the game doesn't open
The hook writes one line per call to `%TEMP%\claude-games-hook.log` (`/tmp/claude-games-hook.log`
elsewhere): which host it saw, which way it chose and, on Windows, the process chain and the
window it saved. No line at all means Claude Code never ran the hook - in the desktop app that
is a known gap in some versions, so use `python3 install.py` (hooks in `settings.json`, which
the app also reads) instead of the plugin. Plugins are not available in the desktop app's
WSL sessions.

On Windows 10 without Windows Terminal the window is a classic console (still works);
`winget install Microsoft.WindowsTerminal` gives the split pane. On a Linux server with
no desktop (ssh) there is nowhere to open a window: use tmux.

Windows Terminal can't target a pane by id, so focus moves by direction: if you rearrange
panes, Enter may not land on Claude (just click it).

### Without the plugin system
    python3 install.py
copies the games to `~/.claude/waiting-games/app` and adds the same hooks to
`~/.claude/settings.json` (backed up first). On Windows it also makes Windows Terminal
the default terminal (the old setting is saved and put back on uninstall).
Remove with `python3 install.py uninstall`.

Try a game without Claude: `python3 games.py` (the menu is on M).

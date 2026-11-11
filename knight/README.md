# Knight vs Devils - a Claude Code waiting game

A 2D terminal brawler that opens under Claude Code while it works and pauses
whenever Claude is waiting for your prompt.

## Needs
- macOS / Linux / WSL: Python 3, tmux, and Claude Code started **inside tmux**.
- Windows 10/11: Python 3 and Claude Code started **inside Windows Terminal**
  (`winget install Microsoft.WindowsTerminal` on Windows 10). No extra packages:
  on Windows the game draws with VT escape codes itself.

## Install
    python3 install.py        # Windows: python install.py
Restart Claude Code. This replaces the dino game's hooks if you installed it.
Remove with `python3 install.py uninstall` (settings.json is backed up first).
The hooks run with the Python that ran the installer.

### Windows Terminal notes
The game opens in a split pane below Claude. Windows Terminal can't target a pane by id,
so focus moves by direction: if you rearrange panes, Enter may not land on Claude
(just click it).

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

Try it alone: `python3 knight.py`

# Knight vs Devils - a Claude Code waiting game

A 2D terminal brawler that opens under Claude Code while it works and pauses
whenever Claude is waiting for your prompt.

Part of the [Claude Code waiting games](..) plugin - install, setup and where the
game opens are described there. Press **M** in game to switch to another game.

## Controls
| Key | Action |
|---|---|
| A / D or Left / Right | move |
| W, Up or Space | jump (over fireballs) |
| J or F | sword - in the air it's a **downward stab** (2 damage, bounces you off) |
| K, S or Down (hold) | shield - blocks hits and fireballs from the side you face. Press it just before a hit lands to **parry**: a long stun, +1 MP, and fireballs fly back |
| 1 / 2 / 3 | pick a perk after a wave |
| H or ? | **how to play** - controls, skills and enemies (pauses the game) |
| T | **swap weapon** - sword, spear (long reach, slower), hammer (short, slow, 2 damage, breaks guard shields, staggers brutes) |
| X | **combo finisher** - after a 6-kill combo: a free slash across the whole screen (3 damage to everything). Earned again every 6 kills of combo; lost if the combo breaks |
| U or E | **dash** (1 MP) - quick, invulnerable, cuts enemies you pass |
| I or R | **sword beam** (2 MP) - flies the way you face, pierces every enemy |
| L or G | **spin** (3 MP) - 2 damage to everything close on both sides, swats fireballs |
| P | pause / resume |
| Q | quit |

Hold A/D (or the arrows) to keep running: terminals send no key-up, so the game reads your
OS key-repeat delay and rate (Windows settings) and keeps the knight going while repeats
arrive. A single tap walks a few cells at half pace. A jump pressed just before landing still counts.

## How it flows
- Send a prompt: the game opens (or resumes) and takes focus.
- Claude finishes: the game pauses. Enter jumps back to Claude; your fight is kept
  and resumes on your next prompt. (P keeps playing anyway.)
- Claude asks for permission: the game pauses with a banner; Enter jumps to Claude.

## Enemies
- Imps: fast, one hit.
- **Elite** (waves 3, 8, 13...): a gold brute with double HP, an "E" over its head, triple
  score and a guaranteed powerup.
- **Scene enemies:** cave **spiders** lower themselves from the ceiling (air stab or spin them
  on the way down; they hurt if they land on you), frost **rollers** roll across the ground
  (jump, block or cut them), lava **fire imps** leave flames on the ground for 3 s.
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
  The boss follows the scene and adds one move of its own:
  - **Devil King** (meadow) - calls imps to its side.
  - **Cave Tyrant** - stalactites rain around you; step out of the warnings.
  - **Frost Warden** - slides all the way to the wall (dodge it, jump it or dash), then sits
    stunned for a couple of seconds: that is your window.
  - **Magma Golem** - a line of geysers marches at you; jump them.

Enemies line up behind each other instead of stacking into one blob. A "!" over an
enemy means it is about to strike, "~" means it is stunned. Hearts (<3) heal you -
every wave drops exactly two; at full health one gives +1 MP instead.

## Scenes
The stage changes every 3 waves with a curtain wipe and a title: **Meadow** (1-3), **Cave** (4-6),
**Frost** (7-9), **Lava** (10-12), then it starts over. Each one has its own backdrop, weather and
ground, and a rule that goes with it:
- **Cave** - stalactites fall (the warning "vVv" shows at the ceiling; they crush enemies too, so lure
  them under one). Bats are more common, and shield drops are more likely.
- **Frost** - the floor is ice: slow to start, slow to turn, a long glide. Guards turn up earlier
  and haste drops are more likely; dash helps.
- **Lava** - geysers erupt after a warning on the ground ("^^^"). Jump them. They burn enemies too.
  Bombers turn up earlier and mana drops are more likely.
A shield powerup absorbs a hazard hit like any other.

## Powerups
Kills drop them (one per wave, two on boss waves); walk over one within 12 s:
- **(S) Shield** - absorbs the next hit (brackets show around the knight).
- **(R) Rage** - 8 s of +1 damage on sword, stab and beam, and faster swings.
- **(H) Haste** - 8 s of faster running and twice the mana regen.
- **(M) Mana** - refills all MP. Only drops when you are short on mana.

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

Try it alone: `python3 knight/knight.py` from the repo root.

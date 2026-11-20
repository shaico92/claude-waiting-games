// The waiting games' line under the prompt (beside the mode label) and the /games
// command that silences them until you bring them back. No model turn is used.
//
// The hook (hook.py) reads the same file: ~/.claude/waiting-games/muted, "1" = silenced.
// Claude Code versions without hooks modules skip this file; the games still work.
import type { EngineInterface as Engine, Register } from 'claude-code'

async function home($: Engine): Promise<string> {
  return (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? '.'
}

async function tempDir($: Engine): Promise<string> {
  // the folder Python's tempfile.gettempdir() picks, in the same order
  return (await $.env.get('TMPDIR')) ?? (await $.env.get('TEMP')) ?? (await $.env.get('TMP')) ?? '/tmp'
}

async function mutedPath($: Engine): Promise<string> {
  return `${await home($)}/.claude/waiting-games/muted`
}

async function isMuted($: Engine): Promise<boolean> {
  try {
    return (await $.fs.read(await mutedPath($))).trim() === '1'
  } catch {
    return false
  }
}

function show($: any, muted: boolean): void {
  $.ui.status(muted ? 'games silenced · /games on' : 'games on · /games off')
}

/** Close the game open on this PC, if any (it beats into claude-waiting-games.alive). */
async function closeOpenGame($: Engine): Promise<boolean> {
  const live = `${await tempDir($)}/claude-waiting-games.alive`
  try {
    const st = await $.fs.stat(live)
    if ((await $.clock.now()) - st.mtimeMs > 3000) return false
    const state = (await $.fs.read(live)).trim()
    if (!state) return false
    await $.fs.write(state, 'quit')
    return true
  } catch {
    return false
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'games',
      description: 'Waiting games: /games off silences them until /games on',
      argumentHint: '[on|off]',
      immediate: true,
    })
    show($, await isMuted($))
    return next(e)
  })

  on('command.run', { command: 'games' }, async ($, e) => {
    const arg = e.args.trim().toLowerCase()
    const was = await isMuted($)
    let muted: boolean
    if (arg === 'off' || arg === 'silence' || arg === 'mute') muted = true
    else if (arg === 'on' || arg === 'unmute') muted = false
    else if (arg === '') muted = !was
    else return { text: 'Use /games off to silence the waiting games, /games on to bring them back.' }

    await $.fs.write(await mutedPath($), muted ? '1' : '0')
    show($, muted)
    if (muted) {
      const closed = await closeOpenGame($)
      return { text: `Waiting games silenced${closed ? ' and closed' : ''}. Type /games on to bring them back.` }
    }
    return { text: 'Waiting games are back: one opens with your next prompt.' }
  })

  // The game's own menu can silence too (X): pick that up on the next prompt.
  on('prompt.submit', async ($, e, next) => {
    show($, await isMuted($))
    return next(e)
  }).catch(($, e, next) => next(e)) // never hold up a prompt
}

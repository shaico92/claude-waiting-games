import { expect, test } from 'claude-code/testing'

// A tiny fake disk and environment: each hook below stands for the engine.
// The engine hands paths over made absolute (C:/h/... with backslashes on Windows): compare as /h/...
const norm = (p: string) => p.split(String.fromCharCode(92)).join('/').replace(/^[A-Za-z]:/, '')

function fakeHost(on: any, files: Record<string, string>, now = 10_000) {
  const statuses: (string | undefined)[] = []
  on('env.get', (_: unknown, e: { name: string }) => ({
    value: ({ USERPROFILE: '/h', TEMP: '/t' } as Record<string, string>)[e.name],
  }))
  on('fs.read', (_: unknown, e: { path: string }) => {
    if (!(norm(e.path) in files)) throw new Error('ENOENT')
    return { value: files[norm(e.path)] }
  })
  on('fs.write', (_: unknown, e: { path: string; text: string }) => {
    files[norm(e.path)] = e.text
    return { value: undefined }
  })
  on('fs.stat', (_: unknown, e: { path: string }) => {
    if (!(norm(e.path) in files)) throw new Error('ENOENT')
    return { value: { kind: 'file', size: 1, mtimeMs: now - 1000, isLink: false } }
  })
  on('clock.now', () => ({ value: now }))
  on('ui.status', (_: unknown, e: { text: string | undefined }) => {
    statuses.push(e.text)
    return { value: undefined }
  })
  on('command.register', () => ({ value: { command: 'games' } }))
  on('session.start', (_: unknown, e: { cwd: string }) => ({ cwd: e.cwd }))
  on('prompt.submit', (_: unknown, e: unknown) => e)
  return statuses
}

const MUTED = '/h/.claude/waiting-games/muted'

test('the status line says the games are on, and /games off silences them', async ($, on) => {
  const files: Record<string, string> = {}
  const statuses = fakeHost(on, files)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  expect(statuses.at(-1)).toBe('games on · /games off')

  const ran = await $.command.run({ command: 'games', args: 'off' })
  expect(files[MUTED]).toBe('1')
  expect(statuses.at(-1)).toBe('games silenced · /games on')
  expect(ran.text).toContain('/games on')
})

test('/games off closes the open game; /games on brings them back', async ($, on) => {
  const files: Record<string, string> = {
    '/t/claude-waiting-games.alive': '/t/claude-knight-wt-A.state',
    '/t/claude-knight-wt-A.state': 'run',
  }
  const statuses = fakeHost(on, files)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  await $.command.run({ command: 'games', args: 'off' })
  expect(files['/t/claude-knight-wt-A.state']).toBe('quit')

  await $.command.run({ command: 'games', args: 'on' })
  expect(files[MUTED]).toBe('0')
  expect(statuses.at(-1)).toBe('games on · /games off')
})

test('/games alone toggles, and silencing from the game menu shows on the next prompt', async ($, on) => {
  const files: Record<string, string> = {}
  const statuses = fakeHost(on, files)
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.command.run({ command: 'games', args: '' })
  expect(files[MUTED]).toBe('1')
  await $.command.run({ command: 'games', args: '' })
  expect(files[MUTED]).toBe('0')

  files[MUTED] = '1' // X in the game's menu wrote this
  await $.prompt.submit({ text: 'hi' })
  expect(statuses.at(-1)).toBe('games silenced · /games on')
})

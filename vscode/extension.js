'use strict';
// Companion for the waiting-games Claude Code plugin: opens the game as a terminal in
// VS Code's panel instead of a separate window, and puts you back in the Claude chat
// when you press Enter in the game. Plain JavaScript, no dependencies.
//
// Protocol (shared with vscodebridge.py): a spool folder of small JSON files.
//   ext-<pid>.json        written here every 2 s: my extension-host pid + workspace folders
//   req-<pid>-<ns>.json   requests for me from the hook or the game:
//                           {type:"open",  state, cmd:[exe, ...args], cwd, name}  start the game
//                           {type:"show",  state}                                  bring it forward
//                           {type:"focus-claude"}                                  back to the chat
const vscode = require('vscode');
const fs = require('fs');
const os = require('os');
const path = require('path');

const SPOOL = process.env.WAITING_GAMES_SPOOL || path.join(os.tmpdir(), 'claude-games-vscode');
const POLL_MS = 400;
const PRESENCE_MS = 2000;
const MAX_AGE_MS = 30000;
const CLAUDE_FOCUS = 'claude-vscode.focus'; // "Claude Code: Focus input"

const me = () => String(process.pid);
let presenceFile = null;
let timers = [];
const terminals = new Map(); // state file -> vscode.Terminal

function writeAtomic(file, text) {
  const tmp = file + '.tmp' + process.pid;
  fs.writeFileSync(tmp, text);
  fs.renameSync(tmp, file);
}

function writePresence() {
  try {
    fs.mkdirSync(SPOOL, { recursive: true });
    writeAtomic(presenceFile, JSON.stringify({
      pid: process.pid,
      workspaces: (vscode.workspace.workspaceFolders || []).map((f) => f.uri.fsPath),
      ts: Date.now(),
    }));
  } catch (e) {
    // the hook then sees no live extension and falls back to a separate window
  }
}

function openGame(req) {
  if (!req.state || !Array.isArray(req.cmd) || req.cmd.length === 0) return;
  const old = terminals.get(req.state);
  if (old && old.exitStatus === undefined) {
    old.show(false); // already running (a quick second prompt): just bring it forward
    return;
  }
  const term = vscode.window.createTerminal({
    name: req.name || 'Waiting games',
    shellPath: req.cmd[0],
    shellArgs: req.cmd.slice(1),
    cwd: req.cwd || undefined,
    env: { WAITING_GAMES_EXT: me(), WAITING_GAMES_SPOOL: SPOOL },
    iconPath: new vscode.ThemeIcon('game'),
    location: vscode.TerminalLocation.Panel,
  });
  terminals.set(req.state, term);
  term.show(false); // false = take focus, so the game is playable at once
}

function handle(req) {
  switch (req && req.type) {
    case 'open':
      openGame(req);
      break;
    case 'show': {
      const t = terminals.get(req.state);
      if (t && t.exitStatus === undefined) t.show(false);
      break;
    }
    case 'focus-claude':
      Promise.resolve(vscode.commands.executeCommand(CLAUDE_FOCUS)).catch(() => {});
      break;
    default:
      break;
  }
}

function tick() {
  let names;
  try {
    names = fs.readdirSync(SPOOL);
  } catch (e) {
    return;
  }
  const prefix = 'req-' + me() + '-';
  for (const name of names.filter((n) => n.startsWith(prefix) && n.endsWith('.json')).sort()) {
    const file = path.join(SPOOL, name);
    let req = null;
    try {
      req = JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch (e) {
      req = null; // half-written or garbage: drop it
    }
    try {
      fs.unlinkSync(file);
    } catch (e) {
      // already gone
    }
    if (req && Date.now() - (req.ts || 0) <= MAX_AGE_MS) handle(req);
  }
}

function activate(context) {
  presenceFile = path.join(SPOOL, 'ext-' + me() + '.json');
  writePresence();
  timers.push(setInterval(writePresence, PRESENCE_MS), setInterval(tick, POLL_MS));
  context.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(writePresence),
    vscode.window.onDidCloseTerminal((t) => {
      for (const [state, term] of terminals) if (term === t) terminals.delete(state);
    })
  );
}

function deactivate() {
  timers.forEach(clearInterval);
  timers = [];
  try {
    fs.unlinkSync(presenceFile);
  } catch (e) {
    // already gone
  }
}

module.exports = { activate, deactivate, _tick: tick, _terminals: terminals };

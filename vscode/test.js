'use strict';
// node vscode/test.js  -  runs extension.js against a stand-in for the VS Code API.
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const Module = require('module');

const spool = fs.mkdtempSync(path.join(os.tmpdir(), 'wg-spool-'));
process.env.WAITING_GAMES_SPOOL = spool;

// ---- the stand-in for the `vscode` module
const calls = { terminals: [], commands: [] };
let closeHandler = null;
const mock = {
  workspace: {
    workspaceFolders: [{ uri: { fsPath: 'C:\\work\\proj' } }],
    onDidChangeWorkspaceFolders: () => ({ dispose() {} }),
  },
  window: {
    createTerminal(opts) {
      const t = { opts, exitStatus: undefined, shows: [], show(preserve) { this.shows.push(preserve); } };
      calls.terminals.push(t);
      return t;
    },
    onDidCloseTerminal(fn) { closeHandler = fn; return { dispose() {} }; },
  },
  commands: { executeCommand: async (id) => { calls.commands.push(id); } },
  ThemeIcon: class { constructor(id) { this.id = id; } },
  TerminalLocation: { Panel: 1, Editor: 2 },
};
const load = Module._load;
Module._load = function (request, ...rest) {
  return request === 'vscode' ? mock : load.call(this, request, ...rest);
};
const ext = require('./extension.js');

const ME = String(process.pid);
let n = 0;
function request(payload, pid = ME, ts = Date.now()) {
  const file = path.join(spool, `req-${pid}-${String(++n).padStart(19, '0')}.json`);
  fs.writeFileSync(file, JSON.stringify(Object.assign({ ts }, payload)));
  return file;
}
const open = (state = 'S1') => ({ type: 'open', state, cmd: ['python3', 'games.py', state, 'vscode'], cwd: 'C:\\g', name: 'Waiting games' });

const tests = {
  'writes a presence file with its pid and workspaces'() {
    ext.activate({ subscriptions: [] });
    const info = JSON.parse(fs.readFileSync(path.join(spool, `ext-${ME}.json`), 'utf8'));
    assert.strictEqual(info.pid, process.pid);
    assert.deepStrictEqual(info.workspaces, ['C:\\work\\proj']);
  },
  'open creates a panel terminal that runs the game and takes focus'() {
    const f = request(open());
    ext._tick();
    assert.strictEqual(calls.terminals.length, 1);
    const t = calls.terminals[0];
    assert.strictEqual(t.opts.shellPath, 'python3');
    assert.deepStrictEqual(t.opts.shellArgs, ['games.py', 'S1', 'vscode']);
    assert.strictEqual(t.opts.location, mock.TerminalLocation.Panel);
    assert.strictEqual(t.opts.env.WAITING_GAMES_EXT, ME);
    assert.strictEqual(t.opts.env.WAITING_GAMES_SPOOL, spool);
    assert.strictEqual(t.opts.name, 'Waiting games');
    assert.deepStrictEqual(t.shows, [false]);
    assert.ok(!fs.existsSync(f), 'request file is consumed');
  },
  'a second open for the same game reuses the terminal'() {
    request(open());
    ext._tick();
    assert.strictEqual(calls.terminals.length, 1);
    assert.deepStrictEqual(calls.terminals[0].shows, [false, false]);
  },
  'show brings the terminal forward, and ignores unknown games'() {
    request({ type: 'show', state: 'S1' });
    request({ type: 'show', state: 'nope' });
    ext._tick();
    assert.strictEqual(calls.terminals[0].shows.length, 3);
  },
  'focus-claude runs the Claude extension focus command'() {
    request({ type: 'focus-claude' });
    ext._tick();
    assert.deepStrictEqual(calls.commands, ['claude-vscode.focus']);
  },
  'requests for another window are left alone'() {
    const f = request(open('S2'), '999999');
    ext._tick();
    assert.ok(fs.existsSync(f));
    assert.strictEqual(calls.terminals.length, 1);
    fs.unlinkSync(f);
  },
  'stale and garbage requests are dropped without effect'() {
    const old = request(open('S3'), ME, Date.now() - 60000);
    const bad = path.join(spool, `req-${ME}-9999999999999999999.json`);
    fs.writeFileSync(bad, '{not json');
    ext._tick();
    assert.ok(!fs.existsSync(old) && !fs.existsSync(bad));
    assert.strictEqual(calls.terminals.length, 1);
  },
  'an exited game gets a fresh terminal'() {
    calls.terminals[0].exitStatus = { code: 0 };
    request(open());
    ext._tick();
    assert.strictEqual(calls.terminals.length, 2);
  },
  'a closed terminal is forgotten'() {
    closeHandler(calls.terminals[1]);
    assert.strictEqual(ext._terminals.size, 0);
    request(open());
    ext._tick();
    assert.strictEqual(calls.terminals.length, 3);
  },
  'requests are handled in the order they were written'() {
    const before = calls.commands.length;
    request({ type: 'focus-claude' });
    request(open('S9'));
    ext._tick();
    assert.strictEqual(calls.commands.length, before + 1);
    assert.strictEqual(calls.terminals[calls.terminals.length - 1].opts.shellArgs[1], 'S9');
  },
  'deactivate removes the presence file'() {
    ext.deactivate();
    assert.ok(!fs.existsSync(path.join(spool, `ext-${ME}.json`)));
  },
};

let failed = 0;
for (const [name, fn] of Object.entries(tests)) {
  try {
    fn();
    console.log('ok   ' + name);
  } catch (e) {
    failed++;
    console.log('FAIL ' + name + '\n     ' + e.message);
  }
}
fs.rmSync(spool, { recursive: true, force: true });
console.log(failed ? `${failed} failed` : `all ${Object.keys(tests).length} passed`);
process.exit(failed ? 1 : 0);

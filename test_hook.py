#!/usr/bin/env python3
"""Which way does hook.py open the game, for each place Claude Code can run?  python3 test_hook.py"""
import json, os, pathlib, sys, tempfile, time, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_argv, sys.argv = sys.argv, sys.argv[:1]   # common.py reads the game's arguments from argv
import common, hook, vscodebridge, winhost
sys.argv = _argv

NOISE = ("CLAUDE_CODE_ENTRYPOINT", "TERM_PROGRAM", "WT_SESSION", "TMUX", "TMUX_PANE",
         "VSCODE_PID", "VSCODE_IPC_HOOK", "VSCODE_IPC_HOOK_CLI")


def route(env, wt=True, default_terminal=False, tmux=True):
    """The mode choose_mode() picks with exactly this environment."""
    keep = {k: v for k, v in os.environ.items() if k not in NOISE}
    keep.update(env)
    with mock.patch.dict(os.environ, keep, clear=True), \
            mock.patch.object(hook, "wt_exe", lambda: "wt" if wt else None), \
            mock.patch.object(hook, "wt_is_default", lambda: default_terminal), \
            mock.patch.object(hook.shutil, "which", lambda n: "tmux" if (tmux and n == "tmux") else None):
        return hook.choose_mode(), hook.host()


CLI = {"CLAUDE_CODE_ENTRYPOINT": "cli"}
WTENV = {"WT_SESSION": "abc"}
TMUXENV = {"TMUX": "/tmp/tmux-1/default,1,0", "TMUX_PANE": "%3"}


class Terminals(unittest.TestCase):
    def test_windows_terminal_splits(self):
        self.assertEqual(route({**CLI, **WTENV}), ("wt", "terminal"))

    def test_tmux_wins_over_everything(self):
        self.assertEqual(route({**CLI, **WTENV, **TMUXENV}), ("tmux", "terminal"))

    def test_tmux_without_the_binary_falls_back(self):
        self.assertEqual(route({**CLI, **TMUXENV}, wt=False, tmux=False), ("window", "terminal"))

    def test_plain_console_with_wt_as_default_terminal(self):
        self.assertEqual(route(CLI, default_terminal=True), ("wt", "terminal"))

    def test_plain_console_without_wt(self):
        self.assertEqual(route(CLI, default_terminal=False), ("window", "terminal"))
        self.assertEqual(route({**CLI, **WTENV}, wt=False), ("window", "terminal"))

    def test_old_cli_without_entrypoint_still_splits_inside_wt(self):
        self.assertEqual(route(WTENV), ("wt", "terminal"))
        # ...but "default terminal" alone is not enough without the cli entrypoint
        self.assertEqual(route({}, default_terminal=True), ("window", "terminal"))


class GuiHosts(unittest.TestCase):
    def test_vscode_extension(self):
        for extra in ({}, WTENV, TMUXENV, {"TERM_PROGRAM": "vscode"}):
            self.assertEqual(route({"CLAUDE_CODE_ENTRYPOINT": "claude-vscode", **extra},
                                   default_terminal=True), ("window", "vscode"), extra)

    def test_vscode_integrated_terminal(self):
        env = {**CLI, "TERM_PROGRAM": "vscode"}
        self.assertEqual(route(env, default_terminal=True), ("window", "vscode-terminal"))
        self.assertEqual(route({**env, "VSCODE_PID": "42"}), ("window", "vscode-terminal"))
        # a tmux pane inside that terminal is a pane we can split
        self.assertEqual(route({**env, **TMUXENV}), ("tmux", "vscode-terminal"))

    def test_desktop_app_never_splits_a_terminal(self):
        """The bug: WT as the default terminal made every desktop-app prompt split
        whichever Windows Terminal window was most recent."""
        for entry in ("claude-desktop", "local-agent", "sdk-ts"):
            for extra in ({}, WTENV, TMUXENV):
                self.assertEqual(route({"CLAUDE_CODE_ENTRYPOINT": entry, **extra},
                                       default_terminal=True), ("window", "desktop"), (entry, extra))


class Diagnostics(unittest.TestCase):
    def test_log_is_written_and_capped(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hook, "LOG", os.path.join(d, "h.log")):
            for i in range(250):
                hook.log("start", {"session_id": "s%07d" % i}, "window")
            with open(hook.LOG, encoding="utf-8") as f:
                lines = f.read().splitlines()
            self.assertEqual(len(lines), 200)
            self.assertIn("s0000249", lines[-1])
            self.assertIn("mode=window", lines[-1])

    def test_log_never_raises(self):
        with mock.patch.object(hook, "LOG", os.path.join("no", "such", "dir", "h.log")):
            hook.log("start", {}, "wt")

    @unittest.skipUnless(os.name == "nt", "process chain lookup is Windows only")
    def test_ancestors_sees_this_process(self):
        chain = hook.ancestors()
        self.assertTrue(chain and "python" in chain[0].lower(), chain)


class VSCodePanel(unittest.TestCase):
    """The game as a terminal in VS Code's panel, via the companion extension."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        p = mock.patch.object(vscodebridge, "SPOOL", self.dir.name)
        p.start()
        self.addCleanup(p.stop)
        self.state = os.path.join(self.dir.name, "x.state")

    def presence(self, pid, workspaces=(), age=0):
        path = os.path.join(self.dir.name, "ext-%d.json" % pid)
        with open(path, "w") as f:
            json.dump({"pid": pid, "workspaces": list(workspaces), "ts": 0}, f)
        if age:
            t = time.time() - age
            os.utime(path, (t, t))

    def requests(self):
        out = []
        for name in sorted(os.listdir(self.dir.name)):
            if name.startswith("req-"):
                with open(os.path.join(self.dir.name, name)) as f:
                    out.append(json.load(f))
        return out

    # ---- finding the right window
    def test_exact_match_by_ancestor_pid(self):
        self.presence(4242, ["C:\\other"])
        self.presence(5555, ["C:\\proj"])
        self.assertEqual(vscodebridge.find_extension("C:\\proj", chain=[1, 4242, 7]), 4242)

    def test_falls_back_to_the_one_window_holding_the_cwd(self):
        self.presence(5555, ["C:\\proj"])
        self.presence(6666, ["C:\\elsewhere"])
        self.assertEqual(vscodebridge.find_extension("C:\\proj\\sub\\dir", chain=[1]), 5555)
        if os.name == "nt":  # Windows paths are case-insensitive
            self.assertEqual(vscodebridge.find_extension("c:\\PROJ", chain=[1]), 5555)

    def test_ambiguous_or_unknown_is_none(self):
        self.presence(5555, ["C:\\proj"])
        self.presence(6666, ["C:\\proj"])      # two windows on the same folder
        self.assertIsNone(vscodebridge.find_extension("C:\\proj", chain=[1]))
        self.assertIsNone(vscodebridge.find_extension("D:\\nowhere", chain=[1]))
        self.assertIsNone(vscodebridge.find_extension(None, chain=[1]))

    def test_stale_presence_is_ignored(self):
        self.presence(4242, ["C:\\proj"], age=60)   # a window that was closed
        self.assertIsNone(vscodebridge.find_extension("C:\\proj", chain=[4242]))

    def test_no_spool_folder_is_fine(self):
        with mock.patch.object(vscodebridge, "SPOOL", os.path.join(self.dir.name, "missing")):
            self.assertIsNone(vscodebridge.find_extension("C:\\proj", chain=[1]))

    # ---- routing
    def route(self, env, data=None):
        keep = {k: v for k, v in os.environ.items() if k not in NOISE}
        keep.update(env)
        with mock.patch.dict(os.environ, keep, clear=True), \
                mock.patch.object(hook, "wt_exe", lambda: "wt"), \
                mock.patch.object(hook, "wt_is_default", lambda: True), \
                mock.patch.object(hook.shutil, "which", lambda n: None):
            return hook.choose_mode(data)

    def test_vscode_uses_the_panel_when_the_extension_is_running(self):
        self.presence(5555, ["C:\\proj"])
        data = {"cwd": "C:\\proj"}
        self.assertEqual(self.route({"CLAUDE_CODE_ENTRYPOINT": "claude-vscode"}, data), "vscode")
        self.assertEqual(self.route({"CLAUDE_CODE_ENTRYPOINT": "cli", "TERM_PROGRAM": "vscode"}, data), "vscode")

    def test_vscode_without_the_extension_keeps_the_separate_window(self):
        self.assertEqual(self.route({"CLAUDE_CODE_ENTRYPOINT": "claude-vscode"}, {"cwd": "C:\\proj"}), "window")

    def test_other_hosts_never_use_the_panel(self):
        self.presence(5555, ["C:\\proj"])
        data = {"cwd": "C:\\proj"}
        self.assertEqual(self.route({"CLAUDE_CODE_ENTRYPOINT": "claude-desktop"}, data), "window")
        self.assertEqual(self.route({"CLAUDE_CODE_ENTRYPOINT": "cli", "WT_SESSION": "x"}, data), "wt")

    # ---- what the hook sends
    def run_start(self, data, alive, ext_alive=True):
        with mock.patch.object(hook.tempfile, "gettempdir", lambda: self.dir.name), \
                mock.patch.object(hook, "open_window") as win:
            if alive:
                path = os.path.join(self.dir.name, "claude-knight-vscode-%s.state" % data["session_id"])
                open(path + ".alive", "w").close()
            hook.run_heartbeat("start", data, "vscode")
        return win

    def test_start_asks_the_extension_to_open_the_game(self):
        self.presence(5555, ["C:\\proj"])
        win = self.run_start({"session_id": "s1", "cwd": "C:\\proj"}, alive=False)
        (req,) = self.requests()
        self.assertEqual(req["type"], "open")
        self.assertEqual(req["cmd"][1:], [hook.GAME, req["state"], "vscode"])
        self.assertTrue(req["state"].endswith("claude-knight-vscode-s1.state"))
        win.assert_not_called()

    def test_start_while_the_game_runs_just_shows_it(self):
        self.presence(5555, ["C:\\proj"])
        self.run_start({"session_id": "s2", "cwd": "C:\\proj"}, alive=True)
        self.assertEqual([r["type"] for r in self.requests()], ["show"])

    def test_extension_gone_falls_back_to_a_window(self):
        win = self.run_start({"session_id": "s3", "cwd": "C:\\proj"}, alive=False)
        self.assertEqual(self.requests(), [])
        win.assert_called_once()

    # ---- the game's side: Enter goes back to the chat
    def test_enter_in_the_game_focuses_the_claude_chat(self):
        with mock.patch.object(common, "CLAUDE_PANE", "vscode"), \
                mock.patch.dict(os.environ, {"WAITING_GAMES_EXT": "5555"}):
            self.assertTrue(common.can_focus())
            common.focus_claude()
        (req,) = self.requests()
        self.assertEqual(req["type"], "focus-claude")
        self.assertIn("req-5555-", [n for n in os.listdir(self.dir.name) if n.startswith("req-")][0])

    def test_focus_without_the_env_var_does_nothing(self):
        env = {k: v for k, v in os.environ.items() if k != "WAITING_GAMES_EXT"}
        with mock.patch.object(common, "CLAUDE_PANE", "vscode"), mock.patch.dict(os.environ, env, clear=True):
            common.focus_claude()
        self.assertEqual(self.requests(), [])


@unittest.skipUnless(os.name == "nt", "window focus is Windows only")
class GoBackToClaude(unittest.TestCase):
    def test_process_chain_starts_with_us(self):
        chain = winhost.process_chain()
        self.assertEqual(chain[0][0], os.getpid())
        self.assertTrue(all(isinstance(p, int) and n for p, n in chain))

    def test_finds_some_window_or_says_why(self):
        hwnd, how = winhost.find_host_window()
        self.assertTrue(hwnd is None or isinstance(hwnd, int))
        self.assertTrue(how)
        if hwnd:
            self.assertNotEqual(winhost.exe_name(hwnd), "?")

    def test_activate_ignores_bad_handles(self):
        self.assertFalse(winhost.activate(None))
        self.assertFalse(winhost.activate(0))
        self.assertFalse(winhost.activate(0x7FFFFFF0))   # not a window

    def test_hook_saves_the_window_and_the_game_reads_it(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(hook, "LOG", os.path.join(d, "h.log")):
            state = os.path.join(d, "x.state")
            with mock.patch.object(winhost, "find_host_window", lambda: (0x1234, "foreground")), \
                    mock.patch.object(winhost, "exe_name", lambda h: "Code.exe"):
                hook.save_host_window(state)
            self.assertEqual(pathlib.Path(state + ".host").read_text(), str(0x1234))
            self.assertIn("foreground exe=Code.exe", pathlib.Path(hook.LOG).read_text(encoding="utf-8"))
            with mock.patch.object(common, "STATE", state), mock.patch.object(common, "CLAUDE_PANE", "window"):
                self.assertEqual(common._host_window(), 0x1234)
                self.assertTrue(common.can_focus())
                with mock.patch.object(winhost, "activate") as act:
                    common.focus_claude()
                act.assert_called_once_with(0x1234)

    def test_no_saved_window_means_no_enter_to_go_back(self):
        with tempfile.TemporaryDirectory() as d:
            state = os.path.join(d, "none.state")
            with mock.patch.object(common, "STATE", state), mock.patch.object(common, "CLAUDE_PANE", "window"):
                self.assertFalse(common.can_focus())
                common.focus_claude()                      # must not raise
            with mock.patch.object(common, "STATE", state), mock.patch.object(common, "CLAUDE_PANE", "wt"):
                self.assertTrue(common.can_focus())        # a WT pane can always move focus up


if __name__ == "__main__":
    unittest.main(verbosity=1)

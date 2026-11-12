#!/usr/bin/env python3
"""Checks for common.py's game registry and HookSession.   python3 test_common.py"""
import json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_argv, sys.argv = sys.argv, sys.argv[:1]  # common reads the hook args from argv
import common
import install
sys.argv = _argv


def game(root, name, meta):
    os.makedirs(os.path.join(root, name))
    open(os.path.join(root, name, name + ".py"), "w").close()
    if meta is not None:
        with open(os.path.join(root, name, "game.json"), "w") as f:
            f.write(meta if isinstance(meta, str) else json.dumps(meta))


class Registry(unittest.TestCase):
    def test_repo_games(self):
        self.assertEqual([g[0] for g in common.GAMES], ["knight", "dino"])

    def test_discovery_order_and_bad_folders(self):
        with tempfile.TemporaryDirectory() as root:
            game(root, "zeta", {"title": "Zeta", "order": 1})
            game(root, "alpha", {"title": "Alpha", "pitch": "p", "order": 2})
            game(root, "broken", "{not json")
            game(root, "nometa", None)
            os.makedirs(os.path.join(root, "loose"))
            open(os.path.join(root, "loose", "game.json"), "w").write('{"title": "x"}')  # no loose.py
            self.assertEqual(common.find_games(root), [("zeta", "Zeta", ""), ("alpha", "Alpha", "p")])

    def test_install_copies_every_game_but_not_tests(self):
        dirs, files = install.game_files(os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(dirs, ["dino", "knight"])
        self.assertIn(os.path.join("knight", "knight.py"), files)
        self.assertIn(os.path.join("dino", "game.json"), files)
        self.assertNotIn(os.path.join("knight", "test_knight.py"), files)


class Scr:
    def clearok(self, b): pass


class Session(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.dir.name, "s.state")
        self.saved = common.STATE, common.ALIVE, common.focus_claude, common.pick_game
        common.STATE, common.ALIVE = self.state, self.state + ".alive"
        self.focused = []
        common.focus_claude = lambda: self.focused.append(1)

    def tearDown(self):
        common.STATE, common.ALIVE, common.focus_claude, common.pick_game = self.saved
        self.dir.cleanup()

    def write(self, text):
        with open(self.state, "w") as f:
            f.write(text)
        st = os.stat(self.state)   # a new mtime even within the same clock tick
        os.utime(self.state, ns=(st.st_atime_ns, st.st_mtime_ns + 10 ** 9 * (1 + len(text))))

    def test_starts_with_the_current_state(self):
        self.write("done")
        self.assertEqual(common.HookSession("x").banner, "done")
        self.write("quit")
        self.assertTrue(common.HookSession("x").quit)

    def test_poll(self):
        ses = common.HookSession("x")
        self.assertIsNone(ses.poll())
        self.assertTrue(os.path.exists(common.ALIVE))   # heartbeat
        self.write("notify")
        self.assertEqual(ses.poll(), "pause")
        self.assertIn("needs you", ses.banner_msg())
        self.assertIsNone(ses.poll())                   # no change, no event
        self.write("run")
        self.assertEqual(ses.poll(), "run")
        self.assertIsNone(ses.banner)
        self.write("quit")
        self.assertEqual(ses.poll(), "quit")

    def test_keys(self):
        ses = common.HookSession("x")
        self.assertIsNone(ses.key(Scr(), ord("j")))
        self.assertEqual(ses.key(Scr(), ord("q")), "quit")
        ses.banner = "done"
        self.assertEqual(ses.key(Scr(), ord("j")), "keep")
        self.assertEqual(ses.key(Scr(), 13), "pause")
        self.assertEqual(self.focused, [1])
        ses.banner = "done"
        self.assertEqual(ses.key(Scr(), ord("p")), "play")
        common.pick_game = lambda scr, cur: "dino"
        self.assertEqual(ses.key(Scr(), ord("m")), "switch")
        self.assertEqual(ses.next, "dino")
        common.pick_game = lambda scr, cur: None
        self.assertEqual(ses.key(Scr(), 9), "back")
        common.pick_game = lambda scr, cur: "quit"
        self.assertEqual(ses.key(Scr(), ord("M")), "quit")

    def test_put_clips(self):
        out = []
        class W:
            def getmaxyx(self): return (5, 10)
            def addstr(self, y, x, s, a=0): out.append((y, x, s))
        common.put(W(), 1, -2, "abcdef")
        common.put(W(), 1, 7.6, "abcdef")
        common.put(W(), 9, 0, "off screen")
        self.assertEqual(out, [(1, 0, "cdef"), (1, 7, "ab")])

    def test_int_file(self):
        p = os.path.join(self.dir.name, "sub", "n")
        self.assertEqual(common.load_int(p), 0)
        common.save_int(p, 42)
        self.assertEqual(common.load_int(p), 42)


if __name__ == "__main__":
    unittest.main(verbosity=1)

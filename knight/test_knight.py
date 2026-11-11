#!/usr/bin/env python3
"""Headless checks for knight.py's Game logic.   python test_knight.py"""
import os, random, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_argv, sys.argv = sys.argv, sys.argv[:1]  # knight.py reads its hook args from argv
import knight as K
sys.argv = _argv

W = 80


def run(g, secs, mv=0, blocking=False):
    for _ in range(int(round(secs / K.DT))):
        g.step(mv, blocking)


def place(g, kind, gap, side=1):
    """Put one enemy `gap` cells from the knight on `side` (+1 right, -1 left)."""
    g.spawn(kind)
    e = g.enemies[-1]
    e["x"] = g.x + K.KW + gap if side > 0 else g.x - gap - e["w"]
    return e


def quiet(g):
    """No waves will arrive by themselves."""
    g.wave, g.inter = 1, 1e9
    g.cleared = True


class Movement(unittest.TestCase):
    def test_tap_and_hold_distance(self):
        g = Game()
        x0 = g.x
        run(g, 0.30, mv=1)
        run(g, 1.0)
        self.assertTrue(5.0 < g.x - x0 < 8.0, g.x - x0)
        g = Game()
        x0 = g.x
        run(g, 1.0, mv=1)
        self.assertTrue(15.0 < g.x - x0 < 20.0, g.x - x0)


class Waves(unittest.TestCase):
    def test_two_hearts_per_wave(self):
        for seed in range(5):
            random.seed(seed)
            g = Game()
            g.hp = 1
            for _ in range(8):
                g.next_wave()
                g.x = 2.0          # far from where hearts land
                drops = 0
                for kind in list(g.queue):
                    g.queue.remove(kind)
                    e = place(g, kind, 40)
                    e["hp"] = 0
                    before = len(g.hearts)
                    g.step(0, False)
                    drops += len(g.hearts) - before
                    g.hearts = []
                self.assertEqual(drops, K.HEARTS_PER_WAVE, (seed, g.wave))
                g.hp = 1

    def test_waves_progress(self):
        random.seed(1)
        g = Game()
        for _ in range(20 * K.FPS):
            for e in g.enemies:
                e["hp"] = 0
            pick_any(g)
            g.step(0, False)
            g.invuln = 5
        self.assertGreaterEqual(g.wave, 3)


class Powers(unittest.TestCase):
    def test_dash_is_invulnerable_and_cuts(self):
        g = Game()
        quiet(g)
        e = place(g, "devil", 2)
        g.dash()
        self.assertGreater(g.invuln, 0)
        run(g, K.DASH_TIME + 0.05)
        self.assertLess(e["hp"], K.KINDS["devil"]["hp"])

    def test_beam_pierces(self):
        g = Game()
        quiet(g)
        a, b = place(g, "devil", 6), place(g, "devil", 12)
        g.beam()
        run(g, 1.0)
        self.assertLess(a["hp"], 2)
        self.assertLess(b["hp"], 2)

    def test_mana_cost(self):
        g = Game()
        g.mp = 1
        g.spin()
        self.assertEqual(g.mp, 1)
        self.assertGreater(g.mp_flash, 0)


def Game():
    return K.Game(W)


def pick_any(g):
    if getattr(g, "offer", None):
        g.pick(0)


if __name__ == "__main__":
    unittest.main(verbosity=1)

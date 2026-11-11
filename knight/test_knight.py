#!/usr/bin/env python3
"""Headless checks for knight.py's Game logic.   python test_knight.py"""
import os, random, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_argv, sys.argv = sys.argv, sys.argv[:1]  # knight.py reads its hook args from argv
import knight as K
sys.argv = _argv
K.SCORE_FILE = os.devnull  # never touch the player's real high score

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


def strike_now(g, e):
    """Fast-forward an enemy to the end of its windup."""
    e["state"], e["t"], e["move"] = "windup", K.DT / 2, e.get("move", "melee")


class Combat(unittest.TestCase):
    def test_enemies_line_up_instead_of_stacking(self):
        random.seed(3)
        g = Game()
        quiet(g)
        g.invuln = 1e9
        # a slow devil in front, fast imps behind: they used to merge into one blob
        place(g, "devil", 20), place(g, "imp", 25), place(g, "imp", 30)
        for _ in range(6 * K.FPS):
            g.step(0, False)
            ground = sorted((e for e in g.enemies), key=lambda e: e["x"])
            for p, q in zip(ground, ground[1:]):
                self.assertGreater(q["x"] - (p["x"] + p["w"]), 0.5, [e["x"] for e in ground])
        self.assertEqual(len(g.enemies), 3)

    def test_block_and_parry(self):
        g = Game()
        quiet(g)
        e = place(g, "devil", 1)
        strike_now(g, e)
        g.step(0, True)                       # plain block: short stun, no damage
        self.assertEqual(g.hp, K.MAX_HP)
        self.assertAlmostEqual(e["t"], 0.8)
        g = Game()
        quiet(g)
        g.mp = 2
        e = place(g, "devil", 1)
        strike_now(g, e)
        g.shield_press()
        g.step(0, True)                       # parry: long stun, +1 MP
        self.assertEqual(g.hp, K.MAX_HP)
        self.assertAlmostEqual(e["t"], 1.6)
        self.assertEqual(g.mp, 3)
        g = Game()
        quiet(g)
        e = place(g, "devil", 1)
        strike_now(g, e)
        g.step(0, False)                      # no shield: hurt
        self.assertEqual(g.hp, K.MAX_HP - 1)

    def test_parry_reflects_fireball(self):
        g = Game()
        quiet(g)
        e = place(g, "devil", 15)
        e["state"], e["t"] = "stun", 99        # stands still
        g.fire.append([g.x + K.KW + 0.2, -22.0, 1, 0])
        g.shield_press()
        g.step(0, True)
        self.assertEqual(g.fire[0][3], 1)
        run(g, 1.0, blocking=True)
        self.assertEqual(e["hp"], 1)
        self.assertEqual(g.hp, K.MAX_HP)

    def test_combo_multiplies_score_and_decays(self):
        g = Game()
        quiet(g)
        for n in range(4):
            place(g, "imp", 40)["hp"] = 0
            g.step(0, False)
        self.assertEqual(g.combo, 4)
        self.assertEqual(g.score, 10 * (1 + 2 + 2 + 3))
        run(g, K.COMBO_TIME + 0.1)
        self.assertEqual(g.combo, 0)
        place(g, "imp", 40)["hp"] = 0
        g.step(0, False)
        self.assertEqual(g.combo, 1)

    def test_air_stab_bounces(self):
        g = Game()
        quiet(g)
        e = place(g, "devil", -1)              # right under the knight
        e["state"], e["t"] = "stun", 99
        g.vy = 14.0
        run(g, 0.15)
        self.assertGreater(g.y, 1.0)
        g.swing()
        self.assertEqual(e["hp"], 0)
        self.assertGreater(g.vy, 10.0)

    def test_hit_stop_freezes_the_world(self):
        g = Game()
        quiet(g)
        e = place(g, "brute", 1)
        g.swing()
        x = e["x"]
        e["state"] = "walk"
        g.step(0, False)
        self.assertEqual(e["x"], x)


class Enemies(unittest.TestCase):
    def test_heart_at_full_hp_gives_mana(self):
        g = Game()
        quiet(g)
        g.mp = 0
        g.hearts.append([g.x + 1, 5.0])
        g.step(0, False)
        self.assertEqual(g.hp, K.MAX_HP)
        self.assertEqual(g.mp, 1)

    def test_bat_needs_a_jump(self):
        g = Game()
        quiet(g)
        e = place(g, "bat", 1)
        e["state"], e["t"] = "stun", 99
        g.swing()
        self.assertEqual(e["hp"], 1)           # ground sword passes under it
        g.atk_cd, g.y = 0, 1.5
        g.swing()
        self.assertEqual(e["hp"], -1)

    def test_guard_blocks_sword_until_stunned(self):
        g = Game()
        quiet(g)
        e = place(g, "guard", 1)
        g.swing()
        self.assertEqual(e["hp"], 2)
        e["state"], e["t"] = "stun", 1.0
        g.atk_cd = 0
        g.swing()
        self.assertEqual(e["hp"], 1)
        g = Game()
        quiet(g)
        e = place(g, "guard", 1)
        g.spin()
        self.assertEqual(e["hp"], 0)

    def test_bomber_explodes(self):
        g = Game()
        quiet(g)
        e = place(g, "bomber", 1)
        o = place(g, "imp", 5)
        strike_now(g, e)
        g.step(0, True)                        # the shield doesn't help
        self.assertEqual(g.hp, K.MAX_HP - 2)
        self.assertLessEqual(o["hp"], 0)
        run(g, 0.2)
        self.assertEqual(g.score, 10)          # the imp; the bomber blew itself up
        g = Game()
        quiet(g)
        e = place(g, "bomber", 6)
        strike_now(g, e)
        g.step(0, False)
        self.assertEqual(g.hp, K.MAX_HP)

    def test_boss_wave(self):
        random.seed(2)
        g = Game()
        g.wave = K.BOSS_EVERY - 1
        g.next_wave()
        self.assertEqual(g.queue[-1], "boss")
        g.spawn(g.queue.pop())
        boss = g.enemies[0]
        self.assertEqual(boss["hp"], 20)
        # charge: runs past the knight and hurts it
        boss["x"] = g.x + K.KW + 15
        boss["move"] = "charge"
        strike_now(boss and g, boss)
        run(g, 1.5)
        self.assertEqual(g.hp, K.MAX_HP - 2)
        # slam: jumping clears it
        g.invuln = 0
        boss["state"], boss["move"], boss["t"] = "windup", "slam", K.DT / 2
        g.y, g.vy = 1.0, 5.0
        g.step(0, False)
        self.assertEqual(g.hp, K.MAX_HP - 2)
        boss["hp"] = 0
        g.queue = []
        run(g, 0.2)
        self.assertGreaterEqual(g.score, 500)


class Perks(unittest.TestCase):
    def test_offer_waits_for_a_pick(self):
        random.seed(4)
        g = Game()
        g.next_wave()
        g.queue = []
        place(g, "imp", 40)["hp"] = 0
        g.step(0, False)
        g.step(0, False)
        self.assertEqual(len(g.offer), 3)
        run(g, 5.0)
        self.assertEqual(g.wave, 1)            # held until a perk is picked
        g.offer = ["hp", "reach", "dash"]
        g.pick(0)
        self.assertEqual((g.max_hp, g.hp), (K.MAX_HP + 1, K.MAX_HP + 1))
        run(g, 3.0)
        self.assertEqual(g.wave, 2)

    def test_perks_apply_and_cap(self):
        g = Game()
        for p in K.PERKS:
            g.offer = [p]
            g.pick(0)
        self.assertEqual(g.dash_cost, 0)
        self.assertEqual(g.reach, K.SWORD_REACH + 2)
        for _ in range(20):
            g.offer = g.roll_perks()
            if not g.offer:
                break
            g.pick(0)
        self.assertLessEqual(g.max_hp, 8)
        self.assertLessEqual(g.max_mp, 10)


class Death(unittest.TestCase):
    def test_death_animates(self):
        g = Game()
        g.hp = 1
        g.hurt(1, 1)
        self.assertTrue(g.dead)
        run(g, 0.3)
        self.assertAlmostEqual(g.death_t, 0.3, places=2)
        self.assertEqual(K.knight_rows(g, False)[0][-1], "/|\\")   # kneeling
        run(g, 0.3)
        self.assertEqual(K.knight_rows(g, False)[0][-1], "_o_")    # fallen


def Game():
    return K.Game(W)


def pick_any(g):
    if getattr(g, "offer", None):
        g.pick(0)


if __name__ == "__main__":
    unittest.main(verbosity=1)

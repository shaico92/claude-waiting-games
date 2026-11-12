#!/usr/bin/env python3
"""Headless checks for knight.py's Game logic.   python test_knight.py"""
import os, random, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_argv, sys.argv = sys.argv, sys.argv[:1]  # knight.py reads its hook args from argv
import knight as K
sys.argv = _argv
K.SCORE_FILE = os.devnull  # never touch the player's real high score
import tempfile
K.RUN_FILE = os.path.join(tempfile.mkdtemp(prefix="knight-test-"), "run.json")  # nor the real save

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

    def test_dash_has_a_cooldown(self):
        # free-dash spam was endless invulnerability: the next dash waits DASH_CD
        g = Game()
        quiet(g)
        g.mp = g.max_mp
        g.dash()
        mp = g.mp
        run(g, K.DASH_TIME + 0.05)
        g.dash()
        self.assertEqual(g.mp, mp)             # refused: still cooling down
        self.assertLessEqual(g.dash_t, 0)
        run(g, K.DASH_CD)
        g.dash()
        self.assertEqual(g.mp, mp - K.DASH_COST)
        self.assertGreater(g.dash_t, 0)

    def test_cheap_dash_refunds_once_on_a_kill(self):
        def after(refund):
            random.seed(1)
            g = Game()
            quiet(g)
            g.dash_refund = refund
            a, b = place(g, "imp", 2), place(g, "imp", 3)
            a["hp"] = b["hp"] = 1
            g.mp = 2
            g.dash()
            run(g, K.DASH_TIME + 0.05)
            self.assertLessEqual(a["hp"], 0)
            self.assertLessEqual(b["hp"], 0)
            return g.mp
        self.assertEqual(after(True) - after(False), K.DASH_COST)   # two kills, one refund

    def test_dash_without_a_kill_is_not_refunded(self):
        g = Game()
        quiet(g)
        g.dash_refund = True
        g.mp = 2
        g.dash()
        run(g, K.DASH_TIME + 0.05)
        self.assertEqual(g.mp, 2 - K.DASH_COST)

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
        self.assertTrue(g.dash_refund)
        self.assertEqual(g.dash_cost, K.DASH_COST)   # "Cheap dash" refunds, it is never free
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

class Powerups(unittest.TestCase):
    def test_each_wave_drops_one_powerup_two_on_boss_waves(self):
        for wave, want in ((1, 1), (4, 1), (5, 2)):
            random.seed(wave)
            g = Game()
            g.wave = wave - 1
            g.next_wave()
            g.x = 40.0   # away from both spawn edges, so nothing is picked up
            for _ in range(len(g.queue)):   # kill the whole wave as it spawns
                g.spawn(g.queue.pop())
                g.enemies[-1]["hp"] = 0
                g.step(0, False)
            self.assertEqual(len(g.powerups) + (g.power_drops != 0) * 99, want, (wave, g.powerups))

    def test_pickup_applies_and_expires(self):
        g = Game()
        quiet(g)
        g.powerups.append([g.x + 1, 12.0, "rage"])
        g.step(0, False)
        self.assertFalse(g.powerups)
        self.assertGreater(g.rage_t, 7.5)
        run(g, 8.5)
        self.assertEqual(g.rage_t, 0.0)

    def test_untouched_powerup_times_out(self):
        g = Game()
        quiet(g)
        g.powerups.append([2.0, 1.0, "haste"])
        g.x = 60.0
        run(g, 1.2)
        self.assertFalse(g.powerups)
        self.assertEqual(g.haste_t, 0.0)

    def test_shield_absorbs_exactly_one_hit(self):
        g = Game()
        g.take_power("aura")
        self.assertFalse(g.hurt(1, 1))
        self.assertEqual((g.hp, g.aura), (g.max_hp, 0))
        run(g, 1.0)                                  # let the invulnerability lapse
        self.assertTrue(g.hurt(1, 1))
        self.assertEqual(g.hp, g.max_hp - 1)

    def test_rage_doubles_sword_damage_and_speeds_swings(self):
        g = Game()
        quiet(g)
        e = place(g, "devil", 1)                     # 2 hp: one raged swing kills it
        g.take_power("rage")
        g.swing()
        self.assertLessEqual(e["hp"], 0)
        self.assertLess(g.atk_cd, 0.25)

    def test_haste_runs_farther(self):
        a, b = Game(), Game()
        b.take_power("haste")
        run(a, 1.0, mv=1)
        run(b, 1.0, mv=1)
        self.assertGreater(b.x, a.x + 3)

    def test_mana_refills_and_aura_is_not_offered_twice(self):
        g = Game()
        g.mp = 0
        g.take_power("mana")
        self.assertEqual(g.mp, g.max_mp)
        g.aura = 1
        g.mp = 0
        for _ in range(50):
            self.assertNotEqual(g.pick_power(), "aura")
        g.mp = g.max_mp
        for _ in range(50):
            self.assertNotEqual(g.pick_power(), "mana")


class Scenes(unittest.TestCase):
    def go_to_scene(self, si):
        g = Game()
        quiet(g)
        g.scene = si
        g.hazards, g.haz_t = [], 1e9    # only the hazards a test adds
        return g

    def test_scene_changes_every_three_waves(self):
        self.assertEqual([K.scene_of(w) for w in range(1, 14)], [0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3, 0])

    def test_new_scene_starts_a_wipe_and_banner(self):
        g = Game()
        g.wave = 3
        g.next_wave()                      # wave 4: cave
        self.assertEqual((g.scene, g.prev_scene), (1, 0))
        self.assertGreater(g.scene_t, 0)
        self.assertGreater(g.scene_msg_t, 0)
        run(g, K.SCENE_MSG_T + 0.1)
        self.assertEqual((g.scene_t, g.scene_msg_t), (0.0, 0.0))

    def test_same_scene_does_not_wipe(self):
        g = Game()
        g.next_wave()
        g.next_wave()
        self.assertEqual(g.scene_t, 0.0)

    def test_scene_biases_the_pool(self):
        random.seed(1)
        kinds = set()
        for _ in range(60):
            g = Game()
            g.wave = 6                      # next wave is 7: frost, which adds guards
            g.next_wave()
            kinds |= set(g.queue)
        self.assertEqual(g.scene, 2)
        self.assertIn("guard", kinds)

    def test_stalactite_hurts_knight_under_it_and_enemies_too(self):
        g = self.go_to_scene(1)
        g.hazards.append([g.x + 1, 0.1, "drip"])
        e = place(g, "devil", 6)
        g.hazards.append([e["x"] + 1, 0.1, "drip"])
        run(g, 0.2)
        self.assertEqual(g.hp, g.max_hp - 1)
        self.assertLessEqual(e["hp"], 0)

    def test_stalactite_warning_does_nothing_until_it_lands(self):
        g = self.go_to_scene(1)
        g.hazards.append([g.x + 1, 1.0, "drip"])
        run(g, 0.5)
        self.assertEqual(g.hp, g.max_hp)

    def test_geyser_can_be_jumped(self):
        g = self.go_to_scene(3)
        g.hazards.append([g.x + 1, 0.1, "geyser"])
        g.vy = K.JUMP_V                    # in the air when it erupts
        run(g, 0.12)
        self.assertEqual(g.hp, g.max_hp)
        g = self.go_to_scene(3)
        g.hazards.append([g.x + 1, 0.1, "geyser"])
        run(g, 0.2)
        self.assertEqual(g.hp, g.max_hp - 1)

    def test_shield_soaks_a_hazard(self):
        g = self.go_to_scene(3)
        g.take_power("aura")
        g.hazards.append([g.x + 1, 0.1, "geyser"])
        run(g, 0.2)
        self.assertEqual((g.hp, g.aura), (g.max_hp, 0))

    def test_hazards_only_spawn_while_fighting(self):
        g = self.go_to_scene(1)
        g.haz_t = 0.0
        run(g, 1.0)
        self.assertFalse(g.hazards)        # nothing to fight: quiet
        place(g, "imp", 30)
        g.haz_t = 0.0
        run(g, 0.1)
        self.assertTrue(g.hazards)

    def test_ice_slides_farther_than_grass(self):
        a, b = self.go_to_scene(0), self.go_to_scene(2)
        for g in (a, b):
            run(g, 0.5, mv=1)
            run(g, 1.0)
        self.assertGreater(b.x - 40, 0)
        self.assertGreater(b.x, a.x + 2)

    def test_boons_follow_the_scene(self):
        random.seed(3)
        g = self.go_to_scene(2)
        picks = [g.pick_power() for _ in range(400)]
        self.assertGreater(picks.count("haste"), picks.count("rage"))

    def test_every_scene_draws(self):
        """Run main() on each scene, mid-wipe, with hazards on screen."""
        class Scr:
            def __init__(self): self.n = 0
            def getmaxyx(self): return (14, 80)
            def getch(self):
                self.n += 1
                return ord("q") if self.n > 60 else -1
            def __getattr__(self, name): return lambda *a, **k: None
        orig = K.Game.__init__
        real = K.time.sleep
        K.time.sleep = lambda s: None
        try:
            for si in range(len(K.SCENES)):
                def init(self, w, si=si):
                    orig(self, w)
                    self.scene, self.prev_scene = si, (si + 1) % len(K.SCENES)
                    self.scene_t, self.scene_msg_t = 1.0, 3.0
                    self.hazards = [[20.0, 1.0, "drip"], [40.0, 0.2, "geyser"], [60.0, -0.1, "drip"], [30.0, -0.1, "geyser"]]
                K.Game.__init__ = init
                K.main(Scr())
        finally:
            K.Game.__init__ = orig
            K.time.sleep = real


class BossVariety(unittest.TestCase):
    def boss(self, scene, gap=10):
        g = Game()
        quiet(g)
        g.wave = K.BOSS_EVERY      # boss hp scales with the wave
        g.scene = scene
        g.hazards, g.haz_t = [], 1e9
        g.spawn("boss")
        b = g.enemies[0]
        b["x"] = g.x + K.KW + gap
        return g, b

    def fire_move(self, g, b, move):
        b["move"], b["state"], b["t"] = move, "windup", K.DT / 2
        g.step(0, False)

    def test_each_scene_has_its_own_boss(self):
        names = set()
        for si in range(len(K.SCENES)):
            g, b = self.boss(si)
            self.assertEqual(b["variant"], si)
            self.assertEqual(b["hp"], K.BOSSES[si]["hp"])
            names.add(K.BOSSES[si]["name"])
            self.assertEqual(g.boss_variant, si)
            self.assertGreater(g.boss_msg_t, 0)
        self.assertEqual(len(names), len(K.SCENES))

    def test_signature_move_is_in_the_rotation(self):
        random.seed(5)
        for si in range(len(K.SCENES)):
            g, b = self.boss(si, gap=4)
            seen = set()
            for _ in range(200):
                b["ai_cd"] = 0
                b["state"] = "walk"
                if g.boss_move(b, 4):
                    seen.add(b["move"])
            self.assertIn(K.BOSSES[si]["move"], seen, si)
            self.assertIn("slam", seen)

    def test_summon_calls_imps_and_respects_the_cap(self):
        g, b = self.boss(0)
        self.fire_move(g, b, "summon")
        self.assertEqual([e["kind"] for e in g.enemies].count("imp"), 2)
        g, b = self.boss(0)
        for _ in range(K.SUMMON_CAP):
            g.spawn("imp")
        n = len(g.enemies)
        self.fire_move(g, b, "summon")
        self.assertEqual(len(g.enemies), n)

    def test_summon_mid_loop_does_not_crash_a_walking_enemy(self):
        # crash seen live: imps summoned during step() had no entry in gaps -> IndexError
        g, b = self.boss(0)
        g.spawn("imp")
        imp = g.enemies[1]
        imp["x"], imp["state"] = b["x"] + 20, "walk"
        self.fire_move(g, b, "summon")
        self.assertEqual([e["kind"] for e in g.enemies].count("imp"), 3)
        run(g, 1.0)

    def test_quake_rains_stalactites_and_one_can_be_dodged(self):
        random.seed(4)
        g, b = self.boss(1)
        g.x = 40.0
        self.fire_move(g, b, "quake")
        self.assertEqual(len([h for h in g.hazards if h[2] == "drip"]), 3)
        run(g, 0.2)
        self.assertEqual(g.hp, g.max_hp)       # still only warnings
        g.x = 5.0                              # step out of the way before they land
        run(g, 1.5)
        self.assertEqual(g.hp, g.max_hp)

    def test_erupt_marches_geysers_toward_the_knight(self):
        g, b = self.boss(3, gap=20)
        self.fire_move(g, b, "erupt")
        gey = sorted((h for h in g.hazards if h[2] == "geyser"), key=lambda h: h[1])
        self.assertEqual(len(gey), 4)
        xs = [h[0] for h in gey]
        self.assertEqual(xs, sorted(xs, reverse=True))   # the first one is nearest the boss
        self.assertGreater(gey[-1][1], gey[0][1])

    def test_slide_goes_to_the_wall_and_leaves_the_boss_stunned(self):
        g, b = self.boss(2, gap=20)
        g.x = 5.0
        b["x"] = 30.0
        self.fire_move(g, b, "slide")
        self.assertEqual(b["state"], "charge")
        for _ in range(int(3.0 / K.DT)):
            g.step(0, False)
            if b["state"] != "charge":
                break
        self.assertEqual(b["state"], "stun")
        self.assertGreater(b["t"], 2.0)
        self.assertLessEqual(b["x"], 0.5)      # it ran all the way to the wall, past the knight

    def test_boss_sprites_differ(self):
        sprites = set()
        for si in range(len(K.SCENES)):
            g, b = self.boss(si)
            sprites.add(tuple(K.enemy_rows(g, b, 0)))
        self.assertEqual(len(sprites), len(K.SCENES))

    def test_every_boss_draws(self):
        class Scr:
            def __init__(self): self.n = 0
            def getmaxyx(self): return (14, 80)
            def getch(self):
                self.n += 1
                return ord("q") if self.n > 50 else -1
            def __getattr__(self, name): return lambda *a, **k: None
        orig, real = K.Game.__init__, K.time.sleep
        K.time.sleep = lambda s: None
        try:
            for si in range(len(K.SCENES)):
                def init(self, w, si=si):
                    orig(self, w)
                    self.scene = self.prev_scene = si
                    self.wave, self.cleared, self.inter = 5, True, 1e9
                    self.spawn("boss")
                    self.enemies[0]["x"] = 50.0
                K.Game.__init__ = init
                K.main(Scr())
        finally:
            K.Game.__init__, K.time.sleep = orig, real


class Elites(unittest.TestCase):
    def test_elite_wave_and_reward(self):
        random.seed(8)
        g = Game()
        g.wave = 2
        g.next_wave()                          # wave 3
        self.assertIn("elite", g.queue)
        g.wave = 3
        g.next_wave()                          # wave 4
        self.assertNotIn("elite", g.queue)
        g.wave = 7
        g.next_wave()                          # wave 8
        self.assertIn("elite", g.queue)
        g = Game()
        quiet(g)
        g.power_drops = 0
        g.spawn("elite")
        e = g.enemies[0]
        self.assertEqual((e["kind"], e["hp"]), ("brute", 10))
        self.assertEqual(K.enemy_col(e), 3)
        e["x"] = 60.0
        e["hp"] = 0
        g.step(0, False)
        self.assertEqual(len(g.powerups), 1)   # an elite always drops one
        self.assertEqual(g.score, 80 * 3)


class SceneEnemies(unittest.TestCase):
    def test_spider_drops_then_walks(self):
        g = Game()
        quiet(g)
        g.h = 14
        g.spawn("spider")
        e = g.enemies[0]
        self.assertEqual(e["state"], "drop")
        self.assertGreater(e["alt"], 3)
        e["x"] = 60.0
        run(g, 1.0)
        self.assertEqual((e["state"], e["alt"]), ("walk", 0))
        e["state"] = "drop"
        e["alt"] = 6.0
        g.swing()                              # a ground swing cannot reach it in the air
        self.assertEqual(e["hp"], 2)

    def test_spider_landing_on_the_knight_hurts(self):
        g = Game()
        quiet(g)
        g.spawn("spider")
        e = g.enemies[0]
        e["x"], e["alt"] = g.x, 0.1
        run(g, 0.1)
        self.assertEqual(g.hp, g.max_hp - 1)

    def test_roller_crosses_the_screen_and_can_be_jumped(self):
        g = Game()
        quiet(g)
        g.spawn("roller")
        e = g.enemies[0]
        e["x"], e["vx"] = g.x - 10, 15.0
        g.y, g.vy = 2.0, 0.0                   # in the air as it passes under
        for _ in range(int(1.2 / K.DT)):
            g.vy, g.y = 0.0, 2.0
            g.step(0, False)
        self.assertEqual(g.hp, g.max_hp)
        run(g, 3.0)
        self.assertFalse(g.enemies)            # rolled off: gone, no score
        self.assertEqual(g.score, 0)

    def test_roller_hurts_on_the_ground_and_a_shield_smashes_it(self):
        g = Game()
        quiet(g)
        g.spawn("roller")
        e = g.enemies[0]
        e["x"], e["vx"] = g.x - 4, 15.0
        run(g, 0.6)
        self.assertEqual(g.hp, g.max_hp - 1)
        g = Game()
        quiet(g)
        g.face = -1
        g.spawn("roller")
        e = g.enemies[0]
        e["x"], e["vx"] = g.x - 4, 15.0
        g.mp = 0
        for _ in range(int(0.6 / K.DT)):
            g.step(0, True)
        self.assertEqual(g.hp, g.max_hp)
        self.assertEqual(g.mp, 1)

    def test_fire_imp_leaves_flames_that_burn(self):
        g = Game()
        quiet(g)
        g.x = 70.0
        g.spawn("fimp")
        e = g.enemies[0]
        e["x"] = 5.0
        run(g, 1.0)
        self.assertTrue(g.flames)
        fl = g.flames[0]
        g.enemies = []
        g.x, g.invuln = fl[0] - 1, 0.0
        g.step(0, False)
        self.assertEqual(g.hp, g.max_hp - 1)
        run(g, K.FLAME_TTL + 0.5)
        self.assertFalse(g.flames)

    def test_scene_pools_include_their_enemy(self):
        random.seed(2)
        for wave, kind in ((3, "spider"), (6, "roller"), (9, "fimp")):
            seen = set()
            for _ in range(40):
                g = Game()
                g.wave = wave
                g.next_wave()
                seen |= set(g.queue)
            self.assertIn(kind, seen)


class Finisher(unittest.TestCase):
    def kill(self, g, n):
        for _ in range(n):
            e = place(g, "imp", 40)
            e["hp"] = 0
            g.step(0, False)

    def test_six_kill_combo_earns_it_and_it_clears_the_screen(self):
        g = Game()
        quiet(g)
        self.kill(g, 5)
        self.assertFalse(g.fin_ready)
        self.kill(g, 1)
        self.assertTrue(g.fin_ready)
        a = place(g, "devil", 6)
        b = place(g, "brute", 12, -1)
        g.finisher()
        self.assertFalse(g.fin_ready)
        self.assertEqual(a["hp"], 0 - 1)       # 3 damage into 2 hp
        self.assertEqual(b["hp"], 5 - 3)       # reaches both sides
        self.assertGreater(g.fin_t, 0)
        self.assertFalse(g.finisher())         # one per earn

    def test_it_is_earned_again_after_six_more(self):
        g = Game()
        quiet(g)
        self.kill(g, 6)
        g.finisher()
        self.kill(g, 5)
        self.assertFalse(g.fin_ready)
        self.kill(g, 1)
        self.assertTrue(g.fin_ready)

    def test_getting_hit_or_waiting_loses_it(self):
        g = Game()
        quiet(g)
        self.kill(g, 6)
        g.hurt(1, 1)
        self.assertFalse(g.fin_ready)
        self.assertFalse(g.finisher())
        g = Game()
        quiet(g)
        self.kill(g, 6)
        run(g, K.COMBO_TIME + 0.5)
        self.assertFalse(g.fin_ready)

    def test_finisher_beats_a_guard_shield(self):
        g = Game()
        quiet(g)
        self.kill(g, 6)
        e = place(g, "guard", 5)
        g.finisher()
        self.assertLessEqual(e["hp"], 0)


class Weapons(unittest.TestCase):
    def test_t_cycles_through_the_three(self):
        g = Game()
        seen = [g.weapon]
        for _ in range(3):
            g.swap_weapon()
            g.atk_cd = 0
            seen.append(g.weapon)
        self.assertEqual(seen, ["sword", "spear", "hammer", "sword"])

    def test_spear_reaches_farther_and_swings_slower(self):
        g = Game()
        quiet(g)
        far = place(g, "imp", 6)               # beyond the sword's reach of 4
        g.swing()
        self.assertEqual(far["hp"], 1)
        g.atk_cd = 0
        g.weapon = "spear"
        g.swing()
        self.assertLessEqual(far["hp"], 0)
        self.assertGreater(g.atk_cd, 0.4)

    def test_hammer_is_short_but_hits_for_two_and_breaks_guards(self):
        g = Game()
        quiet(g)
        g.weapon = "hammer"
        e = place(g, "guard", 2)
        g.swing()
        self.assertLessEqual(e["hp"], 0)       # shield no use: 2 damage, 2 hp
        g = Game()
        quiet(g)
        g.weapon = "hammer"
        far = place(g, "imp", 5)
        g.swing()
        self.assertEqual(far["hp"], 1)         # out of reach
        self.assertAlmostEqual(g.atk_cd, 0.7)

    def test_hammer_staggers_a_brute_a_sword_does_not(self):
        g = Game()
        quiet(g)
        b = place(g, "brute", 1)
        g.swing()
        self.assertNotEqual(b["state"], "stun")
        g = Game()
        quiet(g)
        g.weapon = "hammer"
        b = place(g, "brute", 1)
        g.swing()
        self.assertEqual(b["state"], "stun")
        g = Game()
        quiet(g)
        g.weapon = "hammer"
        boss = place(g, "boss", 1)
        g.swing()
        self.assertNotEqual(boss["state"], "stun")   # bosses stay unstaggerable

    def test_blade_drawn_per_weapon(self):
        g = Game()
        for wpn, tip in (("sword", ">"), ("spear", "}"), ("hammer", "#")):
            g.weapon, g.atk_t = wpn, K.SWING_T
            row = K.knight_rows(g, False)[0][1]
            self.assertTrue(row.endswith(tip), (wpn, row))
        g.face = -1
        g.weapon = "spear"
        self.assertIn("{", K.knight_rows(g, False)[0][1])

    def test_new_things_draw(self):
        class Scr:
            def __init__(self): self.n = 0
            def getmaxyx(self): return (14, 80)
            def getch(self):
                self.n += 1
                return {3: ord("t"), 6: ord("x"), 9: ord("t")}.get(self.n, ord("q") if self.n > 60 else -1)
            def __getattr__(self, name): return lambda *a, **k: None
        orig, real = K.Game.__init__, K.time.sleep
        K.time.sleep = lambda s: None
        try:
            def init(self, w):
                orig(self, w)
                self.wave, self.cleared, self.inter = 5, True, 1e9
                self.fin_ready = True
                self.flames = [[30.0, 2.0]]
                self.spawn("spider"); self.spawn("roller"); self.spawn("fimp"); self.spawn("elite")
            K.Game.__init__ = init
            K.main(Scr())
        finally:
            K.Game.__init__, K.time.sleep = orig, real


class Animation(unittest.TestCase):
    def legs(self, g):
        return K.knight_rows(g, False)[0][-1]

    def test_run_cycle_follows_distance(self):
        g = Game()
        seen = set()
        for _ in range(60):
            g.step(1, False)
            seen.add(self.legs(g))
        self.assertTrue({"/ \\", " | ", r"\ /"} <= seen, seen)
        run(g, 1.5)   # glides to a stop: back to standing
        self.assertEqual(self.legs(g), "/ \\")

    def test_jump_poses_and_landing(self):
        g = Game()
        g.vy = K.JUMP_V
        g.step(0, False)
        self.assertEqual(K.knight_rows(g, False)[0][0], r"\O/")        # rising: arms up
        while g.vy > -8:
            g.step(0, False)
        self.assertEqual(K.knight_rows(g, False)[0][-1], "| |")         # falling: legs tucked
        while g.y > 0:
            g.step(0, False)
        self.assertGreater(g.land_t, 0)                                  # landing crouch
        self.assertEqual(len(K.knight_rows(g, False)[0]), 2)
        run(g, 0.2)
        self.assertEqual(len(K.knight_rows(g, False)[0]), 3)

    def test_sword_draws_back(self):
        g = Game()
        g.swing()
        full = len(K.knight_rows(g, False)[0][1])
        run(g, 0.12)
        self.assertLess(len(K.knight_rows(g, False)[0][1]), full)

    def test_dash_leaves_afterimages_that_fade(self):
        g = Game()
        g.dash()
        run(g, 0.15)
        self.assertTrue(g.ghosts)
        run(g, 0.5)
        self.assertFalse(g.ghosts)

    def test_half_speed_walk_is_slower(self):
        a, b = Game(), Game()
        for _ in range(15):
            a.step(1, False, 0.55)
            b.step(1, False)
        self.assertLess(a.x, b.x)

    def test_enemy_legs_swap_while_walking(self):
        g = Game()
        g.spawn("devil")
        e = g.enemies[0]
        rows = set()
        for x in (10.0, 11.3):
            e["x"] = x
            rows.add(K.enemy_rows(g, e, 0)[-1])
        self.assertEqual(rows, {"/ \\", "| |"})

    def test_whole_screen_draws(self):
        """Run main() against a scripted fake screen: nothing in the draw code may raise."""
        class Scr:
            def __init__(self, keys): self.keys, self.n = keys, 0
            def getmaxyx(self): return (14, 80)
            def getch(self):
                self.n += 1
                return self.keys.get(self.n, ord("q") if self.n > 120 else -1)
            def __getattr__(self, name): return lambda *a, **k: None
        keys = {2: ord("d"), 3: ord("d"), 10: ord("w"), 20: ord("j"), 40: ord("u"), 60: ord("a"), 90: ord("i")}
        real = K.time.sleep
        K.time.sleep = lambda s: None
        try:
            K.main(Scr(keys))
        finally:
            K.time.sleep = real


class HeldKeys(unittest.TestCase):
    """main() with real key-ups (common.KEYS): running survives a stab and a jump."""
    def play(self, real):
        import common
        tr = common.KeyTracker()
        tr.real = real
        tr.event(ord("d"), True)             # D held down for the whole run
        mvs, orig = [], K.Game.step
        def step(g, mv, blocking, speed=1.0):
            mvs.append(mv)
            return orig(g, mv, blocking, speed)
        class Scr:
            def __init__(self): self.n = 0
            def getmaxyx(self): return (14, 80)
            def getch(self):
                self.n += 1
                keys = {3: ord("d"), 9: ord("j"), 15: ord("w"), 21: ord("j")}
                return keys.get(self.n, ord("q") if self.n > 80 else -1)
            def __getattr__(self, name): return lambda *a, **k: None
        now = [K.time.time()]                 # game clock: a frame passes per sleep
        def sleep(s): now[0] += 1.0 / K.FPS
        real_sleep, real_time = K.time.sleep, K.time.time
        K.time.sleep, K.time.time, K.KEYS, K.Game.step = sleep, (lambda: now[0]), tr, step
        try:
            K.main(Scr())
        finally:
            K.time.sleep, K.time.time, K.Game.step = real_sleep, real_time, orig
            K.KEYS = common.KEYS
        return mvs

    def test_real_keys_keep_running_through_stab_and_jump(self):
        mvs = self.play(True)
        self.assertGreater(len(mvs), 20)
        self.assertEqual(set(mvs), {1})

    def test_without_real_keys_the_emulation_still_moves(self):
        mvs = self.play(False)
        self.assertIn(1, mvs)                 # the single D press still walks...
        self.assertEqual(mvs[-1], 0)          # ...but the old guess runs out: the reported bug


def Game():
    return K.Game(W)


def pick_any(g):
    if getattr(g, "offer", None):
        g.pick(0)


class RunSave(unittest.TestCase):
    def setUp(self):
        K.clear_run()

    def test_new_wave_is_saved(self):
        g = Game()
        g.inter = 0.0
        run(g, 0.1)
        self.assertEqual(g.wave, 1)
        d = K.load_run()
        self.assertEqual(d["wave"], 1)
        self.assertEqual(d["hp"], g.hp)

    def test_perk_pick_saves_the_next_wave(self):
        g = Game()
        g.wave, g.score, g.weapon = 4, 321, "spear"
        g.offer = ["hp", "reach", "mana"]
        g.pick(1)
        d = K.load_run()
        self.assertEqual(d["wave"], 5)
        self.assertEqual(d["perks"], ["reach"])
        self.assertEqual((d["score"], d["weapon"]), (321, "spear"))

    def test_round_trip(self):
        g = Game()
        g.wave, g.score, g.best_combo, g.weapon = 6, 900, 7, "hammer"
        g.offer = ["hp", "mana", "reach"]
        g.pick(0)
        g.hp = 3
        K.save_run(g.snapshot(7))
        h = Game()
        self.assertTrue(h.restore(K.load_run()))
        self.assertEqual((h.max_hp, h.hp, h.score, h.best_combo, h.weapon, h.perks),
                         (g.max_hp, 3, 900, 7, "hammer", ["hp"]))
        self.assertTrue(h.resumed)
        h.inter = 0.0
        run(h, 0.1)
        self.assertEqual(h.wave, 7)           # straight into the saved wave
        self.assertEqual(h.scene, K.scene_of(7))
        self.assertEqual(h.scene_t, 0)        # no curtain wipe on resume
        self.assertFalse(h.resumed)

    def test_death_deletes_the_save(self):
        g = Game()
        g.inter = 0.0
        run(g, 0.1)
        self.assertIsNotNone(K.load_run())
        g.invuln, g.hp = 0, 1
        g.hurt(1, 1)
        self.assertTrue(g.dead)
        self.assertIsNone(K.load_run())

    def test_bad_saves_are_ignored(self):
        for text in ("{not json", '{"version": 999, "wave": 3}', '{"version": 1, "wave": 2}'):
            with open(K.RUN_FILE, "w") as f:
                f.write(text)
            self.assertIsNone(K.load_run(), text)
        g = Game()
        d = g.snapshot(3)
        d["hp"] = "lots"
        self.assertFalse(g.restore(d))         # unusable values: a fresh run, no crash
        self.assertEqual((g.wave, g.hp, g.resumed), (0, K.MAX_HP, False))


if __name__ == "__main__":
    unittest.main(verbosity=1)

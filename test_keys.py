"""Held keys from real key-down/up events (common.KeyTracker, key_event, parse_input,
the Windows console reader). Run: python3 test_keys.py"""
import os, subprocess, sys, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

D, J, W = ord("d"), ord("j"), ord("w")
VK_D, VK_J, VK_W, VK_LEFT = 0x44, 0x4A, 0x57, 0x25


class Clock:
    def __init__(self): self.t = 100.0
    def __call__(self): return self.t


def fresh():
    clock = Clock()
    return clock, common.KeyTracker(clock)


def w32(vk, ch, down, repeat=1):
    """A win32-input-mode sequence as Windows Terminal sends it."""
    return [ord(c) for c in "\x1b[%d;32;%d;%d;0;%d_" % (vk, ch, 1 if down else 0, repeat)]


class Tracker(unittest.TestCase):
    def test_text_only_hosts_never_turn_it_on(self):
        # VS Code's terminal: ConPTY fakes an up right after each down, held or not
        clock, k = fresh()
        for _ in range(30):
            k.event(D, True)
            k.event(D, False)
            clock.t += 0.033
        self.assertFalse(k.real)
        self.assertIsNone(k.since([D]))

    def test_a_repeat_without_an_up_proves_it(self):
        clock, k = fresh()
        k.event(D, True)
        clock.t += 0.5
        k.event(D, True)       # OS auto-repeat
        self.assertTrue(k.real)
        self.assertEqual(k.since([D]), 100.0)

    def test_a_slow_up_proves_it(self):
        clock, k = fresh()
        k.event(D, True)
        clock.t += 0.2
        k.event(D, False)
        self.assertTrue(k.real)
        self.assertIsNone(k.since([D]))

    def test_running_survives_a_stab(self):
        # the bug: holding D then pressing J stopped the knight
        clock, k = fresh()
        k.real = True
        k.event(D, True)
        clock.t += 0.6
        k.event(J, True)       # the OS now repeats J, not D
        clock.t += 0.1
        k.event(J, False)
        clock.t += 2.0         # no more events: D is still physically down
        self.assertEqual(k.since([D]), 100.0)

    def test_latest_press_wins(self):
        clock, k = fresh()
        k.real = True
        k.event(D, True)
        clock.t += 0.3
        k.event(ord("a"), True)
        self.assertEqual(k.since([D, ord("a")]), 100.3)

    def test_focus_loss_and_silence_release_everything(self):
        clock, k = fresh()
        k.real = True
        k.event(D, True)
        k.clear()
        self.assertIsNone(k.since([D]))
        k.event(D, True)
        clock.t += k.STALE + 1
        self.assertIsNone(k.since([D]))


class KeyEvents(unittest.TestCase):
    def setUp(self):
        self.k = common.KeyTracker()
        p = mock.patch.object(common, "KEYS", self.k)
        p.start()
        self.addCleanup(p.stop)

    def test_presses(self):
        self.assertEqual(common.key_event(True, VK_D, D), [D])
        self.assertEqual(common.key_event(True, VK_D, ord("D")), [ord("D")])   # shift
        self.assertEqual(common.key_event(True, VK_LEFT, 0), [260])
        self.assertEqual(common.key_event(True, 0x0D, 13), [13])
        self.assertEqual(common.key_event(True, 0x10, 0), [])                # shift alone
        self.assertEqual(common.key_event(False, VK_D, D), [])
        self.assertEqual(common.key_event(True, VK_D, D, 3), [D, D, D])
        with self.assertRaises(KeyboardInterrupt):
            common.key_event(True, 0x43, 3)

    def test_held_ids_ignore_shift_and_layout_case(self):
        common.key_event(True, VK_D, ord("D"))
        common.key_event(True, VK_LEFT, 0)
        self.assertEqual(set(self.k.down), {D, 260})

    def test_win32_input_mode_sequences(self):
        buf = w32(VK_D, D, True) + w32(VK_J, J, True) + w32(VK_J, J, False) + [ord("x")]
        self.assertEqual(common.parse_input(buf, False), [D, J, ord("x")])
        self.assertEqual(buf, [])
        self.assertIn(D, self.k.down)
        self.assertNotIn(J, self.k.down)

    def test_plain_input_passes_through(self):
        buf = [D, 260, 27]
        self.assertEqual(common.parse_input(buf, True), [D, 260, 27])

    def test_half_a_sequence_waits_unless_flushed(self):
        seq = w32(VK_D, D, True)
        buf = seq[:5]
        self.assertEqual(common.parse_input(buf, False), [])
        buf += seq[5:]
        self.assertEqual(common.parse_input(buf, False), [D])
        buf = [27]
        self.assertEqual(common.parse_input(buf, True), [27])   # a lone Esc

    def test_focus_out_releases(self):
        common.parse_input(w32(VK_D, D, True), False)
        common.parse_input([ord(c) for c in "\x1b[O"], False)
        self.assertEqual(self.k.down, {})

    def test_wrapped_screen(self):
        class Scr:
            def __init__(self, codes): self.codes = codes
            def getch(self): return self.codes.pop(0) if self.codes else -1
            def getmaxyx(self): return (10, 40)
        s = common._WinInputScreen(Scr(w32(VK_W, W, True) + w32(VK_W, W, False)))
        self.assertEqual((s.getch(), s.getch()), (W, -1))
        self.assertEqual(s.getmaxyx(), (10, 40))


@unittest.skipUnless(os.name == "nt", "Windows console")
class Console(unittest.TestCase):
    def test_reader_opens_on_a_real_console(self):
        # this test runner usually has no console: start a hidden one for the check
        import tempfile
        res = os.path.join(tempfile.mkdtemp(), "res.txt")
        code = ("import sys; sys.path.insert(0, %r); import common, ctypes;"
                "c = common._ConsoleInput.open();"
                "open(%r, 'w').write('%%s %%s %%s' %% (c is not None, ctypes.sizeof(c.buf[0]) if c else 0,"
                " c.getch() if c else 'x'))" % (os.path.dirname(os.path.abspath(__file__)), res))
        si = subprocess.STARTUPINFO()
        si.dwFlags, si.wShowWindow = subprocess.STARTF_USESHOWWINDOW, 0   # SW_HIDE
        # no pipes: with any std handle redirected the child would not read its own console
        subprocess.run([sys.executable, "-c", code], timeout=20,
                       creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=si)
        self.assertEqual(open(res).read().split(), ["True", "20", "-1"])


if __name__ == "__main__":
    unittest.main(verbosity=1)

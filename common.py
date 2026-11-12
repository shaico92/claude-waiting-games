"""Shared by the waiting games: terminal drawing on Windows, the Claude Code hook
protocol (state file, heartbeat, focus), and the game picker.

argv (set by hook.py): <state file> <claude pane: tmux pane id, "wt" or "window">
"""
import os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))
for _d in ("knight", "dino"):
    if os.path.join(ROOT, _d) not in sys.path:
        sys.path.insert(0, os.path.join(ROOT, _d))

# name, title, one-line pitch - in menu order
GAMES = [
    ("knight", "Knight vs Devils", "sword, shield and spells against waves of devils"),
    ("dino",   "Dino Run",         "jump the cactuses, as long as you can"),
]
DATA = os.path.join(os.path.expanduser("~"), ".claude", "waiting-games")
LAST_GAME = os.path.join(DATA, "last-game")

class _VTCurses:
    """Windows: draw with VT escape codes instead of PDCurses.

    PDCurses writes cell-by-cell to the old console buffer, and Windows Terminal
    only sees that through ConPTY's translation - sprites went missing or
    flickered. Here each frame is one write: only rows that changed, wrapped in
    synchronized-output markers so the terminal shows it all at once.
    Mimics just the part of the curses API that this game uses.
    """
    error = Exception
    A_BOLD, A_REVERSE, A_DIM = 1 << 8, 1 << 9, 1 << 10
    COLOR_BLACK, COLOR_RED, COLOR_GREEN, COLOR_YELLOW = 0, 1, 2, 3
    COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, COLOR_WHITE = 4, 5, 6, 7
    KEY_UP, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_ENTER = 259, 258, 260, 261, 343
    _ARROWS = {"H": KEY_UP, "P": KEY_DOWN, "K": KEY_LEFT, "M": KEY_RIGHT}

    def __init__(self):
        self.pairs = {}

    def curs_set(self, n): pass
    def has_colors(self): return True
    def start_color(self): pass
    def use_default_colors(self): pass
    def init_pair(self, n, fg, bg): self.pairs[n] = fg
    def color_pair(self, n): return n

    def sgr(self, attr):
        codes = ["0"]
        if attr & self.A_BOLD: codes.append("1")
        if attr & self.A_DIM: codes.append("2")
        if attr & self.A_REVERSE: codes.append("7")
        if (attr & 0xFF) in self.pairs:
            codes.append(str(30 + self.pairs[attr & 0xFF]))
        return "\x1b[" + ";".join(codes) + "m"

    def wrapper(self, fn):
        import ctypes
        k32 = ctypes.windll.kernel32
        out = k32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(out, ctypes.byref(mode)):
            k32.SetConsoleMode(out, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        w = sys.__stdout__.write
        w("\x1b[?1049h\x1b[?25l\x1b[2J")  # alternate screen, hide cursor
        sys.__stdout__.flush()
        try:
            return fn(_VTScreen(self))
        finally:
            w("\x1b[0m\x1b[?25h\x1b[?1049l")
            sys.__stdout__.flush()


class _VTScreen:
    def __init__(self, c):
        self.c = c
        self.prev = []      # rows last sent to the terminal
        self.size = None
        self.full = True
        self._con = None    # _ConsoleInput, or False when stdin is not a console
        self._measure()
        self.erase()

    def _measure(self):
        try:
            sz = os.get_terminal_size(sys.__stdout__.fileno())
            size = (sz.lines, sz.columns)
        except OSError:
            size = (24, 80)
        if size != self.size:
            self.size, self.full = size, True

    def nodelay(self, b): pass
    def keypad(self, b): pass
    def clear(self): self.full = True
    def clearok(self, b): self.full = self.full or b
    def getmaxyx(self): return self.size

    def erase(self):
        self._measure()  # once per frame, picks up pane resizes
        h, w = self.size
        self.cells = [[(" ", 0)] * w for _ in range(h)]

    def addstr(self, y, x, s, attr=0):
        h, w = self.size
        if not 0 <= y < h:
            return
        row = self.cells[y]
        for i, ch in enumerate(s):
            if 0 <= x + i < w:
                row[x + i] = (ch, attr)

    def refresh(self):
        h, w = self.size
        out = ["\x1b[?2026h"]  # begin synchronized update
        if self.full:
            out.append("\x1b[0m\x1b[2J")
            self.prev = []
        new = []
        for y, row in enumerate(self.cells):
            parts, cur = [], None
            for ch, a in row[: w - 1]:  # never touch the last column (auto-wrap)
                if a != cur:
                    parts.append(self.c.sgr(a))
                    cur = a
                parts.append(ch)
            line = "".join(parts)
            new.append(line)
            if y >= len(self.prev) or self.prev[y] != line:
                out.append("\x1b[%d;1H%s\x1b[0m\x1b[K" % (y + 1, line))
        out.append("\x1b[?2026l")
        self.prev, self.full = new, False
        sys.__stdout__.write("".join(out))
        sys.__stdout__.flush()

    def getch(self):
        if self._con is None:
            self._con = _ConsoleInput.open() or False
        if self._con:
            return self._con.getch()
        import msvcrt
        if not msvcrt.kbhit():
            return -1
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return self.c._ARROWS.get(msvcrt.getwch(), -1)
        if ch == "\x03":
            raise KeyboardInterrupt
        return ord(ch)


class _ConsoleInput:
    """Windows: read the console's input records instead of msvcrt's characters.
    Records carry key UP as well, so KEYS knows what is held (see KeyTracker)."""

    @classmethod
    def open(cls):
        try:
            return cls()
        except Exception:
            return None

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class KEY(ctypes.Structure):
            _fields_ = [("down", wintypes.BOOL), ("repeat", wintypes.WORD), ("vk", wintypes.WORD),
                        ("scan", wintypes.WORD), ("ch", wintypes.WCHAR), ("state", wintypes.DWORD)]

        class EV(ctypes.Union):
            _fields_ = [("key", KEY), ("focus", wintypes.BOOL), ("pad", ctypes.c_byte * 16)]

        class REC(ctypes.Structure):
            _fields_ = [("type", wintypes.WORD), ("ev", EV)]

        self.c = ctypes
        k32 = self.k32 = ctypes.WinDLL("kernel32")
        k32.GetStdHandle.restype = wintypes.HANDLE
        k32.GetStdHandle.argtypes = [wintypes.DWORD]
        k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.GetNumberOfConsoleInputEvents.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(REC), wintypes.DWORD,
                                          ctypes.POINTER(wintypes.DWORD)]
        self.h = k32.GetStdHandle(wintypes.DWORD(-10 & 0xFFFFFFFF))   # STD_INPUT_HANDLE
        mode = wintypes.DWORD()
        if not k32.GetConsoleMode(self.h, ctypes.byref(mode)):
            raise OSError("stdin is not a console")
        self.buf, self.n, self.queue = (REC * 64)(), wintypes.DWORD(), []

    def getch(self):
        if not self.queue:
            self._pump()
        return self.queue.pop(0) if self.queue else -1

    def _pump(self):
        k32, c = self.k32, self.c
        if not k32.GetNumberOfConsoleInputEvents(self.h, c.byref(self.n)) or not self.n.value:
            return
        if not k32.ReadConsoleInputW(self.h, self.buf, 64, c.byref(self.n)):
            return
        for r in self.buf[:self.n.value]:
            if r.type == 0x0001:      # KEY_EVENT
                k = r.ev.key
                self.queue += key_event(bool(k.down), k.vk, ord(k.ch) if k.ch else 0, k.repeat)
            elif r.type == 0x0010 and not r.ev.focus:   # FOCUS_EVENT: lost focus
                KEYS.clear()


if os.name == "nt":
    curses = _VTCurses()
else:
    import curses


class KeyTracker:
    """Which keys are physically held right now, from real key-down/up events.

    A terminal normally sends characters only: a held key shows up as OS auto-repeat,
    and pressing a second key stops the first key's repeat - so a game that guesses
    "held" from the repeats loses the run key the moment you stab or jump.
    Windows consoles (and Windows Terminal's win32-input-mode) report key UP as well.
    Hosts that only see text (VS Code's terminal) fake an up right after every down, so
    `real` switches on only once the input proves it: an up arriving well after its
    down, or a key repeating with no up in between. Until then since() says None and the
    game keeps its key-repeat emulation.
    """
    STALE = 10.0    # no key event at all for this long: assume the ups were lost

    def __init__(self, clock=time.time):
        self.clock = clock
        self.down = {}      # key id -> when it went down
        self.real = False
        self.last = 0.0

    def event(self, key, is_down):
        now = self.last = self.clock()
        if is_down:
            if key in self.down:
                self.real = True    # auto-repeat with no up in between
            else:
                self.down[key] = now
        else:
            t = self.down.pop(key, None)
            if t is not None and now - t >= 0.03:
                self.real = True

    def clear(self):
        """Focus left the game: ups for the held keys will go somewhere else."""
        self.down.clear()

    def since(self, keys):
        """When the latest-pressed of `keys` went down if one is held, else None.
        None also while key-ups aren't known to be real."""
        if not self.real or self.clock() - self.last > self.STALE:
            return None
        ts = [self.down[k] for k in keys if k in self.down]
        return max(ts) if ts else None


KEYS = KeyTracker()

# virtual-key codes -> what getch() returns (curses KEY_LEFT/UP/RIGHT/DOWN)
_VK_ARROWS = {0x25: 260, 0x26: 259, 0x27: 261, 0x28: 258}


def _key_id(vk):
    """Layout-free id of a key for KEYS: its lowercase letter / digit / space, or arrow code."""
    if vk in _VK_ARROWS:
        return _VK_ARROWS[vk]
    if 0x41 <= vk <= 0x5A:
        return vk + 32
    if 0x30 <= vk <= 0x39 or vk == 0x20:
        return vk
    return None


def key_event(is_down, vk, ch, repeat=1):
    """One key event (a console record, or a win32-input-mode sequence): updates KEYS and
    returns the presses getch() should report for it."""
    kid = _key_id(vk)
    if kid is not None:
        KEYS.event(kid, is_down)
    if not is_down:
        return []
    if ch == 3:
        raise KeyboardInterrupt
    if vk in _VK_ARROWS:
        code = _VK_ARROWS[vk]
    elif vk == 0x0D:
        code = 13
    elif ch:
        code = ch
    else:
        return []           # shift, ctrl, ... on their own
    return [code] * max(1, min(repeat, 4))


# win32-input-mode: CSI Vk ; Sc ; Uc ; Kd ; Cs ; Rc _
_W32 = re.compile(r"\x1b\[(\d*);(\d*);(\d*);(\d*);(\d*)(?:;(\d*))?_")
_PARTIAL = re.compile(r"\x1b(\[[\d;]*)?$")


def parse_input(buf, flush):
    """Turn raw getch() codes into presses, decoding win32-input-mode key events and
    focus reports (ESC [ I / ESC [ O) on the way. `buf` is consumed in place; a
    sequence cut in half stays in it for the next call, unless `flush`."""
    out = []
    while buf:
        if buf[0] == 27:
            s = "".join(chr(c) if c < 256 else "\0" for c in buf[:64])
            m = _W32.match(s)
            if m:
                vk, _, uc, kd, _, rc = m.groups()
                del buf[:m.end()]
                out += key_event(kd == "1", int(vk or 0), int(uc or 0), int(rc or 1))
                continue
            if s.startswith(("\x1b[I", "\x1b[O")):
                if s[2] == "O":
                    KEYS.clear()
                del buf[:3]
                continue
            if not flush and _PARTIAL.match(s):
                break       # the rest of the sequence is still on its way
        out.append(buf.pop(0))
    return out


class _WinInputScreen:
    """Linux/WSL inside Windows Terminal: wraps the curses screen. The terminal is asked
    for win32-input-mode (key down AND up) and focus reports; if it ignores the request
    keys arrive as plain characters and pass straight through."""
    ON, OFF = "\x1b[?9001h\x1b[?1004h", "\x1b[?9001l\x1b[?1004l"

    def __init__(self, scr):
        self.scr, self.buf, self.queue, self.t = scr, [], [], 0.0

    def __getattr__(self, name):
        return getattr(self.scr, name)

    def getch(self):
        if not self.queue:
            while True:
                c = self.scr.getch()
                if c == -1:
                    break
                if not self.buf:
                    self.t = time.time()
                self.buf.append(c)
            self.queue += parse_input(self.buf, time.time() - self.t > 0.05)
        return self.queue.pop(0) if self.queue else -1


def _tty_write(s):
    try:
        sys.__stdout__.write(s)
        sys.__stdout__.flush()
    except Exception:
        pass


STATE = sys.argv[1] if len(sys.argv) > 1 else None        # file written by the hooks
CLAUDE_PANE = sys.argv[2] if len(sys.argv) > 2 else None  # tmux pane id, "wt" or "window"
ALIVE = STATE + ".alive" if STATE else None               # heartbeat the hook checks


def key_repeat_timing():
    """(delay before the OS starts repeating a held key, gap between repeats), seconds.

    Terminals send no key-up, so games emulate "held" from the repeats. On Windows
    the delay is 0.25-1.0 s and the rate 2.5-30/s, both user settings; elsewhere
    there is no portable way to ask, so a typical value is used.
    """
    delay, interval = 0.5, 0.04
    if os.name == "nt":
        try:
            import ctypes
            v = ctypes.c_uint32()
            if ctypes.windll.user32.SystemParametersInfoW(0x0016, 0, ctypes.byref(v), 0):  # GETKEYBOARDDELAY
                delay = (v.value + 1) * 0.25
            if ctypes.windll.user32.SystemParametersInfoW(0x000A, 0, ctypes.byref(v), 0):  # GETKEYBOARDSPEED
                interval = 1.0 / (2.5 + v.value * 27.5 / 31)
        except Exception:
            pass
    return delay, interval


def read_state():
    """Returns (mtime, text) of the hook state file, or None."""
    if not STATE:
        return None
    try:
        return (os.stat(STATE).st_mtime_ns, open(STATE).read().strip())
    except Exception:
        return None


def heartbeat():
    if ALIVE:
        try:
            open(ALIVE, "w").close()
        except Exception:
            pass


def _host_window():
    """Windows: the Claude window (VS Code, desktop app, console) the hook saved, or None."""
    if os.name != "nt" or not STATE:
        return None
    try:
        with open(STATE + ".host") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return None


def can_focus():
    """Whether Enter can take you back to Claude. tmux and Windows Terminal panes: always.
    Own window: only where we know the Claude window (Windows)."""
    return CLAUDE_PANE != "window" or _host_window() is not None


def focus_claude():
    KEYS.clear()    # the key-ups go to Claude's pane from here on
    if CLAUDE_PANE == "vscode":  # a terminal in VS Code's panel: the extension focuses the chat
        try:
            import vscodebridge
            vscodebridge.send(int(os.environ["WAITING_GAMES_EXT"]), {"type": "focus-claude"})
        except (KeyError, ValueError, ImportError):
            pass
        return
    if CLAUDE_PANE == "window":  # its own window: bring the Claude window back
        hwnd = _host_window()
        if hwnd:
            import winhost
            winhost.activate(hwnd)
        return
    if CLAUDE_PANE == "wt":
        subprocess.Popen(["wt" if os.name == "nt" else "wt.exe", "-w", "0", "move-focus", "up"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    elif CLAUDE_PANE:
        subprocess.call(["tmux", "select-pane", "-t", CLAUDE_PANE])


def is_menu_key(k):
    """M or Tab opens the game picker, in every game."""
    return k in (ord("m"), ord("M"), 9)


def _put(scr, y, x, s, attr=0):
    h, w = scr.getmaxyx()
    if 0 <= y < h and 0 <= x < w - 1:
        try:
            scr.addstr(y, x, s[: w - 1 - x], attr)
        except curses.error:
            pass


def pick_game(scr, current):
    """Selection menu over the current game. Returns the chosen game's name, or None
    to go back to the current one (Esc / M / Tab). The game stays paused meanwhile;
    picking another game ends this one."""
    scr.nodelay(True)
    sel = next((i for i, g in enumerate(GAMES) if g[0] == current), 0)
    last_beat = 0
    while True:
        now = time.time()
        if now - last_beat >= 1:
            heartbeat()
            last_beat = now
        while True:
            k = scr.getch()
            if k == -1:
                break
            if k in (27,) or is_menu_key(k):
                return None
            if k in (ord("q"), ord("Q")):
                return "quit"
            if k in (curses.KEY_UP, ord("w"), ord("W"), ord("k"), ord("K")):
                sel = (sel - 1) % len(GAMES)
            elif k in (curses.KEY_DOWN, ord("s"), ord("S"), ord("j"), ord("J")):
                sel = (sel + 1) % len(GAMES)
            elif ord("1") <= k < ord("1") + len(GAMES):
                sel = k - ord("1")
                return GAMES[sel][0]
            elif k in (10, 13, ord(" "), curses.KEY_ENTER):
                return GAMES[sel][0]
        h, w = scr.getmaxyx()
        scr.erase()
        rows = ["  CHOOSE A GAME  ", ""]
        for i, (name, title, pitch) in enumerate(GAMES):
            mark = ">" if i == sel else " "
            now_playing = "  (playing)" if name == current else ""
            rows.append("%s %d. %s%s" % (mark, i + 1, title, now_playing))
            rows.append("     " + pitch)
        rows += ["", "Up/Down + Enter, or 1-%d    Esc/M: back    Q: quit" % len(GAMES)]
        top = max(0, (h - len(rows)) // 2)
        width = max(len(r) for r in rows)
        x = max(0, (w - width) // 2)
        for i, r in enumerate(rows):
            attr = curses.A_REVERSE if i == 0 else 0
            if r.startswith(">"):
                attr = curses.A_BOLD | curses.A_REVERSE
            elif r.startswith("     "):
                attr = curses.A_DIM
            _put(scr, top + i, x, r.ljust(width) if attr & curses.A_REVERSE else r, attr)
        scr.refresh()
        time.sleep(1.0 / 30)


def last_game():
    try:
        name = open(LAST_GAME).read().strip()
        if any(g[0] == name for g in GAMES):
            return name
    except Exception:
        pass
    return GAMES[0][0]


def run(first=None):
    """Run games in one terminal session: a game's main(scr) returns the name of the
    game to switch to (picked in the menu), or None to quit."""
    import importlib
    name = first or last_game()
    heartbeat()

    def loop(scr):
        nonlocal name
        if os.name != "nt" and os.environ.get("WT_SESSION"):
            scr = _WinInputScreen(scr)
            _tty_write(_WinInputScreen.ON)
        try:
            games(scr)
        finally:
            if isinstance(scr, _WinInputScreen):
                _tty_write(_WinInputScreen.OFF)

    def games(scr):
        nonlocal name
        while name:
            try:
                os.makedirs(DATA, exist_ok=True)
                open(LAST_GAME, "w").write(name)
            except Exception:
                pass
            nxt = importlib.import_module(name).main(scr)
            name = nxt if any(g[0] == nxt for g in GAMES) else None

    try:
        curses.wrapper(loop)
    except KeyboardInterrupt:
        pass
    finally:
        if ALIVE:
            try:
                os.remove(ALIVE)
            except Exception:
                pass

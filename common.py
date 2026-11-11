"""Shared by the waiting games: terminal drawing on Windows, the Claude Code hook
protocol (state file, heartbeat, focus), and the game picker.

argv (set by hook.py): <state file> <claude pane: tmux pane id, "wt" or "window">
"""
import os, subprocess, sys, time

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
        import msvcrt
        if not msvcrt.kbhit():
            return -1
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return self.c._ARROWS.get(msvcrt.getwch(), -1)
        if ch == "\x03":
            raise KeyboardInterrupt
        return ord(ch)


if os.name == "nt":
    curses = _VTCurses()
else:
    import curses


STATE = sys.argv[1] if len(sys.argv) > 1 else None        # file written by the hooks
CLAUDE_PANE = sys.argv[2] if len(sys.argv) > 2 else None  # tmux pane id, "wt" or "window"
ALIVE = STATE + ".alive" if STATE else None               # heartbeat the hook checks


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


def focus_claude():
    if CLAUDE_PANE == "window":
        return  # its own window: nothing to move focus to
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

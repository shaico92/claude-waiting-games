"""Windows only: find the window Claude Code is typed in, and bring it back to the front.

The hook runs the moment you send a prompt, so the foreground window then IS the Claude
window (VS Code, the Claude desktop app, a console). It is saved next to the game's state
file; Enter in the game, which opens in its own window, activates it again.
Standard library only (ctypes). Every function is safe to call anywhere: on failure they
return empty values instead of raising.
"""
import os


def _api():
    import ctypes
    from ctypes import wintypes
    k32, u32 = ctypes.windll.kernel32, ctypes.windll.user32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    u32.GetForegroundWindow.restype = wintypes.HWND
    u32.GetWindow.restype = wintypes.HWND
    u32.IsWindow.argtypes = u32.IsIconic.argtypes = u32.IsWindowVisible.argtypes = [wintypes.HWND]
    u32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    u32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u32.SetForegroundWindow.argtypes = [wintypes.HWND]
    u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    return ctypes, wintypes, k32, u32


def _processes():
    """{pid: (parent pid, exe name)} for every running process."""
    ctypes, wintypes, k32, _ = _api()

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    procs, pe = {}, PE()
    pe.dwSize = ctypes.sizeof(PE)
    ok = k32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        procs[pe.th32ProcessID] = (pe.th32ParentProcessID, pe.szExeFile)
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return procs


def process_chain(depth=8):
    """[(pid, exe name)] for this process and the ones above it: python <- claude <- Code ..."""
    if os.name != "nt":
        return []
    try:
        procs = _processes()
        out, pid = [], os.getpid()
        while pid in procs and len(out) < depth:
            parent, name = procs[pid]
            out.append((pid, name))
            if parent == pid or parent not in procs:
                break
            pid = parent
        return out
    except Exception:
        return []


def _pid_of(u32, hwnd):
    import ctypes
    from ctypes import wintypes
    pid = wintypes.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _windows_of(pid):
    """Visible, titled, unowned top-level windows of one process."""
    ctypes, wintypes, _, u32 = _api()
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if (u32.IsWindowVisible(hwnd) and u32.GetWindowTextLengthW(hwnd) > 0
                and not u32.GetWindow(hwnd, 4)  # GW_OWNER: skip dialogs and tool windows
                and _pid_of(u32, hwnd) == pid):
            found.append(hwnd)
        return True

    u32.EnumWindows(proc(cb), 0)
    return found


def find_host_window():
    """(hwnd, how) of the window the user just typed the prompt in; (None, why) if unknown.

    1. the foreground window, when it belongs to a process above us (VS Code, the desktop
       app: their window is owned by an ancestor of the claude process);
    2. else a window of the nearest such ancestor;
    3. else the foreground window anyway (a classic console belongs to conhost, which is
       not an ancestor)."""
    if os.name != "nt":
        return None, "not windows"
    try:
        _, _, _, u32 = _api()
        above = [pid for pid, _ in process_chain()][1:]
        fg = u32.GetForegroundWindow()
        if fg and _pid_of(u32, fg) in above:
            return fg, "foreground"
        for pid in above:
            wins = _windows_of(pid)
            if wins:
                return wins[0], "ancestor"
        if fg:
            return fg, "foreground-fallback"
        return None, "no window"
    except Exception as e:
        return None, "error: %s" % type(e).__name__


def exe_name(hwnd):
    """Exe name of a window's process, for the log (never the window title)."""
    try:
        _, _, _, u32 = _api()
        return _processes().get(_pid_of(u32, hwnd), (0, "?"))[1]
    except Exception:
        return "?"


def activate(hwnd):
    """Bring a window to the front (restoring it if minimized). True if it now is."""
    if os.name != "nt" or not hwnd:
        return False
    try:
        _, _, _, u32 = _api()
        if not u32.IsWindow(hwnd):
            return False
        if u32.IsIconic(hwnd):
            u32.ShowWindow(hwnd, 9)  # SW_RESTORE
        # Windows only lets the foreground process take focus; a tap on Alt makes it count
        # the caller as having just received input.
        u32.keybd_event(0x12, 0, 0, 0)
        ok = u32.SetForegroundWindow(hwnd)
        u32.keybd_event(0x12, 0, 2, 0)
        return bool(ok)
    except Exception:
        return False

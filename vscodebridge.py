"""Talk to the Waiting Games companion extension for VS Code (see vscode/).

No sockets, no ports: both sides use one folder of small JSON files.
  <spool>/ext-<pid>.json         written by the extension every 2 s: its extension-host pid
                                 and the workspace folders of its window ("I am alive")
  <spool>/req-<pid>-<ns>.json    requests to the extension with that pid (hook or game ->
                                 extension): {"type": "open" | "show" | "focus-claude", ...}
The extension host is the parent of the claude process the VS Code extension starts, so a
hook finds *its own* window exactly by looking for that pid among its ancestors.
Standard library only; every function is safe to call from a hook (it never raises).
"""
import json, os, tempfile, time

SPOOL = os.environ.get("WAITING_GAMES_SPOOL") or os.path.join(tempfile.gettempdir(), "claude-games-vscode")
FRESH = 6        # seconds a presence file counts as alive (the extension refreshes every 2)
MAX_AGE = 30     # the extension ignores requests older than this


def ancestor_pids():
    """pids of this process and the ones above it."""
    try:
        if os.name == "nt":
            import winhost
            return [pid for pid, _ in winhost.process_chain(12)]
        out, pid = [], os.getpid()
        while pid > 1 and len(out) < 12:  # Linux/WSL: walk /proc
            out.append(pid)
            with open("/proc/%d/stat" % pid) as f:
                pid = int(f.read().rsplit(")", 1)[1].split()[1])  # field 4 = ppid
        return out
    except Exception:
        return [os.getpid(), os.getppid()]


def _inside(path, folder):
    p, f = os.path.normcase(os.path.normpath(path)), os.path.normcase(os.path.normpath(folder))
    return p == f or p.startswith(f.rstrip(os.sep) + os.sep)


def find_extension(cwd=None, chain=None):
    """pid of the live extension that serves this Claude, or None.
    Exact: its pid is an ancestor of ours. Else: the only live window whose workspace
    folders contain `cwd` (several matching windows = ambiguous = None)."""
    try:
        above = set(chain if chain is not None else ancestor_pids())
        now, near = time.time(), []
        for name in os.listdir(SPOOL):
            if not (name.startswith("ext-") and name.endswith(".json")):
                continue
            path = os.path.join(SPOOL, name)
            try:
                if now - os.stat(path).st_mtime > FRESH:
                    continue
                with open(path, encoding="utf-8") as f:
                    info = json.load(f)
                pid = int(info["pid"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if pid in above:
                return pid
            if cwd and any(_inside(cwd, w) for w in info.get("workspaces", []) if w):
                near.append(pid)
        return near[0] if len(near) == 1 else None
    except Exception:
        return None


def send(ext_pid, payload):
    """Drop a request for the extension with pid `ext_pid`. True if it was written."""
    try:
        os.makedirs(SPOOL, exist_ok=True)
        ns = time.time_ns()
        path = os.path.join(SPOOL, "req-%d-%d.json" % (ext_pid, ns))
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dict(payload, ts=int(time.time() * 1000)), f)
        os.replace(tmp, path)
        return True
    except Exception:
        return False

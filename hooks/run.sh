#!/bin/sh
# Runs hook.py with the first Python 3 found. Used when hooks run in bash/sh
# (Linux, macOS, WSL, Windows with Git Bash). Never fails the hook.
for p in python3 python py; do
  command -v "$p" >/dev/null 2>&1 || continue
  "$p" -c 'import sys; sys.exit(sys.version_info[0] < 3)' </dev/null >/dev/null 2>&1 || continue
  exec "$p" "$(dirname "$0")/../hook.py" "$@"
done
exit 0

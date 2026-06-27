#!/usr/bin/env bash
# Add kiki-compressor to your Claude Desktop config (macOS / Linux).
#
#   ./install_claude_desktop.sh                 # default reranker backend
#   ./install_claude_desktop.sh --dry-run       # preview, change nothing
#   ./install_claude_desktop.sh --model-kind t5 --repo-dir ./attention_compressor
#
# Any options are forwarded to add_to_claude_desktop.py (run with --help to see them).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Prefer the project's venv Python; fall back to system python3.
PY="$DIR/.venv/bin/python"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3 || true)"
fi
if [ -z "${PY:-}" ]; then
  echo "No Python found. Create the venv first:  python3 -m venv .venv  (see README)." >&2
  exit 1
fi

exec "$PY" "$DIR/add_to_claude_desktop.py" "$@"

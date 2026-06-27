#!/usr/bin/env python3
"""
Add (or update) the kiki-compressor MCP server in your Claude Desktop config.

Cross-platform: works on macOS, Windows, and Linux. Run it with any Python 3 —
it figures out the right venv-python path and config location for the current OS,
backs up any existing config, merges the entry without clobbering other servers,
and writes it back.

Usage:
    python add_to_claude_desktop.py [options]

Common options:
    --name NAME           server key in the config        (default: kiki-compressor)
    --model-kind KIND     reranker | t5 | causal          (default: reranker)
    --model ID            HuggingFace model id            (default: MiniLM reranker)
    --window N            sentences per scored unit        (default: 1)
    --repo-dir PATH       attention_compressor path (t5/causal backends)
    --device DEV          cuda | mps | cpu                 (default: auto)
    --dry-run             print what would be written, change nothing
"""
import argparse
import json
import os
import platform
import shutil
import sys
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MODEL = {
    "reranker": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "t5": "google/flan-t5-base",
    "causal": "Qwen/Qwen2-0.5B-Instruct",
}


def venv_python() -> str:
    if platform.system() == "Windows":
        return os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
    return os.path.join(PROJECT_DIR, ".venv", "bin", "python")


def config_path() -> str:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))
        return os.path.join(base, "Claude", "claude_desktop_config.json")
    if system == "Darwin":
        return os.path.expanduser(
            "~/Library/Application Support/Claude/claude_desktop_config.json"
        )
    # Linux / other (Claude Desktop is unofficial here, but be helpful)
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "Claude", "claude_desktop_config.json")


def load_config(path: str) -> dict:
    """Return the existing config as a dict. Back up and start fresh if unreadable."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("top-level config is not a JSON object")
        return data
    except (json.JSONDecodeError, ValueError) as e:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = f"{path}.corrupt-{ts}"
        shutil.copy2(path, backup)
        print(f"!! Existing config is not valid JSON ({e}).")
        print(f"!! Backed it up to: {backup}")
        print("!! Starting from an empty config (your backup is safe).")
        return {}


def main() -> int:
    p = argparse.ArgumentParser(description="Install kiki-compressor into Claude Desktop.")
    p.add_argument("--name", default="kiki-compressor")
    p.add_argument("--model-kind", default="reranker", choices=["reranker", "t5", "causal"])
    p.add_argument("--model", default=None)
    p.add_argument("--window", default="1")
    p.add_argument("--repo-dir", default=None)
    p.add_argument("--device", default=None)
    p.add_argument("--config", default=None, help="override config path")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    py = venv_python()
    server = os.path.join(PROJECT_DIR, "server.py")
    model = args.model or DEFAULT_MODEL[args.model_kind]

    # Sanity checks
    if not os.path.exists(py):
        print(f"ERROR: venv Python not found at:\n  {py}")
        print("Create it first:  python3 -m venv .venv  (see README setup steps).")
        return 1
    if not os.path.exists(server):
        print(f"ERROR: server.py not found at:\n  {server}")
        return 1

    env = {
        "QUITO_MODEL_KIND": args.model_kind,
        "QUITO_MODEL": model,
        "QUITO_RERANK_WINDOW": str(args.window),
    }
    if args.repo_dir:
        env["QUITO_REPO_DIR"] = os.path.abspath(args.repo_dir)
    if args.device:
        env["QUITO_DEVICE"] = args.device

    entry = {"command": py, "args": [server], "env": env}

    cfg_path = args.config or config_path()
    data = load_config(cfg_path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    overwriting = args.name in servers
    servers[args.name] = entry
    data["mcpServers"] = servers

    rendered = json.dumps(data, indent=2) + "\n"

    if args.dry_run:
        print(f"[dry-run] would write to: {cfg_path}")
        print(f"[dry-run] server entry '{args.name}'"
              + (" (OVERWRITES existing)" if overwriting else " (new)") + ":")
        print(json.dumps({args.name: entry}, indent=2))
        return 0

    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    if os.path.exists(cfg_path):
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        backup = f"{cfg_path}.backup-{ts}"
        shutil.copy2(cfg_path, backup)
        print(f"Backed up existing config -> {backup}")

    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(rendered)

    print(f"{'Updated' if overwriting else 'Added'} server '{args.name}' in:\n  {cfg_path}")
    print(f"  command: {py}")
    print(f"  model:   {model}  (kind={args.model_kind})")
    if not os.path.isdir(os.path.dirname(cfg_path)):
        print("  note: Claude Desktop config dir didn't exist — is the app installed?")
    print("\nDone. Restart Claude Desktop for the compress_context tool to appear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

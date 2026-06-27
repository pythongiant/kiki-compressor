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
import subprocess
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


def add_to_claude_code(name: str, entry: dict, scope: str, dry_run: bool) -> bool:
    """Register the MCP server with Claude Code via the `claude` CLI (safer than hand-editing
    ~/.claude.json). Idempotent: removes any existing entry in this scope first, then re-adds."""
    claude = shutil.which("claude")
    payload = json.dumps(entry)
    if not claude:
        print("!! `claude` CLI not on PATH — skipping Claude Code registration. Add it manually:")
        print(f"   claude mcp add-json {name} '{payload}' -s {scope}")
        return False
    if dry_run:
        print(f"[dry-run] Claude Code: would run "
              f"`claude mcp add-json {name} '<json>' -s {scope}`")
        return True
    # Remove first so re-runs don't fail on a duplicate name; ignore "not found".
    subprocess.run([claude, "mcp", "remove", name, "-s", scope],
                   capture_output=True, text=True)
    res = subprocess.run([claude, "mcp", "add-json", name, payload, "-s", scope],
                         capture_output=True, text=True)
    if res.returncode == 0:
        print(f"Registered '{name}' with Claude Code (scope={scope}).")
        return True
    print(f"!! Claude Code registration failed (exit {res.returncode}):")
    print("  " + (res.stderr or res.stdout or "").strip())
    return False


def default_skills_dir() -> str:
    # Claude Code / Agent Skills location (cross-platform).
    return os.path.expanduser(os.path.join("~", ".claude", "skills"))


def install_skill(skills_dir: str, dry_run: bool):
    """Copy the bundled compress-and-answer skill into a skills directory."""
    src = os.path.join(PROJECT_DIR, "skills", "compress-and-answer")
    if not os.path.isdir(src):
        print(f"!! skill source not found at {src} — skipping skill install.")
        return None
    dst = os.path.join(skills_dir, "compress-and-answer")
    if dry_run:
        print(f"[dry-run] would install skill 'compress-and-answer' -> {dst}")
        return dst
    os.makedirs(skills_dir, exist_ok=True)
    shutil.copytree(src, dst, dirs_exist_ok=True)
    print(f"Installed skill 'compress-and-answer' -> {dst}")
    return dst


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
    p.add_argument("--config", default=None, help="override Claude Desktop config path")
    p.add_argument("--no-desktop", action="store_true",
                   help="do not write the Claude Desktop config")
    p.add_argument("--no-claude-code", action="store_true",
                   help="do not register the server with Claude Code")
    p.add_argument("--claude-code-scope", default="user",
                   choices=["local", "user", "project"],
                   help="Claude Code config scope (default: user = all projects)")
    p.add_argument("--no-skill", action="store_true",
                   help="do not install the compress-and-answer skill")
    p.add_argument("--skills-dir", default=None,
                   help="where to install the skill (default: ~/.claude/skills)")
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

    skills_dir = args.skills_dir or default_skills_dir()

    # --- Claude Desktop config ---
    if not args.no_desktop:
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
            print(f"[dry-run] Claude Desktop: would write to {cfg_path}")
            print(f"[dry-run] server entry '{args.name}'"
                  + (" (OVERWRITES existing)" if overwriting else " (new)") + ":")
            print(json.dumps({args.name: entry}, indent=2))
        else:
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            if os.path.exists(cfg_path):
                ts = datetime.now().strftime("%Y%m%d%H%M%S")
                backup = f"{cfg_path}.backup-{ts}"
                shutil.copy2(cfg_path, backup)
                print(f"Backed up existing config -> {backup}")
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(rendered)
            print(f"{'Updated' if overwriting else 'Added'} server '{args.name}' in Claude Desktop:")
            print(f"  {cfg_path}")
            print(f"  command: {py}")
            print(f"  model:   {model}  (kind={args.model_kind})")

    # --- Claude Code (via the `claude` CLI) ---
    if not args.no_claude_code:
        add_to_claude_code(args.name, entry, args.claude_code_scope, dry_run=args.dry_run)

    # --- compress-and-answer skill ---
    if not args.no_skill:
        dst = install_skill(skills_dir, dry_run=args.dry_run)
        if dst and not args.dry_run:
            print("  note: that path is read by Claude Code. For Claude Desktop, also add the skill")
            print(f"        via Settings -> Capabilities/Skills, pointing at:\n"
                  f"        {os.path.join(PROJECT_DIR, 'skills', 'compress-and-answer')}")

    if args.dry_run:
        print("\n[dry-run] nothing was changed.")
        return 0

    print("\nDone. Restart Claude Desktop, and in Claude Code reconnect MCP "
          "(/mcp or restart), for the compress_context tool to appear.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Single entry point for the novel-style-forge skill.

Prepares an isolated Python with jieba (the only dependency), then dispatches
to the style analyzer or the draft comparator. No network calls during use.

  python run.py check
  python run.py setup
  python run.py analyze --input sample.txt --out profile.json [--title ...] [--author ...]
  python run.py compare --profile profile.json --input draft.txt --out comparison.json [--top 8]
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import venv
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
VENV = Path.home() / ".workbuddy" / ".cache" / "novel-style-forge-venv"
COMMANDS = {"check", "setup", "analyze", "compare"}


def venv_python() -> Path | None:
    rel = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    p = VENV / rel
    return p if p.exists() else None


def has_jieba(python: str) -> bool:
    return subprocess.run([python, "-c", "import jieba"], capture_output=True).returncode == 0


def ensure_env() -> str:
    if importlib.util.find_spec("jieba") is not None:
        return sys.executable
    p = venv_python()
    if p and has_jieba(str(p)):
        return str(p)
    if not p:
        print(f"[env] Creating isolated Python environment at {VENV} ...", flush=True)
        VENV.parent.mkdir(parents=True, exist_ok=True)
        venv.create(str(VENV), with_pip=True)
        p = venv_python()
    if not p:
        raise RuntimeError("Failed to create a Python virtual environment.")
    print("[env] Installing jieba (one-time, needs network) ...", flush=True)
    proc = subprocess.run(
        [str(p), "-m", "pip", "install", "--disable-pip-version-check", "--quiet", "jieba"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not has_jieba(str(p)):
        raise RuntimeError(
            "jieba installation failed. Run `python -m pip install jieba` manually, "
            f"or check network access. pip output: {proc.stderr[-500:]}"
        )
    print("[env] jieba ready.", flush=True)
    return str(p)


def check() -> int:
    python = ensure_env()
    proc = subprocess.run(
        [python, "-c", "import jieba, sys; print(jieba.__version__, sys.version.split()[0])"],
        capture_output=True, text=True,
    )
    print(f"python        : {sys.executable}")
    print(f"runtime used  : {python}")
    print(f"jieba/python  : {proc.stdout.strip() or 'NOT FOUND'}")
    print(f"scripts       : {SCRIPTS}")
    return 0 if proc.returncode == 0 else 1


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    cmd, rest = sys.argv[1], sys.argv[2:]
    try:
        if cmd == "check":
            return check()
        python = ensure_env()
        if cmd == "setup":
            print(f"[env] Ready. Runtime: {python}")
            return 0
        script = SCRIPTS / ("analyze_style.py" if cmd == "analyze" else "compare_style.py")
        if not rest or "--help" in rest or "-h" in rest:
            return subprocess.run([python, str(script), "--help"]).returncode
        return subprocess.run([python, str(script), *rest], cwd=str(SCRIPTS)).returncode
    except (RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

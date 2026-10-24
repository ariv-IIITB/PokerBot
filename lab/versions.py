"""Frozen bot versions for sparring.

A snapshot is a copy of `bot/` + `variant/` in `snapshots/<name>/`, plus a META.txt.
It runs as a subprocess (`python -m bot.main` with cwd = the snapshot), so old and new
code never share module names in one process.

CLI:
    .venv/bin/python -m lab.versions create v1            # from the working tree
    .venv/bin/python -m lab.versions create v0 --ref phase-7   # from a git tag/commit
    .venv/bin/python -m lab.versions list
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Optional

from lab.players import PlayerSpec

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "snapshots"
PACKAGES = ("bot", "variant")


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True).stdout


def create_snapshot(name: str, ref: Optional[str] = None, root: Path = SNAPSHOT_DIR,
                    force: bool = False) -> Path:
    """Copy bot/ + variant/ (from the working tree, or from git `ref`) into root/name."""
    dest = root / name
    if dest.exists():
        if not force:
            raise FileExistsError(f"snapshot {name!r} already exists (use force=True)")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    if ref is None:
        for pkg in PACKAGES:
            shutil.copytree(ROOT / pkg, dest / pkg,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        source = "working tree"
        try:
            source += f" @ {_git('rev-parse', '--short', 'HEAD').decode().strip()} (+ local changes)"
        except Exception:
            pass
    else:
        data = _git("archive", "--format=tar", ref, *PACKAGES)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data")
        source = f"git {ref} @ {_git('rev-parse', '--short', ref).decode().strip()}"
    (dest / "META.txt").write_text(f"source: {source}\ncreated: {dt.datetime.now():%Y-%m-%d %H:%M}\n")
    return dest


def list_snapshots(root: Path = SNAPSHOT_DIR) -> list[str]:
    return sorted(p.name for p in root.iterdir() if (p / "bot" / "main.py").is_file()) \
        if root.is_dir() else []


def snapshot_player(name: str, brain: Optional[str] = None,
                    root: Path = SNAPSHOT_DIR) -> PlayerSpec:
    """PlayerSpec that runs snapshot `name` as a subprocess bot."""
    path = root / name
    if not (path / "bot" / "main.py").is_file():
        raise FileNotFoundError(f"no snapshot at {path}")
    cmd = [sys.executable, "-m", "bot.main"] + (["--brain", brain] if brain else [])
    return PlayerSpec.subprocess(cmd, cwd=str(path), label=f"{name}" + (f":{brain}" if brain else ""))


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="Manage bot snapshots.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("name")
    c.add_argument("--ref", default=None, help="git tag/commit (default: working tree)")
    c.add_argument("--force", action="store_true")
    sub.add_parser("list")
    args = ap.parse_args(argv)
    if args.cmd == "create":
        print(create_snapshot(args.name, args.ref, force=args.force))
    else:
        for n in list_snapshots():
            meta = (SNAPSHOT_DIR / n / "META.txt")
            print(f"{n:<20} {meta.read_text().splitlines()[0] if meta.exists() else ''}")


if __name__ == "__main__":
    main()

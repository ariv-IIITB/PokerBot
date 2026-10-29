"""Build and verify the minimal submission package for the active variant.

    .venv/bin/python -m tools.package_submission [--variant variant/active.json]
        [--brain tier2] [--protocol placeholder] [--out dist/submission] [--zip]

The package contains only what the variant needs: bot/ modules reachable from bot/main.py
(imports scanned with ast) plus the brain, the protocol adapter and the step plugins the
spec uses; variant/spec.py, rules.py, evaluator_hook.py and the spec as variant/active.json;
bot/config/*.json; and data/<variant>/ tables (.npy + meta.json) if they match the spec.
Only bot brains can be packaged (the lab-only CFR brain can't), and CFR strategy files are
never copied.
The repo itself is never modified: everything is copied into --out (a fresh folder).

Then it checks the PACKAGE and fails loudly (exit 1) if any check fails:
  1. import scan: stdlib + numpy (+ scipy imported lazily) only, no network modules,
     no file writes
  2. startup time below --max-startup (default 1.0 s on this machine)
  3. subprocess smoke match from the package folder (no errors / forfeits)
  4. timing benchmark: a full match, projected x2 time below the bank
  5. peak memory below --max-mb (default 900 MB)
"""
from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.game.steps import step_module  # noqa: E402
from bot.main import BRAINS  # noqa: E402
from bot.protocols import ADAPTERS  # noqa: E402
from variant.spec import VariantSpec, spec_hash  # noqa: E402

ALWAYS = ["bot.main", "bot.protocols.placeholder", "bot.brains.tier0", "variant.spec",
          "variant.rules", "variant.evaluator_hook"]
DATA_CAP_MB = 50
FORBIDDEN = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib",
             "telnetlib", "xmlrpc", "socketserver", "asyncio", "webbrowser", "requests",
             "subprocess", "multiprocessing", "sqlite3", "tempfile", "shutil"}


def module_path(mod: str) -> Path:
    p = ROOT / Path(*mod.split("."))
    return p / "__init__.py" if p.is_dir() else p.with_suffix(".py")


def is_module(mod: str) -> bool:
    """A real module file, matched case-exactly (macOS file systems ignore case, so
    "from bot.game.steps import Betting" must not look like a module Betting.py)."""
    p = module_path(mod)
    return p.is_file() and p.name in {f.name for f in p.parent.iterdir()} and \
        (p.name == "__init__.py" or p.parent.name in {f.name for f in p.parent.parent.iterdir()})


def local_imports(path: Path) -> set[str]:
    """Every bot.* / variant.* module imported anywhere in the file (lazy imports too)."""
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.add(node.module)
            for a in node.names:                        # "from bot.game import state"
                out.add(f"{node.module}.{a.name}")
    return {m for m in out if m.split(".")[0] in ("bot", "variant") and is_module(m)}


def needed_modules(spec: VariantSpec, brain: str, protocol: str) -> set[str]:
    roots = set(ALWAYS)
    roots.add(BRAINS[brain].partition(":")[0])
    roots.add(ADAPTERS[protocol].partition(":")[0])
    for t in spec.step_types():
        roots.add(step_module(t))
    for p in spec.payoffs:
        if p.get("type") == "bounty":
            roots.add(step_module("bounty"))
    seen: set[str] = set()
    todo = list(roots)
    while todo:
        m = todo.pop()
        if m in seen:
            continue
        seen.add(m)
        parts = m.split(".")
        for i in range(1, len(parts)):                  # parent packages' __init__
            todo.append(".".join(parts[:i]))
        todo += list(local_imports(module_path(m)) - seen)
    return seen


def runtime_data_files(data_dir: Path) -> list[Path]:
    """The data files the bot reads at runtime: precomputed tables (.npy) and meta.json.
    Never training checkpoints, and never CFR strategies (CFR is lab-only, see
    docs/PART3_ROADMAP.md "CFR status")."""
    return sorted(f for f in data_dir.iterdir()
                  if f.is_file() and (f.suffix == ".npy" or f.name == "meta.json"))


def build(spec_path: Path, brain: str, protocol: str, out: Path) -> dict:
    spec = VariantSpec.load(spec_path)
    if out.exists():
        if not (out / "PACKAGE.json").is_file():
            raise SystemExit(f"{out} exists and is not a previous package: refusing to touch it")
        shutil.rmtree(out)                              # only our own previous output
    out.mkdir(parents=True)
    mods = needed_modules(spec, brain, protocol)
    for m in sorted(mods):
        src = module_path(m)
        dst = out / src.relative_to(ROOT)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    # Trimmed registries: unused plugins are absent, so point the defaults at what we ship.
    _patch(out / "bot" / "main.py", 'DEFAULT_BRAIN = "tier2"', f'DEFAULT_BRAIN = "{brain}"')
    _patch(out / "bot" / "protocols" / "__init__.py", 'DEFAULT = "pokerbots"',
           f'DEFAULT = "{protocol}"')
    shutil.copyfile(spec_path, out / "variant" / "active.json")
    cfg = out / "bot" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "bot" / "config").glob("*.json"):
        shutil.copyfile(f, cfg / f.name)
    data_src = ROOT / "data" / spec.name
    data = False
    if (data_src / "meta.json").is_file():
        meta = json.loads((data_src / "meta.json").read_text())
        if meta.get("spec_hash") == spec_hash(spec):
            dst = out / "data" / spec.name
            dst.mkdir(parents=True)
            files = runtime_data_files(data_src)
            total = sum(f.stat().st_size for f in files)
            if total > DATA_CAP_MB * 1024 * 1024:
                raise SystemExit(f"data/{spec.name} is {total / 1e6:.0f} MB > cap {DATA_CAP_MB} MB")
            for f in files:
                shutil.copyfile(f, dst / f.name)
            data = True
    info = {"variant": spec.name, "spec_hash": spec_hash(spec), "brain": brain,
            "protocol": protocol, "modules": sorted(mods), "data": data}
    (out / "PACKAGE.json").write_text(json.dumps(info, indent=2))
    return info


def _patch(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old in text:
        path.write_text(text.replace(old, new))


# --------------------------------------------------------------------------- checks

def check_imports(out: Path) -> list[str]:
    problems = []
    allowed = set(sys.stdlib_module_names) | {"numpy", "scipy", "bot", "variant"}
    for f in (out / "bot").rglob("*.py"):
        tree = ast.parse(f.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for n in names:
                if n not in allowed or n in FORBIDDEN:
                    problems.append(f"{f.relative_to(out)} imports {n}")
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                if any(m.startswith("scipy") for m in mods):
                    problems.append(f"{f.relative_to(out)}: top-level scipy import (slow startup)")
    return problems


def check_package(out: Path, spec_path: Path, protocol: str, brain: str, hands: int,
                  max_startup: float, max_mb: float) -> list[str]:
    from lab.engine import play_match
    from lab.players import PlayerSpec, SubprocessPlayer
    from lab.timing_bench import run_timing
    problems = check_imports(out)
    spec = VariantSpec.load(spec_path)
    rep = run_timing(brain, "maniac", hands=hands, cwd=out, protocol=protocol,
                     variant=str(spec_path))
    print("  " + rep.summary().replace("\n", "\n  "))
    if rep.startup_s > max_startup:
        problems.append(f"startup {rep.startup_s:.2f}s > {max_startup}s")
    if not rep.ok:
        problems.append(f"timing: projected {rep.projected_used_s:.1f}s vs bank {rep.bank_s}s "
                        f"{'(' + rep.forfeit + ')' if rep.forfeit else ''}")
    bot = SubprocessPlayer([sys.executable, "-m", "bot.main"], cwd=str(out), protocol=protocol)
    m = play_match([bot, PlayerSpec.brain("random_legal").build()], spec, seed=7, hands=40,
                   audit=True)
    if m.forfeit is not None or m.errors[0]:
        problems.append(f"smoke match: errors {m.errors}, forfeit {m.forfeit_reason!r}")
    proc = subprocess.run([sys.executable, "-m", "lab.memory_check", "--hands", "150",
                           "--cwd", str(out), "--variant", str(spec_path), "--protocol", protocol,
                           "--brain", brain], cwd=ROOT, capture_output=True, text=True, timeout=900)
    print("  " + proc.stdout.strip())
    if proc.returncode != 0:
        problems.append(f"memory check failed: {proc.stdout.strip()} {proc.stderr[-300:]}")
    else:
        mb = float(proc.stdout.split("RSS:")[1].split("MB")[0])
        if mb > max_mb:
            problems.append(f"peak memory {mb:.0f} MB > {max_mb} MB")
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build + verify the submission package.")
    ap.add_argument("--variant", default=str(ROOT / "variant" / "active.json"))
    ap.add_argument("--brain", default="tier2", choices=sorted(BRAINS))
    ap.add_argument("--protocol", default="placeholder", choices=sorted(ADAPTERS))
    ap.add_argument("--out", default=str(ROOT / "dist" / "submission"))
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--hands", type=int, default=None, help="timing match length (default: spec)")
    ap.add_argument("--max-startup", type=float, default=1.0)
    ap.add_argument("--max-mb", type=float, default=900.0)
    args = ap.parse_args(argv)
    spec_path = Path(args.variant)
    if not spec_path.is_file():
        from lab.harness import load_variant
        spec = load_variant(args.variant)                    # a catalog name
        spec_path = ROOT / "variant" / "catalog" / f"{spec.name}.json"
    out = Path(args.out)
    info = build(spec_path, args.brain, args.protocol, out)
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"package: {out} ({len(info['modules'])} modules, {size / 1024:.0f} KB, "
          f"data: {'yes' if info['data'] else 'no'})")
    spec = VariantSpec.load(spec_path)
    problems = check_package(out, spec_path, args.protocol, args.brain,
                             args.hands or spec.match.hands, args.max_startup, args.max_mb)
    if args.zip:
        z = out.with_suffix(".zip")
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in sorted(out.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts:
                    zf.write(f, f.relative_to(out))
        print(f"zip: {z} ({z.stat().st_size / 1024:.0f} KB)")
    if problems:
        print("\nPACKAGE CHECKS FAILED:")
        for p in problems:
            print("  -", p)
        return 1
    print("\nall package checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

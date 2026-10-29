"""Build and verify the submission package (`bot.py` + the `bot/` and `variant/` modules it needs).

    .venv/bin/python -m tools.package_submission [--variant variant/active.json]
        [--brain tier2] [--protocol pokerbots] [--out dist/submission] [--zip] [--stage2]

The package contains only what the variant needs: `bot.py` at the top level, the bot/ modules
reachable from bot/main.py (imports scanned with ast) plus the brain, the protocol adapter and
the step plugins the spec uses, variant/spec.py, and a
freshly generated bot/embedded.py (the spec, hyperparameters and tables: the bot reads no files).
The repo itself is never modified: everything is copied into --out (a fresh folder).

With --zip the package is zipped (`bot.py` at the top level, sorted entries and fixed
timestamps, so the same sources give the same hash), the zip must be <= 5 MB, and ALL the checks
run on the UNPACKED zip, i.e. on what the organisers will run:
  1. import scan: stdlib + numpy (+ scipy imported lazily) only, no network modules, no writes
  2. sandbox: no call that reads files or starts processes/threads (static scan of every
     module), and a run of the Protocol section 10 hand under an audit hook (no forbidden event)
  3. startup (launch -> exit on an empty match) under --max-startup (default 1.0 s, serial)
  4. smoke matches over the real protocol: vs the organisers' starter bot and a random bot
  5. timing, as `python bot.py` over the real protocol: for each opponent in --opponents, the
     projected 2x bank use is <= 50 % of the bank and no reply takes over 0.5 s; --stage2 repeats
     it at 1000 hands / 150 s
  6. peak memory below --max-mb (default 500 MB)
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.game.steps import step_module  # noqa: E402
from bot.main import BRAINS  # noqa: E402
from bot.protocols import ADAPTERS  # noqa: E402
from tools import embed_data  # noqa: E402
from tools.sandbox_scan import SHIPPED_ALLOW, sandbox_violations  # noqa: E402
from variant.spec import VariantSpec  # noqa: E402

ALWAYS = ["bot.main", "bot.embedded", "bot.protocols.placeholder", "bot.brains.tier0",
          "variant.spec"]
ZIP_CAP_BYTES = 5 * 1024 * 1024
ZIP_DATE = (2026, 1, 1, 0, 0, 0)                    # fixed, so equal sources give equal zips
FORBIDDEN = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib",
             "telnetlib", "xmlrpc", "socketserver", "asyncio", "webbrowser", "requests",
             "subprocess", "multiprocessing", "sqlite3", "tempfile", "shutil"}
BOT_PY = '''"""Submission entry point: `python3.11 bot.py`. Speaks the %(protocol)s protocol on stdin/stdout.
Everything lives in the `bot/` package next to this file (a package wins over this module for
`import bot`, so the name clash is harmless)."""
import os
import sys

sys.dont_write_bytecode = True   # the filesystem is read-only: don't even try to cache .pyc files
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["--brain", "%(brain)s", "--protocol", "%(protocol)s"]))
'''
EXAMPLE_HAND = ROOT / "tests" / "fixtures" / "protocol" / "example_hand.txt"
SANDBOX_RUN = ROOT / "tests" / "kit" / "sandbox_run.py"


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
    # The embedded data: generated for THIS spec (not the repo's committed copy).
    (out / "bot" / "embedded.py").write_text(embed_data.render(str(spec_path)))
    # The registries name plugins we don't ship, so bot.py names the brain and protocol we do.
    (out / "bot.py").write_text(BOT_PY % {"brain": brain, "protocol": protocol})
    embedded = (out / "bot" / "embedded.py").read_text()
    info = {"variant": spec.name, "brain": brain, "protocol": protocol,
            "modules": sorted(mods), "data": "TABLES = None" not in embedded}
    (out / "PACKAGE.json").write_text(json.dumps(info, indent=2))
    return info


def make_zip(pkg: Path, zip_path: Path) -> str:
    """Zip `pkg` with bot.py first at the top level; deterministic. Returns the sha256."""
    files = sorted((f for f in pkg.rglob("*") if f.is_file() and "__pycache__" not in f.parts
                    and f.name != "PACKAGE.json"),
                   key=lambda f: (f.relative_to(pkg).as_posix() != "bot.py", f.relative_to(pkg).as_posix()))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for f in files:
            zi = zipfile.ZipInfo(f.relative_to(pkg).as_posix(), ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, f.read_bytes())
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- checks

def check_imports(out: Path) -> list[str]:
    problems = []
    allowed = set(sys.stdlib_module_names) | {"numpy", "scipy", "bot", "variant"}
    for f in [*(out / "bot").rglob("*.py"), out / "bot.py"]:
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


def check_sandbox(out: Path, protocol: str) -> list[str]:
    """Static scan of every packaged module, then a real run under the audit hook."""
    problems = []
    for f in [*(out / "bot").rglob("*.py"), *(out / "variant").rglob("*.py"), out / "bot.py"]:
        problems += sandbox_violations(f.relative_to(out), f.read_text(), SHIPPED_ALLOW)
    if protocol == "pokerbots" and EXAMPLE_HAND.is_file():
        lines = [ln[3:] for ln in EXAMPLE_HAND.read_text().splitlines() if ln.startswith("E> ")]
        proc = subprocess.run([sys.executable, str(SANDBOX_RUN), "--protocol", protocol],
                              input="\n".join(lines) + "\n", capture_output=True, text=True,
                              env=dict(os.environ, SANDBOX_ROOT=str(out)), cwd=out, timeout=120)
        problems += [ln for ln in proc.stderr.splitlines() if ln.startswith("SANDBOX-VIOLATION")]
        if len(proc.stdout.splitlines()) != 5:
            problems.append(f"sandbox run answered {len(proc.stdout.splitlines())} of 5 requests: "
                            f"{proc.stderr[-300:]}")
    return problems


def check_package(out: Path, spec_path: Path, protocol: str, brain: str, hands: int,
                  max_startup: float, max_mb: float, opponents: list[str],
                  stage2: bool = False) -> list[str]:
    from lab.engine import play_match
    from lab.eval import opponent_spec
    from lab.players import PlayerSpec, SubprocessPlayer
    from lab.timing_bench import measure_startup, run_timing
    cmd = [sys.executable, "bot.py"]
    problems = check_imports(out) + check_sandbox(out, protocol)
    print(f"  imports + sandbox: {'ok' if not problems else 'FAILED'}")
    spec = VariantSpec.load(spec_path)
    startup = measure_startup(brain, cwd=out, protocol=protocol, cmd=cmd, repeats=5)
    print(f"  startup (best of 5, launch -> exit): {startup * 1000:.0f} ms (limit {max_startup * 1000:.0f})")
    if startup > max_startup:
        problems.append(f"startup {startup:.2f}s > {max_startup}s")
    for name in ("starter", "random_legal"):
        opp = opponent_spec(name, "on") if name == "starter" else PlayerSpec.brain(name)
        bot = SubprocessPlayer(cmd, cwd=str(out), protocol=protocol)
        m = play_match([bot, opp.build()], spec, seed=7, hands=60, audit=True, reply_limit_s=5.0)
        ok = m.forfeit is None and m.errors[0] == 0 and m.hands_played == 60
        print(f"  smoke match vs {name}: {'ok' if ok else 'FAILED'} (errors {m.errors[0]})")
        if not ok:
            problems.append(f"smoke match vs {name}: errors {m.errors}, forfeit {m.forfeit_reason!r}")
    runs = [(hands, spec.match.time_bank_s)] + ([(1000, 150.0)] if stage2 else [])
    for n, bank in runs:
        for opp in opponents:
            rep = run_timing(brain, opp, hands=n, bank_s=bank, cwd=out, protocol=protocol,
                             variant=str(spec_path), cmd=cmd)
            lines = rep.summary().splitlines()
            print(f"  timing, {n} hands / {bank:g}s bank vs {opp}: {lines[1]}\n    {lines[2]}")
            if not rep.ok:
                problems.append(f"timing vs {opp} ({n} hands): projected "
                                f"{rep.projected_used_s:.1f}s vs bank {rep.bank_s}s, worst reply "
                                f"{rep.worst_s * 1000:.0f} ms {rep.forfeit}")
    proc = subprocess.run([sys.executable, "-m", "lab.memory_check", "--hands", str(hands),
                           "--cwd", str(out), "--variant", str(spec_path), "--protocol", protocol,
                           "--brain", brain, "--cmd", f"{sys.executable} bot.py"],
                          cwd=ROOT, capture_output=True, text=True, timeout=1200)
    print("  " + proc.stdout.strip())
    try:
        mb = float(proc.stdout.split("RSS:")[1].split("MB")[0])
        if mb > max_mb:
            problems.append(f"peak memory {mb:.0f} MB > {max_mb} MB")
    except (IndexError, ValueError):
        problems.append(f"memory check failed: {proc.stdout.strip()} {proc.stderr[-300:]}")
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build + verify the submission package.")
    ap.add_argument("--variant", default=str(ROOT / "variant" / "active.json"))
    ap.add_argument("--brain", default="tier2", choices=sorted(BRAINS))
    ap.add_argument("--protocol", default="pokerbots", choices=sorted(ADAPTERS))
    ap.add_argument("--out", default=str(ROOT / "dist" / "submission"))
    ap.add_argument("--zip", action="store_true", help="also build <out>.zip and check THAT, unpacked")
    ap.add_argument("--stage2", action="store_true", help="also time 1000 hands / 150 s")
    ap.add_argument("--hands", type=int, default=None, help="timing match length (default: spec)")
    ap.add_argument("--opponents", default="tier2-nolock,maniac,starter")
    ap.add_argument("--max-startup", type=float, default=1.0)
    ap.add_argument("--max-mb", type=float, default=500.0)
    args = ap.parse_args(argv)
    spec_path = Path(args.variant)
    if not spec_path.is_file():
        from lab.harness import load_variant
        spec = load_variant(args.variant)                    # a catalog name
        spec_path = ROOT / "variant" / "catalog" / f"{spec.name}.json"
    out = Path(args.out)
    info = build(spec_path, args.brain, args.protocol, out)
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file() and "__pycache__" not in f.parts)
    print(f"package: {out} ({len(info['modules'])} modules, {size / 1024:.0f} KB, "
          f"tables: {'yes' if info['data'] else 'no'})")
    spec = VariantSpec.load(spec_path)
    problems: list[str] = []
    check_dir = out
    tmp = None
    if args.zip:
        z = out.with_suffix(".zip")
        digest = make_zip(out, z)
        zsize = z.stat().st_size
        print(f"zip: {z} ({zsize / 1024:.0f} KB, sha256 {digest})")
        if zsize > ZIP_CAP_BYTES:
            problems.append(f"zip is {zsize / 1e6:.2f} MB > the 5 MB limit")
        tmp = tempfile.mkdtemp(prefix="submission_check_")
        with zipfile.ZipFile(z) as zf:
            names = zf.namelist()
            if "bot.py" not in names:
                problems.append("bot.py is not at the top level of the zip")
            zf.extractall(tmp)
        check_dir = Path(tmp)
        print(f"checks run on the unpacked zip: {check_dir}")
    problems += check_package(check_dir, spec_path, args.protocol, args.brain,
                              args.hands or spec.match.hands, args.max_startup, args.max_mb,
                              [o for o in args.opponents.split(",") if o], args.stage2)
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    if problems:
        print("\nPACKAGE CHECKS FAILED:")
        for p in problems:
            print("  -", p)
        return 1
    print("\nall package checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

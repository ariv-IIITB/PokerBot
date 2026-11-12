"""Build the single-file submission dist/bot.py (BUILDMAP §7 Phase 6).

    python tools/build_bot.py [--blob data/strategy/runB_final_avg.blob] [--out dist/bot.py]
                              [--river-allin-rule off|start|updated] [--river-stub FILE]
                              [--sample-seed N] [--preflop-allin-rule off|on] [--small-bet MODE]
                              [--purify-eps X] [--force-mode M] [--slowdown K]
                              [--river-solver off|s1|s2] [--solver-passes N] [--river-solver-file F]
                              [--river-min-ms X] [--solver-box-ms X] [--solver-buckets N]

dist/bot.py contains: the source of every shared/ and botsrc/ module in a dict, a small importlib
meta-path finder that imports them from that dict (no file access at run time), the strategy blob
as a triple-quoted base64 string (76-character lines; base64 decoding ignores newlines), and a
version stamp (git, strategy, run, thresholds sha) and CONFIG (build-time switches). The build
refuses to write more than 4.6 MB.
  --river-allin-rule  off (default) | start | updated | mix: the river all-in rule (BUILDMAP §9.7)
  --preflop-allin-rule off (default) | on: the preflop all-in rule (§9.12); bundles data/preflop_allin.bin
  --small-bet         off (default) | scale | equity | both | gated: answers to bets below our smallest size (§9.4)
  --purify-eps X      purification threshold (default 0.03, §9.5)
  --river-solver M    off (default) | s1 | s2: bundle the teammate's river solver (botsrc/river_solver.py,
                      unchanged) and our glue (botsrc/river_glue.py) behind river_api. s1: it plays every
                      river decision it gets a budget for; s2: the same, except facing an all-in, where the
                      river all-in rule decides. Docs: docs/river_solver.md.
  --solver-out on     with the solver: once the opponent raises a bet or raise of ours on the river, the
                      solver steps aside and the blueprint + river rule play the rest of the hand (F-out)
  --solver-fold on    with the solver: mix in a best response to the opponent's fold rate to our river bets
                      and raises in this leg (the solver's fold_obs, the teammate's RNR weights) (F-fold)
  --solver-passes N   EVAL ONLY: seeded builds solve with exactly N passes (default SOLVER_PASSES_2X, the
                      median the real time box gives under the 2x slow-server emulation)
  --solver-buckets N  EVAL ONLY: with pinned passes, the bucket count the solver plays (48, 64 or 96; default
                      64, what the 2x server's 80 ms box gives)
  --solver-box-ms X   EVAL ONLY: cap the solver's time box at X ms instead of 80 (measures the passes a
                      smaller box gives)
  --river-min-ms X    with the solver: the least time budget the time manager gives it (botsrc/timeman.py
                      RIVER_MIN_MS, 50 ms by default); below it, NOSOLVER plays the river
  --exploit M         the exploit layer (botsrc/exploit.py): off (default) | track (traits only, no move:
                      plays exactly as off) | all | a comma-separated list of moves (overfolder, station,
                      prefold, aggressor, riverbluff)
  --river-solver-file F  EVAL ONLY: bundle F as botsrc.river_solver instead of the teammate's file (tests:
                      tests/fixtures/river_solver_broken.py)
  --force-mode M      EVAL ONLY: play the whole leg in one time-manager mode (NORMAL/NOSOLVER/LEAN/PANIC)
  --slowdown K        EVAL ONLY: make our own work K times slower (emulates a slower server)
  --river-stub FILE   bundle FILE as botsrc.river_stub (e.g. a test stub that sleeps for its budget)
  --sample-seed N     EVAL BUILDS ONLY: each decision draws its random number from (N, deal, seat, street,
                      history index), so both hands of a duplicate pair play a spot the same way and
                      variants of one bot differ only where their decisions differ (BUILDMAP §11).
                      Never use it for an upload: tournament builds keep the process RNG. The build
                      refuses --sample-seed for any file in dist/, and a seeded bot prints a
                      "DHBOT EVAL BUILD" warning to stderr at start-up.
"""
import argparse
import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared import blob as BL  # noqa: E402

MAX_BYTES = 4_600_000
DEFAULT_BLOB = ROOT / "data" / "strategy" / "runB_final_avg.blob"   # the blueprint since 4 Nov (run B average)

# (module name, source file, is package). Order does not matter at run time.
MODULES = [
    ("shared", "shared/__init__.py", True),
    ("shared.abstraction", "shared/abstraction.py", False),
    ("shared.cards", "shared/cards.py", False),
    ("shared.evaluator", "shared/evaluator.py", False),
    ("shared.features", "shared/features.py", False),
    ("shared.showdown", "shared/showdown.py", False),
    ("shared.betting", "shared/betting.py", False),
    ("shared.infoset", "shared/infoset.py", False),
    ("shared.blob", "shared/blob.py", False),
    ("botsrc", "botsrc/__init__.py", True),
    ("botsrc.log", "botsrc/log.py", False),
    ("botsrc.protocol", "botsrc/protocol.py", False),
    ("botsrc.translate", "botsrc/translate.py", False),
    ("botsrc.hooks", "botsrc/hooks.py", False),
    ("botsrc.exploit", "botsrc/exploit.py", False),
    ("botsrc.timeman", "botsrc/timeman.py", False),
    ("botsrc.state", "botsrc/state.py", False),
    ("botsrc.ranges", "botsrc/ranges.py", False),
    ("botsrc.policy", "botsrc/policy.py", False),
    ("botsrc.river_api", "botsrc/river_api.py", False),
    ("botsrc.river_stub", "botsrc/river_stub.py", False),
    ("botsrc.main", "botsrc/main.py", False),
]

TEMPLATE = '''#!/usr/bin/env python3
# Discard Hold'em CFR bot. Generated by tools/build_bot.py -- do not edit; rebuild instead.
# {stamp}
# Python 3.11, standard library + numpy only. Reads stdin, writes protocol JSON to stdout, logs to stderr.
import importlib.abc
import importlib.util
import sys

VERSION = {version!r}
CONFIG = {config!r}

if CONFIG.get("river_solver", "off") != "off":
    # The river solver multiplies mid-size matrices. One BLAS thread runs it 2-4x faster than numpy's
    # default thread pool on a busy machine, and its passes stay on time (docs/river_solver.md). This
    # must happen before numpy loads; builds without the solver leave the environment alone.
    import os
    for _k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        os.environ[_k] = "1"

_SOURCES = {{
{sources}
}}


class _BundleFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Imports shared.* and botsrc.* from _SOURCES (never from the file system)."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname in _SOURCES:
            return importlib.util.spec_from_loader(fullname, self, is_package=_SOURCES[fullname][0])
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        source = _SOURCES[module.__name__][1]
        exec(compile(source, "<bot.py:" + module.__name__ + ">", "exec"), module.__dict__)


sys.meta_path.insert(0, _BundleFinder())

_BLOB = """
{blob}"""


def _fallback_loop(error):
    """Standard library only: used if the runtime cannot even be imported (e.g. numpy missing or
    broken). Plays the BUILDMAP §9.2 fallback, so a broken environment loses chips, not by forfeit."""
    import json
    try:
        import numpy  # noqa: F401
        why = "the bot runtime failed to import (%s: %s)" % (type(error).__name__, error)
    except Exception as numpy_error:
        why = "numpy is NOT available (%s: %s)" % (type(numpy_error).__name__, numpy_error)
    banner = "!" * 78
    sys.stderr.write("%s\\nDHBOT DEGRADED: %s\\nPlaying fallback actions only: this match does NOT use the strategy.\\n%s\\n"
                     % (banner, why, banner))
    sys.stderr.flush()
    ranks, suits = "23456789TJQKA", "shdc"
    for raw in sys.stdin:
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        if not isinstance(msg, dict):
            continue
        t, reply = msg.get("type"), None
        try:
            if t == "action_request":
                legal = msg.get("legal_actions") or []
                to_call, pot = float(msg.get("to_call") or 0), float(msg.get("pot") or 0)
                if "check" in legal:
                    act = "check"
                elif "call" in legal and to_call <= pot / 4:
                    act = "call"
                else:
                    act = "fold" if "fold" in legal else "call"
                reply = {{"type": "action", "action": act}}
            elif t == "discard_request":
                hole = [c for c in (msg.get("hole_cards") or []) if isinstance(c, str) and len(c) == 2
                        and c[0] in ranks and c[1] in suits]
                card = min(hole, key=lambda c: (ranks.index(c[0]), suits.index(c[1]))) if hole else ""
                reply = {{"type": "discard", "card": card}}
        except Exception:
            reply = {{"type": "action", "action": "fold"}} if t == "action_request" else None
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\\n")
            sys.stdout.flush()
        if t == "match_end":
            break


if __name__ == "__main__":
    try:
        from botsrc.main import run
    except Exception as _e:
        _fallback_loop(_e)
    else:
        run(_BLOB, VERSION, CONFIG)
'''


def git_describe():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "describe", "--always", "--dirty"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


RULES = ("off", "start", "updated", "mix")
SOLVERS = ("off", "s1", "s2")
SOLVER_MODULES = [("botsrc.river_solver", "botsrc/river_solver.py", False),     # the teammate's, unchanged
                  ("botsrc.river_glue", "botsrc/river_glue.py", False)]
SOLVER_PASSES_2X = 715      # seeded twins: the median the real 80 ms box gave under the 2x emulation (S1 release
                            # build, one match against each zoo bot, 5 Nov: bin 710-719 of 2,380 solves, 64 buckets)
SMALL_BET = ("off", "scale", "equity", "both", "gated")
EXPLOIT_MOVES = ("overfolder", "station", "prefold", "aggressor", "riverbluff", "rivervalue", "rivernarrow", "overbetdef", "foldbet", "lkprior")   # botsrc/exploit.py MOVES
PREFLOP_TABLE = ROOT / "data" / "preflop_allin.bin"
PREFLOP_META = ROOT / "data" / "preflop_allin.json"


def preflop_table_source():
    """botsrc.preflop_table, generated from data/preflop_allin.{bin,json} (tools/build_preflop_allin.py):
    the table rides inside the bundle, so the bot never reads a file at run time."""
    import base64
    import json
    import zlib
    meta = json.loads(PREFLOP_META.read_text())
    raw = PREFLOP_TABLE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != meta["bin_sha256"]:
        raise SystemExit("data/preflop_allin.bin does not match its .json (rebuild with tools/build_preflop_allin.py)")
    data = base64.b64encode(zlib.compress(raw, 9)).decode()
    return ('"""Generated by tools/build_bot.py from data/preflop_allin.bin -- do not edit."""\n'
            f"F_GRID = {tuple(meta['f_grid'])!r}\nSHAPE = {tuple(meta['bin_shape'])!r}\n"
            f"SHA256 = {meta['bin_sha256']!r}\nDATA = {data!r}\n")


DIST = ROOT / "dist"


def refuse_seeded_dist(out_path, sample_seed, force_mode=None, slowdown=None, solver_passes=None,
                       river_solver_file=None, solver_box_ms=None, solver_buckets=None):
    """Eval-only builds (--sample-seed, --force-mode, --slowdown, --solver-passes, --river-solver-file,
    --solver-box-ms, --solver-buckets) must never be uploaded: refuse to write one anywhere in dist/
    (the upload folder)."""
    used = [k for k, v in (("--sample-seed", sample_seed), ("--force-mode", force_mode),
                           ("--slowdown", slowdown), ("--solver-passes", solver_passes),
                           ("--river-solver-file", river_solver_file), ("--solver-box-ms", solver_box_ms),
                           ("--solver-buckets", solver_buckets)) if v is not None]
    if not used:
        return
    out = pathlib.Path(out_path).resolve()
    if out.parent == DIST.resolve() or DIST.resolve() in out.parents:
        raise SystemExit(f"refusing to write a seeded or other eval-only ({', '.join(used)}) build to {out}: "
                         f"eval builds are for evaluation only; build into eval/bots/ instead")


FORCE_MODES = ("NORMAL", "NOSOLVER", "LEAN", "PANIC")


def build(blob_path, out_path, river_allin_rule="off", river_stub=None, sample_seed=None, preflop_allin_rule="off",
          small_bet="off", purify_eps=None, force_mode=None, slowdown=None, river_solver="off", solver_passes=None,
          river_solver_file=None, solver_out="off", solver_fold="off", river_min_ms=None, solver_box_ms=None,
          solver_buckets=None, exploit="off"):
    refuse_seeded_dist(out_path, sample_seed, force_mode, slowdown, solver_passes, river_solver_file,
                       solver_box_ms, solver_buckets)
    for flag, v in (("--river-min-ms", river_min_ms), ("--solver-box-ms", solver_box_ms),
                    ("--solver-buckets", solver_buckets)):
        if v is not None and river_solver == "off":
            raise SystemExit(f"{flag} needs --river-solver s1|s2")
    if river_min_ms is not None and not 10.0 <= float(river_min_ms) <= 50.0:
        raise SystemExit("--river-min-ms must be in [10, 50]")
    if solver_box_ms is not None and not 10.0 <= float(solver_box_ms) <= 80.0:
        raise SystemExit("--solver-box-ms must be in [10, 80]")
    if solver_buckets is not None and (int(solver_buckets) not in (48, 64, 96) or
                                       (solver_passes is None and sample_seed is None)):
        raise SystemExit("--solver-buckets must be 48, 64 or 96, with pinned passes (--solver-passes or a seeded build)")
    for flag, v in (("--solver-out", solver_out), ("--solver-fold", solver_fold)):
        if v not in ("off", "on"):
            raise SystemExit(f"{flag} must be off or on")
        if v == "on" and river_solver == "off":
            raise SystemExit(f"{flag} needs --river-solver s1|s2")
    if river_solver_file is not None and river_solver == "off":
        raise SystemExit("--river-solver-file needs --river-solver s1|s2")
    if river_solver not in SOLVERS:
        raise SystemExit(f"--river-solver must be one of {SOLVERS}")
    if solver_passes is not None and (river_solver == "off" or int(solver_passes) < 20):
        raise SystemExit("--solver-passes needs --river-solver s1|s2 and at least 20 passes")
    if force_mode is not None and force_mode not in FORCE_MODES:
        raise SystemExit(f"--force-mode must be one of {FORCE_MODES}")
    if slowdown is not None and not 1.0 <= float(slowdown) <= 20.0:
        raise SystemExit("--slowdown must be in [1, 20]")
    if river_allin_rule not in RULES:
        raise SystemExit(f"--river-allin-rule must be one of {RULES}")
    exploit = str(exploit or "off")
    names = [m.strip() for m in exploit.split(",")]
    if exploit != "off" and not all(m in EXPLOIT_MOVES + ("track", "all") for m in names):
        raise SystemExit(f"--exploit must be off, track, all or moves from {EXPLOIT_MOVES}")
    if preflop_allin_rule not in ("off", "on"):
        raise SystemExit("--preflop-allin-rule must be off or on")
    if small_bet not in SMALL_BET:
        raise SystemExit(f"--small-bet must be one of {SMALL_BET}")
    if purify_eps is not None and not 0.0 <= float(purify_eps) < 0.5:
        raise SystemExit("--purify-eps must be in [0, 0.5)")
    blob_path, out_path = pathlib.Path(blob_path), pathlib.Path(out_path)
    blob = blob_path.read_bytes().strip()
    header, _ = BL.decode_blob(blob)                      # validates the blob before embedding it
    meta = header["meta"]
    version = {"git": git_describe(), "strategy": blob_path.stem, "abstraction": meta.get("abstraction", "a1"),
               "mode": meta["mode"],
               "run": meta["source"]["run"], "t": meta["source"]["t"],
               "thresholds_sha": meta["thresholds_sha"], "blob_sha256": hashlib.sha256(blob).hexdigest()}
    config = {"river_allin_rule": river_allin_rule}
    if river_stub:
        config["river_stub"] = pathlib.Path(river_stub).name
    if sample_seed is not None:
        config["sample_seed"] = int(sample_seed)
    if preflop_allin_rule != "off":
        config["preflop_allin_rule"] = preflop_allin_rule
    if small_bet != "off":
        config["small_bet"] = small_bet
    if purify_eps is not None:
        config["purify_eps"] = float(purify_eps)
    if force_mode is not None:
        config["force_mode"] = force_mode
    if slowdown is not None:
        config["slowdown"] = float(slowdown)
    if river_solver != "off":
        config["river_solver"] = river_solver
        if sample_seed is not None or solver_passes is not None:
            config["solver_passes"] = int(solver_passes if solver_passes is not None else SOLVER_PASSES_2X)
        if river_solver_file is not None:
            config["river_solver_file"] = pathlib.Path(river_solver_file).name
        if solver_out == "on":
            config["solver_out"] = "on"
        if solver_fold == "on":
            config["solver_fold"] = "on"
        if river_min_ms is not None:
            config["river_min_ms"] = float(river_min_ms)
        if solver_box_ms is not None:
            config["solver_box_ms"] = float(solver_box_ms)
        if solver_buckets is not None:
            config["solver_buckets"] = int(solver_buckets)
    if exploit != "off":
        config["exploit"] = exploit
    version["config"] = config
    sources = []
    for name, rel, is_pkg in MODULES + (SOLVER_MODULES if river_solver != "off" else []):
        path = pathlib.Path(river_stub) if (name == "botsrc.river_stub" and river_stub) else ROOT / rel
        if name == "botsrc.river_solver" and river_solver_file:
            path = pathlib.Path(river_solver_file)
        src = path.read_text()
        compile(src, rel, "exec")                          # syntax check before bundling
        sources.append(f"    {name!r}: ({is_pkg!r}, {src!r}),")
    if preflop_allin_rule == "on":
        src = preflop_table_source()
        compile(src, "botsrc/preflop_table.py", "exec")
        sources.append(f"    {'botsrc.preflop_table'!r}: (False, {src!r}),")
    text = blob.decode()
    lines = "\n".join(text[i:i + 76] for i in range(0, len(text), 76)) + "\n"
    stamp = (f"git {version['git']}; strategy {version['strategy']} ({version['mode']}, run {version['run']} "
             f"t={version['t']}); thresholds {version['thresholds_sha'][:16]}")
    out = TEMPLATE.format(stamp=stamp, version=version, config=config, sources="\n".join(sources), blob=lines)
    data = out.encode()
    if len(data) > MAX_BYTES:
        raise SystemExit(f"dist/bot.py would be {len(data):,} bytes, over the {MAX_BYTES:,} limit")
    compile(out, str(out_path), "exec")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    return len(data), version


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blob", default=str(DEFAULT_BLOB))
    ap.add_argument("--out", default=str(ROOT / "dist" / "bot.py"))
    ap.add_argument("--river-allin-rule", default="off", choices=RULES)
    ap.add_argument("--river-stub", default=None)
    ap.add_argument("--sample-seed", type=int, default=None, help="eval builds only (see the module docstring)")
    ap.add_argument("--preflop-allin-rule", default="off", choices=("off", "on"))
    ap.add_argument("--small-bet", default="off", choices=SMALL_BET)
    ap.add_argument("--purify-eps", type=float, default=None, help="purification threshold (default 0.03, §9.5)")
    ap.add_argument("--force-mode", default=None, choices=FORCE_MODES, help="eval builds only: pin one mode")
    ap.add_argument("--slowdown", type=float, default=None, help="eval builds only: our own work K times slower")
    ap.add_argument("--river-solver", default="off", choices=SOLVERS)
    ap.add_argument("--solver-passes", type=int, default=None, help="eval builds only: pinned solver passes")
    ap.add_argument("--river-solver-file", default=None, help="eval builds only: bundle this file as the solver")
    ap.add_argument("--solver-out", default="off", choices=("off", "on"))
    ap.add_argument("--solver-fold", default="off", choices=("off", "on"))
    ap.add_argument("--river-min-ms", type=float, default=None, help="with the solver: its least time budget")
    ap.add_argument("--solver-box-ms", type=float, default=None, help="eval builds only: cap the solver's box")
    ap.add_argument("--solver-buckets", type=int, default=None, help="eval builds only: pinned bucket count")
    ap.add_argument("--exploit", default="off", help="the exploit layer: off | track | all | moves (see above)")
    args = ap.parse_args()
    size, version = build(args.blob, args.out, args.river_allin_rule, args.river_stub, args.sample_seed,
                          args.preflop_allin_rule, args.small_bet, args.purify_eps, args.force_mode, args.slowdown,
                          args.river_solver, args.solver_passes, args.river_solver_file, args.solver_out,
                          args.solver_fold, args.river_min_ms, args.solver_box_ms, args.solver_buckets,
                          args.exploit)
    print(f"wrote {args.out}: {size:,} bytes (limit {MAX_BYTES:,}); {version}")


if __name__ == "__main__":
    main()

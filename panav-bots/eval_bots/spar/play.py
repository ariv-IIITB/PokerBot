"""Play any two bots against each other on the official engine, N matches, and print every match and a total.

    python eval/bots/spar/play.py BOT_A BOT_B [--matches 10] [--stage 1] [--workers 2] [--seed-base 1]

BOT is a sparring bot name (eqtag trapper potctl polar betfold light3b donk adapt tilt discardread), the word
`final` (dist/bot.py), or a path to any bot file that speaks the protocol (python bot.py, stdin/stdout JSON).
A match is two legs (Stage 1: 200 hands each, Stage 2: 500), the same deals in both legs with the seats swapped.
Results use the engine's own summary: chips for A, who won the match (more net chips), chips per hand with a 95%
interval over the matches. At most 4 matches run at a time (this laptop gets slow beyond that).

Example:  python eval/bots/spar/play.py trapper polar --matches 20 --workers 4
"""
import argparse
import concurrent.futures as cf
import math
import pathlib
import re
import statistics
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENGINE = ROOT / "starter_kit" / "engine.py"
PY = ROOT / ".venv311" / "bin" / "python"
if not PY.exists():
    PY = pathlib.Path(sys.executable)


def resolve(spec):
    if spec == "final":
        return ROOT / "dist" / "bot.py"
    p = HERE / spec / "bot.py"
    if p.exists():
        return p
    q = pathlib.Path(spec).expanduser()
    if q.is_file():
        return q.resolve()
    raise SystemExit(f"unknown bot {spec!r}: not a sparring bot name, 'final', or a file")


def match(a, b, stage, seed):
    with tempfile.TemporaryDirectory() as d:
        r = subprocess.run([str(PY), str(ENGINE), str(a), str(b), "--stage", str(stage), "--seed", str(seed),
                            "--log-dir", d, "--python", str(PY)], capture_output=True, text=True, timeout=3600)
    out = r.stdout + r.stderr
    nets = re.findall(r"^\s+[AB]\s+.*?\s+net\s+([+-]?\d+)", out, re.M)
    hands = re.search(r"(\d+) of (\d+) hands played", out)
    forfeit = re.search(r"([AB]) forfeited", out)
    if len(nets) < 2 or not hands:
        raise RuntimeError("could not read the engine's summary:\n" + out[-600:])
    return {"seed": seed, "a": int(nets[0]), "hands": int(hands.group(1)), "forfeit": forfeit.group(1) if forfeit else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--matches", type=int, default=10)
    ap.add_argument("--stage", type=int, default=1, choices=(1, 2))
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--seed-base", type=int, default=1)
    args = ap.parse_args()
    a, b = resolve(args.a), resolve(args.b)
    workers = max(1, min(4, args.workers))
    print(f"{args.a} (A) vs {args.b} (B): {args.matches} Stage {args.stage} matches, {workers} at a time", flush=True)
    rows = []
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = [ex.submit(match, a, b, args.stage, args.seed_base + i) for i in range(args.matches)]
        for f in futs:
            r = f.result()
            rows.append(r)
            w = args.a if r["a"] > 0 else args.b if r["a"] < 0 else "draw"
            print(f"  seed {r['seed']:>4}: {w:12s} {args.a} {r['a']:+6d} chips" + (f"  FORFEIT {r['forfeit']}" if r["forfeit"] else ""),
                  flush=True)
    per_hand = [r["a"] / max(1, r["hands"]) for r in rows]
    mean = statistics.mean(per_hand)
    half = 1.96 * statistics.stdev(per_hand) / math.sqrt(len(per_hand)) if len(per_hand) > 1 else float("nan")
    wins = sum(r["a"] > 0 for r in rows)
    losses = sum(r["a"] < 0 for r in rows)
    print(f"{args.a}: {wins} wins, {len(rows) - wins - losses} draws, {losses} losses; "
          f"{mean:+.3f} chips/hand (95% CI {mean - half:+.3f} .. {mean + half:+.3f}); total {sum(r['a'] for r in rows):+d}")


if __name__ == "__main__":
    main()

"""League search: random sampling + cross-entropy refinement of param-bot settings vs final.

  PYTHONPATH=. .venv/bin/python panav-bots/loop/league/search.py --out panav-bots/loop/results/league_search \
        [--rounds 4] [--pop 24] [--n0 28] [--pairs 8] [--hands 200] [--processes 3]

Fitness = chips/hand of the param bot vs final (A = param bot; paired duplicate deals via file_duel.pair).
Seeds: 1000-1999 only. Round r uses its own block of `pairs` seeds (fresh deals per round, so CE does not chase one
set of deals); the blocks are written to the ledger. Results are appended to <out>/evals.jsonl (resumable).
"""
from __future__ import annotations
import argparse, json, math, multiprocessing as mp, random, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "tools"))
from make_bot import build          # noqa: E402
from param_bot import SPACE         # noqa: E402
from file_duel import pair          # noqa: E402

FINAL = str(HERE.parents[1] / "final" / "bot.py")
KEYS = list(SPACE)


def decode(u):
    return {k: SPACE[k][0] + min(1.0, max(0.0, x)) * (SPACE[k][1] - SPACE[k][0]) for k, x in zip(KEYS, u)}


def encode(p):
    out = []
    for k in KEYS:
        lo, hi, d = SPACE[k]
        out.append((float(p.get(k, d)) - lo) / (hi - lo))
    return out


FINAL_USED = FINAL


def run_round(pool, out: Path, tag: str, cfgs: list, seeds: list, hands: int):
    """Evaluate every cfg on every seed. Returns list of dict(tag, id, params, mean, se, ...)."""
    bots = out / "bots"
    bots.mkdir(exist_ok=True)
    tasks, meta = [], []
    for i, p in enumerate(cfgs):
        f = bots / f"{tag}_{i:02d}.py"
        f.write_text(build(p))
        for s in seeds:
            tasks.append((str(f), FINAL_USED, s, hands, None, None))
            meta.append(i)
    t0 = time.time()
    res = pool.map(pair, tasks, chunksize=1)
    per = {i: [] for i in range(len(cfgs))}
    ff = {i: 0 for i in range(len(cfgs))}
    for i, r in zip(meta, res):
        per[i].append(r["chips"] / max(1, r["hands"]))
        ff[i] += r["ff_a"]
    rows = []
    for i, p in enumerate(cfgs):
        x = per[i]
        n = len(x)
        m = sum(x) / n
        se = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1) / n) if n > 1 else float("nan")
        row = dict(tag=tag, id=f"{tag}_{i:02d}", params=p, mean=m, se=se, n=n, seeds=seeds, ff_a=ff[i])
        rows.append(row)
        with open(out / "evals.jsonl", "a") as fh:
            fh.write(json.dumps(row) + "\n")
    print(f"[{tag}] {len(cfgs)} cfgs x {len(seeds)} pairs in {time.time()-t0:.0f}s; "
          f"best {max(r['mean'] for r in rows):+.2f} median {sorted(r['mean'] for r in rows)[len(rows)//2]:+.2f}",
          flush=True)
    return rows


def ce_sample(rng, mu, sd, n):
    pop = []
    for _ in range(n):
        pop.append([min(1.0, max(0.0, rng.gauss(m, s))) for m, s in zip(mu, sd)])
    return pop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--rounds", type=int, default=4)
    ap.add_argument("--pop", type=int, default=24)
    ap.add_argument("--n0", type=int, default=28)
    ap.add_argument("--pairs", type=int, default=8)
    ap.add_argument("--hands", type=int, default=200)
    ap.add_argument("--processes", type=int, default=3)
    ap.add_argument("--first-seed", type=int, default=1000)
    ap.add_argument("--elite", type=float, default=0.25)
    ap.add_argument("--final", default=FINAL)
    ap.add_argument("--rng", type=int, default=7)
    a = ap.parse_args()
    global FINAL_USED
    FINAL_USED = a.final
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.rng)
    corners = json.loads((HERE / "configs" / "corners.json").read_text())
    seed_next = a.first_seed
    pool = mp.get_context("spawn").Pool(a.processes)
    allrows = []

    def seeds():
        nonlocal seed_next
        s = list(range(seed_next, seed_next + a.pairs))
        seed_next += a.pairs
        assert seed_next <= 2000
        return s

    # round 0: corner styles + uniform random
    cfgs = [dict(v) for v in corners.values()]
    cfgs += [decode([rng.random() for _ in KEYS]) for _ in range(a.n0 - len(cfgs))]
    rows = run_round(pool, out, "r0", cfgs, seeds(), a.hands)
    allrows += rows
    for r in range(1, a.rounds + 1):
        k = max(3, int(len(rows) * a.elite))
        elite = sorted(rows, key=lambda x: -x["mean"])[:k]
        vecs = [encode(e["params"]) for e in elite]
        mu = [sum(v[j] for v in vecs) / k for j in range(len(KEYS))]
        sd = [max(0.12, math.sqrt(sum((v[j] - mu[j]) ** 2 for v in vecs) / k)) for j in range(len(KEYS))]
        if r == 1:                                  # r0 is noisy and wide: do not collapse yet
            sd = [max(s, 0.25) for s in sd]
        cfgs = [decode(u) for u in ce_sample(rng, mu, sd, a.pop - 2)]
        cfgs += [e["params"] for e in elite[:2]]    # re-test the two best on fresh deals (shrinkage)
        rows = run_round(pool, out, f"r{r}", cfgs, seeds(), a.hands)
        allrows += rows
        top = sorted(rows, key=lambda x: -x["mean"])[:3]
        print("  top:", [(t["id"], round(t["mean"], 2)) for t in top], flush=True)
    (out / "ledger.txt").write_text(f"seeds used {a.first_seed}..{seed_next - 1}\n")
    print("done; seeds", a.first_seed, seed_next - 1)


if __name__ == "__main__":
    main()

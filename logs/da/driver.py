"""DA coordinate descent (resumable). Run from the repo root: .venv/bin/python logs/da/driver.py cd|grid
Each point = one lab.eval (30 pairs, seeds 53000-53029, locks off, Discard Hold'em, train+tier1+tier2),
wrapped in the laptop turnstile; a point whose .txt exists is never re-run. Moves need diff > 1 SE
(sum over bots, SE = hypot of the per-bot SEs, as lab.eval --compare)."""
import json, math, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from lab.eval import parse_summary

OUT = Path("logs/da"); SEED, PAIRS = 53000, 30
START = ([0.70, 0.68, 0.70, 0.74], 0.02)
RE_STEP, CM_STEP = 0.02, 0.01

def key(re_, cm): return "re" + "-".join(f"{round(x*100):d}" for x in re_) + f"_cm{round(cm*100):d}"

def run(re_, cm, smart=True, seed=SEED, pairs=PAIRS, locks="off", prefix="cd"):
    name = "plain" if not smart else key(re_, cm)
    f = OUT / f"{prefix}_{name}.txt"
    tmp = f.with_suffix(".tmp")
    while subprocess.run(["pgrep", "-f", "[-]-out " + str(tmp)], capture_output=True).returncode == 0:
        time.sleep(20)                       # an orphaned eval of this point from a previous driver
    if not f.exists() and tmp.exists() and len(tmp.read_text().splitlines()) >= 8:
        tmp.rename(f)
    if not f.exists():
        cfg = {"smart_rollout_discard": True, "raise_equity": re_, "call_margin": cm} if smart else None
        brain = "tier3:" + json.dumps(cfg, separators=(",", ":")) if cfg else "tier3"
        cmd = ["flock", "/tmp/pokerbot_turnstile.lock", "true"]
        subprocess.run(cmd)
        cmd = ["flock", "-s", "/tmp/pokerbot_laptop.lock", "nice", "-n", "15", ".venv/bin/python", "-m", "lab.eval", brain,
               "--pool", "train", "tier1", "tier2", "--pairs", str(pairs), "--first-seed", str(seed),
               "--locks", locks, "--variant", "discard_holdem", "--processes", (OUT / "processes").read_text().strip(), "--out", str(f.with_suffix(".tmp"))]
        with open(f.with_suffix(".log"), "w") as lg:
            r = subprocess.run(cmd, stdout=lg, stderr=subprocess.STDOUT)
        if r.returncode: sys.exit(f"eval failed for {name}")
        f.with_suffix(".tmp").rename(f)
    return parse_summary(f)

def diff(a, b):  # b - a, sum over bots, SE
    sh = [o for o in a if o in b]
    return sum(b[o][0] - a[o][0] for o in sh), math.sqrt(sum(a[o][1] ** 2 + b[o][1] ** 2 for o in sh))

def log(msg):
    print(msg, flush=True)
    with open(OUT / "moves.log", "a") as f: f.write(msg + "\n")

def descent():
    re_, cm = list(START[0]), START[1]
    plain = run(None, None, smart=False)
    best = run(re_, cm)
    d, se = diff(plain, best); log(f"start smart-on (Tier 3 values) vs plain tier3 same seeds: {d:+.2f} ± {se:.2f}")
    rnd = 0
    while rnd < 3:
        rnd += 1; cands = []
        for i in range(len(re_)):
            for s in (-RE_STEP, RE_STEP):
                r2 = list(re_); r2[i] = round(r2[i] + s, 2); cands.append((r2, cm))
        for s in (-CM_STEP, CM_STEP): cands.append((list(re_), round(cm + s, 2)))
        res = []
        for r2, c2 in cands:
            d, se = diff(best, run(r2, c2)); res.append((d, se, r2, c2))
            log(f"round {rnd} {key(r2, c2)} vs {key(re_, cm)}: {d:+.2f} ± {se:.2f} (z {d/se:+.1f})")
        d, se, r2, c2 = max(res)
        if d > se:
            log(f"round {rnd} MOVE to {key(r2, c2)} ({d:+.2f} ± {se:.2f})")
            best = run(r2, c2); re_, cm = r2, c2
        else:
            log(f"round {rnd} STOP: best change {key(r2, c2)} {d:+.2f} ± {se:.2f} not > 1 SE"); break
    log(f"FINAL descent point {key(re_, cm)}")
    (OUT / "best.json").write_text(json.dumps({"raise_equity": re_, "call_margin": cm}))

def sens(best_re, best_cm):
    """|diff| of the +-step neighbours of the final best, per parameter (from the files of the last round)."""
    base = run(best_re, best_cm); out = {}
    for i in range(len(best_re)):
        ds = []
        for st in (-RE_STEP, RE_STEP):
            r2 = list(best_re); r2[i] = round(r2[i] + st, 2)
            if (OUT / f"cd_{key(r2, best_cm)}.txt").exists(): ds.append(abs(diff(base, run(r2, best_cm))[0]))
        out[("re", i)] = max(ds) if ds else 0.0
    ds = [abs(diff(base, run(best_re, round(best_cm + st, 2)))[0]) for st in (-CM_STEP, CM_STEP)
          if (OUT / f"cd_{key(best_re, round(best_cm + st, 2))}.txt").exists()]
    out[("cm", 0)] = max(ds) if ds else 0.0
    return out

def point(best_re, best_cm, par, k):
    if par[0] == "cm": return list(best_re), round(best_cm + k * CM_STEP, 2)
    r2 = list(best_re); r2[par[1]] = round(r2[par[1]] + k * RE_STEP, 2); return r2, best_cm

def grid():
    b = json.loads((OUT / "best.json").read_text()); re_, cm = b["raise_equity"], b["call_margin"]
    sv = sens(re_, cm); top = sorted(sv, key=sv.get, reverse=True)[:2]
    log(f"grid: sensitivities {sv}; grid on {top} around {key(re_, cm)}")
    best = run(re_, cm); res = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            if i == j == 0: continue
            r2, c2 = point(re_, cm, top[0], i)
            r3 = list(r2); c3 = c2
            if top[1][0] == "cm": c3 = round(cm + j * CM_STEP, 2)
            else: r3[top[1][1]] = round(r3[top[1][1]] + j * RE_STEP, 2) if top[1] != top[0] else r3[top[1][1]]
            d, se = diff(best, run(r3, c3)); res.append((d, se, r3, c3))
            log(f"grid {key(r3, c3)} vs {key(re_, cm)}: {d:+.2f} ± {se:.2f} (z {d/se:+.1f})")
    d, se, r3, c3 = max(res)
    if d > se: log(f"grid MOVE to {key(r3, c3)} ({d:+.2f} ± {se:.2f})"); re_, cm = r3, c3
    else: log(f"grid STAY at {key(re_, cm)} (best {key(r3, c3)} {d:+.2f} ± {se:.2f})")
    (OUT / "final.json").write_text(json.dumps({"raise_equity": re_, "call_margin": cm}))

def confirm():
    f = json.loads((OUT / "final.json").read_text())
    for locks in ("off", "on"):
        for smart in (False, True):
            run(f["raise_equity"], f["call_margin"], smart=smart, seed=54000, pairs=50, locks=locks, prefix=f"conf{locks}")
    log("confirm runs done")

if __name__ == "__main__":
    {"cd": descent, "grid": grid, "confirm": confirm}[sys.argv[1]]()

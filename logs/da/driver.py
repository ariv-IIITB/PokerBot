"""DA coordinate descent (resumable). Run from the repo root: .venv/bin/python logs/da/driver.py cd|grid
Each point = one lab.eval (30 pairs, seeds 53000-53029, locks off, Discard Hold'em, train+tier1+tier2),
wrapped in the laptop turnstile; a point whose .txt exists is never re-run. Moves need diff > 1 SE
(sum over bots, SE = hypot of the per-bot SEs, as lab.eval --compare)."""
import json, math, subprocess, sys
from pathlib import Path
sys.path.insert(0, ".")
from lab.eval import parse_summary

OUT = Path("logs/da"); SEED, PAIRS = 53000, 30
START = ([0.70, 0.68, 0.70, 0.74], 0.02)
RE_STEP, CM_STEP = 0.02, 0.01

def key(re_, cm): return "re" + "-".join(f"{round(x*100):d}" for x in re_) + f"_cm{round(cm*100):d}"

def run(re_, cm, smart=True):
    name = "plain" if not smart else key(re_, cm)
    f = OUT / f"cd_{name}.txt"
    if not f.exists():
        cfg = {"smart_rollout_discard": True, "raise_equity": re_, "call_margin": cm} if smart else None
        brain = "tier3:" + json.dumps(cfg, separators=(",", ":")) if cfg else "tier3"
        cmd = ["flock", "/tmp/pokerbot_turnstile.lock", "true"]
        subprocess.run(cmd)
        cmd = ["flock", "-s", "/tmp/pokerbot_laptop.lock", "nice", "-n", "15", ".venv/bin/python", "-m", "lab.eval", brain,
               "--pool", "train", "tier1", "tier2", "--pairs", str(PAIRS), "--first-seed", str(SEED),
               "--locks", "off", "--variant", "discard_holdem", "--processes", "3", "--out", str(f.with_suffix(".tmp"))]
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

if __name__ == "__main__":
    descent()

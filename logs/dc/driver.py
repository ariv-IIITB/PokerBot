"""DC resumable driver. Run from the repo root: .venv/bin/python logs/dc/driver.py cd|budget|confirm
Each point = one lab.eval (30 pairs, seeds 21000-21029, locks off, Discard Hold'em, train+tier1+tier2) under the laptop
turnstile; a point whose .txt exists is never re-run. A move needs diff > 1 SE (sum over bots, SE = hypot of per-bot SEs).
Points are brain configs on top of tier3.json (DA's values, smart rollouts on)."""
import json, math, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, ".")
from lab.eval import parse_summary

OUT = Path("logs/dc"); SEED, PAIRS = 21000, 30
START = {"discard_mix": 0.15, "discard_eps": 0.25}
STEPS = {"discard_mix": 0.1, "discard_eps": 0.15}
BASE = {"discard_mix": 0.0}

def key(cfg): return "_".join(f"{k}{v:g}" for k, v in sorted(cfg.items())) or "base"

def run(cfg, seed=SEED, pairs=PAIRS, locks="off", prefix="cd", pool=("train", "tier1", "tier2")):
    f = OUT / f"{prefix}_{key(cfg)}.txt"
    tmp = f.with_suffix(".tmp")
    while subprocess.run(["pgrep", "-f", "[-]-out " + str(tmp)], capture_output=True).returncode == 0:
        time.sleep(20)
    if not f.exists() and tmp.exists() and len(tmp.read_text().splitlines()) >= 8:
        tmp.rename(f)
    if not f.exists():
        brain = "tier3:" + json.dumps(cfg, separators=(",", ":")) if cfg else "tier3"
        subprocess.run(["flock", "/tmp/pokerbot_turnstile.lock", "true"])
        cmd = ["flock", "-s", "/tmp/pokerbot_laptop.lock", "nice", "-n", "15", ".venv/bin/python", "-m", "lab.eval", brain,
               "--pool", *pool, "--pairs", str(pairs), "--first-seed", str(seed),
               "--locks", locks, "--variant", "discard_holdem", "--processes", (OUT / "processes").read_text().strip(),
               "--out", str(tmp)]
        with open(f.with_suffix(".log"), "w") as lg:
            r = subprocess.run(cmd, stdout=lg, stderr=subprocess.STDOUT)
        if r.returncode: sys.exit(f"eval failed for {key(cfg)}")
        tmp.rename(f)
    return parse_summary(f)

def diff(a, b):
    sh = [o for o in a if o in b]
    return sum(b[o][0] - a[o][0] for o in sh), math.sqrt(sum(a[o][1] ** 2 + b[o][1] ** 2 for o in sh))

def log(msg):
    print(msg, flush=True)
    with open(OUT / "moves.log", "a") as f: f.write(msg + "\n")

def descent():
    cfg = dict(START)
    base = run(BASE)
    best = run(cfg)
    d, se = diff(base, best); log(f"start {key(cfg)} vs base (smart on, mix off), same seeds: {d:+.2f} ± {se:.2f}")
    for rnd in range(1, 4):
        res = []
        for k, st in STEPS.items():
            for s in (-st, st):
                c2 = dict(cfg); c2[k] = round(max(0.0, c2[k] + s), 2)
                if c2 == cfg or (k == "discard_mix" and c2[k] == 0): continue
                d, se = diff(best, run(c2)); res.append((d, se, c2))
                log(f"round {rnd} {key(c2)} vs {key(cfg)}: {d:+.2f} ± {se:.2f} (z {d/se:+.1f})")
        d, se, c2 = max(res, key=lambda r: r[0])
        if d > se:
            log(f"round {rnd} MOVE to {key(c2)} ({d:+.2f} ± {se:.2f})"); cfg = c2; best = run(cfg)
        else:
            log(f"round {rnd} STOP: best {key(c2)} {d:+.2f} ± {se:.2f} not > 1 SE"); break
    d, se = diff(base, best); log(f"FINAL {key(cfg)} vs base: {d:+.2f} ± {se:.2f}")
    (OUT / "best.json").write_text(json.dumps(cfg))

if __name__ == "__main__":
    {"cd": descent}[sys.argv[1]]()

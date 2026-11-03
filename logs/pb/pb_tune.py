"""PB (laptop) tuning driver: coordinate descent, 3x3 grid, confirmation, restriction. Resumable.

    .venv/bin/python logs/pb/pb_tune.py anti_folder [anti_value anti_aggro]

Every lab.eval run is one file under logs/pb/<member>/runs/; an existing file is never re-run, so the
whole decision flow is replayed from the files after a restart. Rules: docs/tier4/README.md ("Aim",
light testing, user 2026-11-03) and PB_tuning.md.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from lab.eval import LINE, compare as chips_compare  # noqa: E402
from lab.opps.score_compare import SCORE, compare as score_compare  # noqa: E402

VARIANT = "discard_holdem"
PROCS = 6                   # manager, 2026-11-03: GX cancelled, 4 -> 6
DESCENT_PAIRS = 30          # tuning points
MAX_ROUNDS = 3              # light testing (user, 2026-11-03)
CONFIRM_PAIRS = 50
RESTRICT_PAIRS = 30         # restriction vs tier3: one head-to-head, locks off (manager, 2026-11-03)
# name: (family, tuning seed base, confirmation seed base, [(param, PA default, step, (lo, hi))])
PLAN = {
    "anti_folder": (["d_new_exploiter", "d_conv_opp3", "d_new_rules"], 51000, 52000,
                    [("x_bluff_max", 0.60, 0.15, (0.0, 1.0)), ("x_river_bluff_mult", 2.5, 1.0, (0.0, 8.0)),
                     ("x_vo_margin", 0.12, 0.06, (0.0, 0.5))]),
    "anti_value": (["d_new_minraise", "d_new_trapper"], 51300, 52300,
                   [("x_vo_margin", 0.12, 0.06, (0.0, 0.5)), ("av_raise_fold_eq", 0.60, 0.10, (0.0, 1.0))]),
    "anti_aggro": (["d_new_lag", "maniac"], 51600, 52600,
                   [("aa_call_margin", -0.03, 0.03, (-0.2, 0.1)), ("aa_mdf_mult", 1.10, 0.10, (0.8, 1.6)),
                    ("aa_bluff_mult", 0.50, 0.25, (0.0, 2.0))]),
}


def brain(member: str, pt: dict) -> str:
    return "tier4p:" + json.dumps({"member": member, "members": {member: pt}}, sort_keys=True, separators=(",", ":"))


def key(pt: dict) -> str:
    return "_".join(f"{pt[k]:g}" for k in sorted(pt))


def run(member: str, brain_arg: str, tag: str, opp: str, pairs: int, seed: int, locks: str) -> dict:
    """One lab.eval run (cached): returns {chips, se, score, sse, n}."""
    f = ROOT / "logs/pb" / member / "runs" / f"{seed}_{pairs}_{locks}_{tag}_{opp}.txt"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        cmd = ['flock /tmp/pokerbot_turnstile.lock true; flock -s /tmp/pokerbot_laptop.lock "$@"', "_",
               str(ROOT / ".venv/bin/python"), "-m", "lab.eval", brain_arg, "--pool", opp, "--pairs", str(pairs),
               "--first-seed", str(seed), "--locks", locks, "--variant", VARIANT, "--processes", str(PROCS),
               "--out", str(f)]
        with open(f"/tmp/pb_{member}.err", "ab") as err:
            r = subprocess.run(["bash", "-c", *cmd], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=err)
        if r.returncode or not f.exists():
            f.unlink(missing_ok=True)
            raise SystemExit(f"lab.eval failed for {f.name} (rc {r.returncode})")
    line = next(l for l in f.read_text().splitlines() if LINE.match(l))
    m, s = LINE.match(line), SCORE.search(line)
    return {"chips": float(m["m"]), "se": float(m["se"]), "score": float(s["s"]), "sse": float(s["se"]), "n": int(s["n"])}


def run_pool(member, brain_arg, tag, pool, pairs, seed, locks):
    return {o: run(member, brain_arg, tag, o, pairs, seed, locks) for o in pool}


def chips(res: dict) -> dict:
    return {o: (r["chips"], r["se"]) for o, r in res.items()}


def scores(res: dict) -> dict:
    return {o: (r["score"], r["sse"]) for o, r in res.items()}


def delta(before: dict, after: dict) -> tuple[float, float, float]:
    """(sum of per-bot chip differences, its SE, z): the same sum lab.eval --compare prints."""
    d = sum(after[o]["chips"] - before[o]["chips"] for o in before)
    se = math.sqrt(sum(before[o]["se"] ** 2 + after[o]["se"] ** 2 for o in before))
    return d, se, d / se if se else 0.0


class Report:
    def __init__(self, member: str) -> None:
        self.path = ROOT / "logs/pb" / member / "report.md"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lines: list[str] = []

    def add(self, text: str = "") -> None:
        self.lines.append(text)
        print(text, flush=True)
        self.path.write_text("\n".join(self.lines) + "\n")


def commit(member: str, msg: str) -> None:
    subprocess.run(["git", "add", f"logs/pb/{member}"], cwd=ROOT)
    subprocess.run(["git", "commit", "-q", "-m", f"PB: {msg}", "--", "logs/pb"], cwd=ROOT)


def fmt(pt: dict) -> str:
    return ", ".join(f"{k}={v:g}" for k, v in pt.items())


def tune(member: str) -> None:
    pool, tbase, cbase, params = PLAN[member]
    rep = Report(member)
    defaults = {p: d for p, d, _, _ in params}
    best = dict(defaults)
    swing = {p: 0.0 for p in defaults}
    rep.add(f"## {member}: family {', '.join(pool)}; defaults {fmt(defaults)}")

    def go(pt: dict, seed: int, pairs: int = DESCENT_PAIRS, locks: str = "off") -> dict:
        return run_pool(member, brain(member, pt), key(pt), pool, pairs, seed, locks)

    # 1. coordinate descent
    moved_last = False
    for r in range(MAX_ROUNDS):
        seed = tbase + DESCENT_PAIRS * r
        center = go(best, seed)
        rep.add(f"\n### Descent round {r + 1} (seeds {seed}-{seed + DESCENT_PAIRS - 1}, {DESCENT_PAIRS} pairs, locks off)")
        rep.add(f"centre {fmt(best)}: " + ", ".join(f"{o} {x['chips']:+.2f}±{x['se']:.2f}" for o, x in center.items()) +
                f" | sum {sum(x['chips'] for x in center.values()):+.2f}")
        rep.add("| parameter | value | sum diff vs centre ± SE | z |")
        rep.add("|---|---|---|---|")
        cands = []
        for p, _, step, (lo, hi) in params:
            for sgn in (-1, 1):
                v = round(best[p] + sgn * step, 4)
                if not lo <= v <= hi:
                    rep.add(f"| {p} | {v:g} | out of range | |")
                    continue
                pt = {**best, p: v}
                d, se, z = delta(center, go(pt, seed))
                swing[p] = max(swing[p], abs(d))
                cands.append((d, z, pt, p))
                rep.add(f"| {p} | {v:g} | {d:+.2f} ± {se:.2f} | {z:+.1f} |")
        d, z, pt, p = max(cands, key=lambda c: c[0])
        moved_last = z > 1
        if moved_last:
            best = pt
            rep.add(f"**move** {p} -> {pt[p]:g} (diff {d:+.2f}, z {z:+.1f})")
        else:
            rep.add(f"**no move**: best candidate {p}={pt[p]:g} diff {d:+.2f}, z {z:+.1f} <= 1")
        commit(member, f"{member} descent round {r + 1}")
        if not moved_last:
            break
    if moved_last:
        rep.add(f"(descent stopped at the {MAX_ROUNDS}-round cap, light testing; last round moved)")

    # 2. 3x3 grid on the two most sensitive parameters
    top = sorted(swing, key=lambda p: -swing[p])[:2]
    steps = {p: (s, rng) for p, _, s, rng in params}
    gseed = tbase + 100
    rep.add(f"\n### Grid on {top[0]}, {top[1]} around {fmt(best)} (swings {', '.join(f'{p} {swing[p]:.2f}' for p in swing)}; "
            f"seeds {gseed}-{gseed + DESCENT_PAIRS - 1})")
    centre = go(best, gseed)
    rep.add(f"| {top[0]} \\ {top[1]} | " + " | ".join(f"{best[top[1]] + k * steps[top[1]][0]:g}" for k in (-1, 0, 1)) + " |")
    rep.add("|---|---|---|---|")
    gbest = (0.0, 0.0, best)
    for i in (-1, 0, 1):
        row = []
        for j in (-1, 0, 1):
            pt = dict(best)
            vals = {top[0]: round(best[top[0]] + i * steps[top[0]][0], 4), top[1]: round(best[top[1]] + j * steps[top[1]][0], 4)}
            if any(not steps[q][1][0] <= v <= steps[q][1][1] for q, v in vals.items()):
                row.append("out")
                continue
            pt.update(vals)
            if (i, j) == (0, 0):
                row.append("centre")
                continue
            d, se, z = delta(centre, go(pt, gseed))
            row.append(f"{d:+.2f} ± {se:.2f} (z {z:+.1f})")
            if d > gbest[0]:
                gbest = (d, z, pt)
        rep.add(f"| {best[top[0]] + i * steps[top[0]][0]:g} | " + " | ".join(row) + " |")
    if gbest[1] > 1:
        rep.add(f"**grid move** to {fmt(gbest[2])} (diff {gbest[0]:+.2f}, z {gbest[1]:+.1f})")
        best = gbest[2]
    else:
        rep.add(f"**no grid move** (best other point diff {gbest[0]:+.2f}, z {gbest[1]:+.1f} <= 1)")
    commit(member, f"{member} grid")
    rep.add(f"\nFinal point: {fmt(best)} (defaults {fmt(defaults)})")

    if best == defaults:
        rep.add("\nFinal point = PA defaults: nothing to confirm; MEMBERS unchanged.")
        rep.add("VERDICT: defaults")
        commit(member, f"{member} done (defaults)")
        return

    # 3. confirmation vs the PA defaults, one 50-pair run per lock mode, fresh seeds
    def conf(locks: str):
        a = run_pool(member, brain(member, defaults), key(defaults), pool, CONFIRM_PAIRS, cbase, locks)
        b = run_pool(member, brain(member, best), key(best), pool, CONFIRM_PAIRS, cbase, locks)
        return a, b
    a, b = conf("off")
    lines, keep_chips = chips_compare(chips(a), chips(b))
    d, se, z = delta(a, b)
    rep.add(f"\n### Confirmation vs defaults, {CONFIRM_PAIRS} pairs, seeds {cbase}-{cbase + CONFIRM_PAIRS - 1}, locks off (chips)")
    rep.add("```\n" + "\n".join(lines) + "\n```")
    a2, b2 = conf("on")
    slines, keep_score = score_compare(scores(a2), scores(b2))
    rep.add("locks on (score):\n```\n" + "\n".join(slines) + "\n```")
    keep = keep_chips and keep_score
    rep.add(f"Two-part rule: chips {'pass' if keep_chips else 'FAIL'} (sum {d:+.2f} ± {se:.2f}), score "
            f"{'pass' if keep_score else 'FAIL'} -> {'KEEP' if keep else 'DROP'}")
    commit(member, f"{member} confirmation")
    if not keep:
        rep.add("VERDICT: defaults (confirmation failed)")
        return

    # 4. restriction vs tier3 head to head, one 30-pair run, locks off, same fresh seeds (a different matchup)
    off = run(member, brain(member, best), key(best), "tier3", RESTRICT_PAIRS, cbase, "off")
    ok = off["chips"] >= -0.10
    rep.add(f"\n### Restriction vs tier3, {RESTRICT_PAIRS} pairs, locks off: {off['chips']:+.2f} ± {off['se']:.2f} chips/hand "
            f"({'ok' if ok else 'FAIL'}, limit -0.10); match score {off['score']:.3f} ± {off['sse']:.3f} (info)")
    rep.add("VERDICT: " + (f"KEEP {json.dumps(best)}" if ok else "defaults (restriction failed)"))
    commit(member, f"{member} restriction")


if __name__ == "__main__":
    for m in sys.argv[1:]:
        tune(m)

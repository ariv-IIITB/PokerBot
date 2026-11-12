"""All sparring and new bots against the reference opponents, 40 matches each, and the table.

    python eval/bots/stats.py run [--matches 40] [--seed-base 12001]     # plays (resumable: skips finished cells)
    python eval/bots/stats.py report                                      # writes eval/results/bot_stats.md

Opponents: final (dist/bot.py), tier3x (logs/tier3x.noindex/bot/bot.py), v16 (logs/v16.noindex/bot/bot.py),
v6 (logs/v6.noindex/bot/bot.py). Same deals for every bot (the same seeds), so cells are comparable. Results go to
logs/stats.noindex/<bot>__<opponent>/results.jsonl; the chips come from the engine summary per match.
"""
import json
import math
import pathlib
import statistics
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
PY = ROOT / ".venv311" / "bin" / "python"
OUT = ROOT / "logs" / "stats.noindex"
OPPS = [("v16", ROOT / "logs/v16.noindex/bot/bot.py"), ("v6", ROOT / "logs/v6.noindex/bot/bot.py"),
        ("final", ROOT / "dist/bot.py"), ("tier3x", ROOT / "logs/tier3x.noindex/bot/bot.py")]
SPAR = "eqtag trapper potctl polar betfold light3b donk adapt tilt discardread".split()
STRONG = "s1_ranges s3_exploit s6_discard s2_rollout s7_solver s8_meta s9_sizing s10_regret s5_preflop s4_balanced".split()
BOTS = [(n, ROOT / "eval/bots/strong" / n / "bot.py") for n in STRONG[:2]] + \
       [(n, ROOT / "eval/bots/spar" / n / "bot.py") for n in SPAR[:3]] + \
       [(n, ROOT / "eval/bots/strong" / n / "bot.py") for n in STRONG[2:]] + \
       [(n, ROOT / "eval/bots/spar" / n / "bot.py") for n in SPAR[3:]]


V4 = [("v4_" + n, ROOT / "eval/bots/spar_v4" / n / "bot.py") for n in SPAR]


def cell(bot, opp):
    return OUT / f"{bot}__{opp}"


def load(path):
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def run(matches, seed_base, bots=None):
    OUT.mkdir(parents=True, exist_ok=True)
    for opp, opath in OPPS:
        for bot, bpath in (bots or BOTS):
            d = cell(bot, opp)
            have = {r["seed"] for r in load(d / "results" / "results.jsonl")}
            if len(have) >= matches:
                continue
            subprocess.run([str(PY), str(ROOT / "eval/run_matches.py"), "--name", "results", "--a", str(bpath),
                            "--a-label", bot, "--b", f"{opp}={opath}", "--matches", str(matches),
                            "--seed-base", str(seed_base), "--workers", "4", "--allow-more-workers", "--out", str(d)],
                           stdout=(d.parent / f"{bot}__{opp}.txt").open("w"), stderr=subprocess.STDOUT, cwd=ROOT)


def stat(rows):
    ph = [r["net"]["A"] / max(1, r["played"]) for r in rows]
    m = statistics.mean(ph)
    h = 1.96 * statistics.stdev(ph) / math.sqrt(len(ph)) if len(ph) > 1 else float("nan")
    return sum(r["net"]["A"] > 0 for r in rows), sum(r["net"]["A"] < 0 for r in rows), m, h


def detail():
    """Every one of the 20 agent bots (10 new, 10 improved sparring variants) against each opponent, in full."""
    ORIG = {"v4_" + n: n for n in SPAR}
    out = ["# The 20 agent bots in detail", "",
           "Stage 1, 40 matches per cell on the same deals (seeds 12001-12040) for every bot. Won / lost / drawn matches, "
           "chips per hand with the 95% interval, total chips over the 40 matches, mean bot time used per match "
           "(both legs; the bank is 30 s per leg), forfeits and notices. Chips are the bot's view.", ""]
    for title, names in (("New bots (strong/)", STRONG), ("Improved sparring variants (spar_v4/)", ["v4_" + n for n in SPAR])):
        out += [f"## {title}", ""]
        for bot in names:
            out += [f"### {bot}" + (f"  (original: {ORIG[bot]})" if bot in ORIG else ""), "",
                    "| opponent | n | won-lost-drawn | chips/hand | 95% interval | total chips | time/match | forfeits | notices |",
                    "|---|---|---|---|---|---|---|---|---|"]
            for opp, _ in OPPS:
                rows = load(cell(bot, opp) / "results" / "results.jsonl")
                if not rows:
                    out.append(f"| {opp} | 0 | not run yet | | | | | | |")
                    continue
                w, l, m, h = stat(rows)
                d = len(rows) - w - l
                t = statistics.mean(r["time_used"]["A"] for r in rows)
                f = sum(bool(r["forfeits"]) for r in rows)
                nt = sum(sum(r["notices"].values()) if isinstance(r["notices"], dict) else r["notices"] for r in rows)
                tot = sum(r["net"]["A"] for r in rows)
                out.append(f"| {opp} | {len(rows)} | {w}-{l}-{d} | {m:+.2f} | {m - h:+.2f} .. {m + h:+.2f} | {tot:+d} | {t:.1f} s | {f} | {nt} |")
            if bot in ORIG:
                out += ["", "Original " + ORIG[bot] + " on the same deals: " + " | ".join(
                    f"{opp} {stat(load(cell(ORIG[bot], opp) / 'results' / 'results.jsonl'))[0]}-"
                    f"{stat(load(cell(ORIG[bot], opp) / 'results' / 'results.jsonl'))[1]} "
                    f"{stat(load(cell(ORIG[bot], opp) / 'results' / 'results.jsonl'))[2]:+.2f}" for opp, _ in OPPS
                    if load(cell(ORIG[bot], opp) / 'results' / 'results.jsonl'))]
            out.append("")
    p = ROOT / "eval/results/agent_bots_detail.md"
    p.write_text("\n".join(out) + "\n")
    print(f"wrote {p}")


def report():
    lines = ["# All bots against final, tier3x, v16 and v6", "",
             "Stage 1 matches (two legs of 200 hands, duplicate deals), the same seeds for every bot. Cell: matches won"
             " - lost, then chips per hand with the 95% interval (the bot's view). `n` below 40 means unfinished.", "",
             "| bot | " + " | ".join(o for o, _ in OPPS) + " |", "|---|" + "---|" * len(OPPS)]
    for bot, _ in BOTS:
        cells = []
        for opp, _ in OPPS:
            rows = load(cell(bot, opp) / "results" / "results.jsonl")
            if not rows:
                cells.append("not run yet")
                continue
            w, l, m, h = stat(rows)
            cells.append(f"{w}-{l} {m:+.2f} (±{h:.2f})" + (f" n={len(rows)}" if len(rows) < 40 else ""))
        lines.append(f"| {bot} | " + " | ".join(cells) + " |")
    p = ROOT / "eval/results/bot_stats.md"
    p.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "run":
        n = int(a[a.index("--matches") + 1]) if "--matches" in a else 40
        s = int(a[a.index("--seed-base") + 1]) if "--seed-base" in a else 12001
        run(n, s)
    elif a and a[0] == "run-v4":
        run(40, 12001, V4)
    elif a and a[0] == "detail":
        detail()
    elif a and a[0] == "report":
        report()
    else:
        raise SystemExit(__doc__)

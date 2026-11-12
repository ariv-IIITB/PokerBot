"""lakshya1 against final and against panav3 (final + overbetdef): one markdown report.

    python eval/lakshya_report.py FINAL_DIR NEW_DIR OUT.md

Both dirs are run_matches outputs with the same opponent label (lakshya1) and the same seeds; only seeds
counted in both are used. Chips are our bot's (A).
"""
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval import analyze as AN  # noqa: E402
from eval import matchlog as ML  # noqa: E402
from eval import run_matches as RM  # noqa: E402


def recs(d):
    return {r["seed"]: r for r in RM.load_records(pathlib.Path(d) / "results.jsonl") if not RM.exclusion(r)}


def hands_of(d, seeds):
    out = []
    for s, r in recs(d).items():
        if s not in seeds:
            continue
        for h in ML.parse_hands((pathlib.Path(r["log_dir"]) / "match.log").read_text()):
            h["replay"] = ML.replay(h)
            h["seed"] = s
            out.append(h)
    return out


def ci(xs):
    n = len(xs)
    mu = sum(xs) / n
    sd = (sum((v - mu) ** 2 for v in xs) / (n - 1)) ** 0.5 if n > 1 else 0.0
    return mu, 1.96 * sd / math.sqrt(n)


def endings(hs, who):
    rows = {}
    for h in hs:
        k = AN.ending(h, who)
        c, v = rows.get(k, (0, 0))
        rows[k] = (c + 1, v + h["net"][who])
    return rows


def facing(hs, who, by_size=True):
    """per (street, size bin): n, fold, call, raise, avg whole-hand net of calls and of folds, odds."""
    out = {}
    for h in hs:
        st = h["replay"]["steps"]
        for i, s in enumerate(st):
            if s["actor"] == who or s["code"] != "r" or s["allin"]:
                continue
            nx = next((t for t in st[i + 1:] if t["actor"] == who), None)
            if nx is None:
                continue
            k = (s["street"], AN.size_bin(s["frac"]))
            d = out.setdefault(k, {"f": 0, "c": 0, "r": 0, "fnet": 0, "cnet": 0})
            c = nx["code"] if nx["code"] in "fcr" else "c"
            d[c] += 1
            if c == "f":
                d["fnet"] += h["net"][who]
            elif c == "c":
                d["cnet"] += h["net"][who]
            break
    return out


def betting(hs, who):
    """who's own betting: per street, decisions not facing a bet -> bet rate and mean size; facing a bet -> f/c/r."""
    out = {}
    for h in hs:
        for s in h["replay"]["steps"]:
            if s["actor"] != who or s["street"] == "preflop":
                continue
            d = out.setdefault(s["street"], {"open_n": 0, "open_bet": 0, "size": 0.0, "big": 0, "face_n": 0, "f": 0, "c": 0, "r": 0})
            if s["to_call"] == 0:
                d["open_n"] += 1
                if s["code"] == "r":
                    d["open_bet"] += 1
                    d["size"] += s["frac"]
                    d["big"] += s["frac"] >= 1.0
            else:
                d["face_n"] += 1
                d[s["code"] if s["code"] in "fcr" else "c"] += 1
    return out


def seat(hs):
    out = {"button": [0, 0], "big_blind": [0, 0]}
    for h in hs:
        k = "button" if h["button"] == "A" else "big_blind"
        out[k][0] += 1
        out[k][1] += h["net"]["A"]
    return out


def exploit_lines(d, seeds):
    tot = {}
    legs = 0
    for s in seeds:
        r = recs(d)[s]
        for leg in (1, 2):
            f = pathlib.Path(r["log_dir"]) / f"A_leg{leg}_stderr.txt"
            if not f.exists():
                continue
            e = ML.parse_bot_stderr(f.read_text()).get("exploit")
            if not e:
                continue
            legs += 1
            for k, t in e["traits"].items():
                x = tot.setdefault(k, {"yes": 0, "no": 0, "open": 0, "on_hands": 0, "n": 0, "hits": 0})
                x[t["verdict"]] += 1
                x["on_hands"] += t["on_hands"]
                x["n"] += t["n"]
                x["hits"] += round((t["rate"] or 0) * t["n"])
            for k, v in e["touched"].items():
                tot.setdefault("touched_" + k, 0)
                tot["touched_" + k] += v
    return legs, tot


def main(fd, nd, out):
    rf, rn = recs(fd), recs(nd)
    seeds = sorted(set(rf) & set(rn), key=int)
    L = []
    w = L.append
    nf = [rf[s]["net"]["A"] for s in seeds]
    nn = [rn[s]["net"]["A"] for s in seeds]
    hands_per = rf[seeds[0]]["played"]
    H = hands_per * len(seeds)
    w("# lakshya1 vs final and vs panav3 (final + overbetdef)\n")
    w(f"{len(seeds)} paired seeds ({', '.join(seeds)}), {hands_per} hands per match, stage 2. Chips are ours (final / panav3), "
      "so negative = lakshya1 wins.\n")
    w("## 1. Headline\n")
    w("| bot | chips | chips/hand | 95% CI (per hand) | matches won | lost |\n|---|---|---|---|---|---|")
    for name, v in (("final (panav 2)", nf), ("panav3 (final + overbetdef)", nn)):
        mu, h = ci(v)
        w(f"| {name} | {sum(v):+d} | {sum(v) / H:+.3f} | {(mu - h) / hands_per:+.3f} .. {(mu + h) / hands_per:+.3f} | "
          f"{sum(x > 0 for x in v)} | {sum(x < 0 for x in v)} |")
    d = [b - a for a, b in zip(nf, nn)]
    mu, h = ci(d)
    w(f"\nPaired difference panav3 - final: {sum(d):+d} chips, {mu / hands_per:+.3f} +- {h / hands_per:.3f} chips/hand; "
      f"panav3 better on {sum(x > 0 for x in d)} of {len(d)} seeds.\n")
    w("## 2. Match by match\n")
    w("| seed | final | panav3 | panav3 - final |\n|---|---|---|---|")
    for s, a, b in zip(seeds, nf, nn):
        w(f"| {s} | {a:+d} | {b:+d} | {b - a:+d} |")
    hf, hn = hands_of(fd, set(seeds)), hands_of(nd, set(seeds))
    w("\n## 3. Where the chips go (how hands ended)\n")
    w("Chips per hand over all hands; 'we' = our bot.\n")
    ef, en = endings(hf, "A"), endings(hn, "A")
    w("| ended | final hands | final c/h | panav3 hands | panav3 c/h | change c/h |\n|---|---|---|---|---|---|")
    keys = sorted(set(ef) | set(en), key=lambda k: (AN.STREETS.index(k[0]), k[1]))
    for k in keys:
        a, b = ef.get(k, (0, 0)), en.get(k, (0, 0))
        w(f"| {k[0]} {k[1]} | {a[0]} | {a[1] / len(hf):+.3f} | {b[0]} | {b[1] / len(hn):+.3f} | {(b[1] / len(hn)) - (a[1] / len(hf)):+.3f} |")
    for name, e, n in (("final", ef, len(hf)), ("panav3", en, len(hn))):
        fold = sum(c for (s, k), (c, v) in e.items() if k == "we fold")
        tf = sum(c for (s, k), (c, v) in e.items() if k == "they fold")
        w(f"\n{name}: we fold {fold / n:.1%} of hands, lakshya1 folds {tf / n:.1%}.")
    w("\n## 4. Facing lakshya1's bets (not all-in): fold rate and what calls and folds earned\n")
    w("fold% vs the pot odds offered shows over- or under-defence. 'call net' / 'fold net' = average whole-hand chips "
      "of those hands (calls are selected: we call with our better hands).\n")
    ff, fn = facing(hf, "A"), facing(hn, "A")
    w("| street | bet size (pot) | n final | fold% final | n panav3 | fold% panav3 | call net final | call net panav3 | fold net |\n|---|---|---|---|---|---|---|---|---|")
    for k in sorted(set(ff) | set(fn), key=lambda k: (AN.STREETS.index(k[0]), AN.SIZE_BINS.index(next(b for b in AN.SIZE_BINS if b[2] == k[1])))):
        a = ff.get(k, {"f": 0, "c": 0, "r": 0, "fnet": 0, "cnet": 0})
        b = fn.get(k, {"f": 0, "c": 0, "r": 0, "fnet": 0, "cnet": 0})
        na, nb = a["f"] + a["c"] + a["r"], b["f"] + b["c"] + b["r"]
        if na + nb < 30:
            continue
        w(f"| {k[0]} | {k[1]} | {na} | {a['f'] / max(na, 1):.0%} | {nb} | {b['f'] / max(nb, 1):.0%} | "
          f"{a['cnet'] / max(a['c'], 1):+.1f} | {b['cnet'] / max(b['c'], 1):+.1f} | {a['fnet'] / max(a['f'], 1):+.1f} |")
    w("\n## 5. Facing an all-in\n")
    for name, hs in (("final", hf), ("panav3", hn)):
        fa = AN.facing_allin(hs, "A")
        w(f"- {name}: " + "; ".join(
            f"{st}: fold {len(x['fold'])} ({sum(y['net'] for y in x['fold']):+d}), call {len(x['call'])} ({sum(y['net'] for y in x['call']):+d}, "
            f"won {sum(y['net'] > 0 for y in x['call'])})" for st, x in sorted(fa.items(), key=lambda kv: AN.STREETS.index(kv[0]))))
    w("\n## 6. How lakshya1 plays (its own decisions, seen from both runs)\n")
    w("| vs | street | its bet rate (not facing a bet) | mean bet size (pot) | bets >= 1.0 pot | folds when facing our bet | calls | raises |\n|---|---|---|---|---|---|---|---|")
    for name, hs in (("final", hf), ("panav3", hn)):
        b = betting(hs, "B")
        for st in ("flop", "turn", "river"):
            x = b.get(st)
            if not x:
                continue
            w(f"| {name} | {st} | {x['open_bet'] / max(x['open_n'], 1):.0%} | {x['size'] / max(x['open_bet'], 1):.2f} | "
              f"{x['big'] / max(x['open_bet'], 1):.0%} | {x['f'] / max(x['face_n'], 1):.0%} | {x['c'] / max(x['face_n'], 1):.0%} | {x['r'] / max(x['face_n'], 1):.0%} |")
    w("\nOur own betting (same table, our bot):\n")
    w("| bot | street | bet rate | mean size | folds facing a bet | calls | raises |\n|---|---|---|---|---|---|---|")
    for name, hs in (("final", hf), ("panav3", hn)):
        b = betting(hs, "A")
        for st in ("flop", "turn", "river"):
            x = b.get(st)
            if x:
                w(f"| {name} | {st} | {x['open_bet'] / max(x['open_n'], 1):.0%} | {x['size'] / max(x['open_bet'], 1):.2f} | "
                  f"{x['f'] / max(x['face_n'], 1):.0%} | {x['c'] / max(x['face_n'], 1):.0%} | {x['r'] / max(x['face_n'], 1):.0%} |")
    w("\n## 7. Seats\n")
    sf, sn = seat(hf), seat(hn)
    w("| seat | final hands | final c/h | panav3 hands | panav3 c/h |\n|---|---|---|---|---|")
    for k in ("button", "big_blind"):
        w(f"| {k} | {sf[k][0]} | {sf[k][1] / max(sf[k][0], 1):+.3f} | {sn[k][0]} | {sn[k][1] / max(sn[k][0], 1):+.3f} |")
    w("\n## 8. Did the new move fire? (panav3's exploit layer, over its legs)\n")
    legs, tot = exploit_lines(nd, seeds)
    w(f"{legs} legs read.\n")
    w("| trait | legs at yes | no | undecided | rate (hits/decisions) |\n|---|---|---|---|---|")
    for k, x in tot.items():
        if isinstance(x, dict):
            w(f"| {k} | {x['yes']} | {x['no']} | {x['open']} | {x['hits']}/{x['n']} = {x['hits'] / max(x['n'], 1):.2f} |")
    w("\nDecisions changed per move: " + ", ".join(f"{k[8:]} {v}" for k, v in tot.items() if k.startswith("touched_")))
    pathlib.Path(out).write_text("\n".join(L) + "\n")
    print("wrote", out, len(L), "lines")


if __name__ == "__main__":
    main(*sys.argv[1:4])

"""RF: chips per river spot class, BASE vs SOLVER arms, plus range / RNR diagnostics.

    flock ... .venv/bin/python -m lab.rf_spots OPP --arm base|solver|na --pairs 25 --first-seed 73000 --out F.pkl
    .venv/bin/python -m lab.rf_spots --report F1.pkl F2.pkl ...

Per hand we record the FIRST river decision of ours: its class (we act first / checked to us / face a small bet < 0.75 pot /
face a big bet) and the action taken. The pre-river play is the same code in every arm, so the chips of the river alone,
`river_ev = delta + pot0 / 2` (pot0 = the pot when the river starts, each side has put in half of it), compare across arms
by class. Also logged: the narrowed range mass vs bet size (`_narrow_range`), the RNR mix weight and the opponent's
observed vs real river fold rate.
"""
import argparse
import json
import pickle
from multiprocessing import Pool

import numpy as np

import bot.brains.tier3 as t3
from bot.actions import CHECK, FOLD, RAISE
from bot.state import ME, OPP
from bot.strategy.river_solver import hand_ranks
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec

BASE = {"x_narrow": True, "x_air_eq": 0.45, "lock_enabled": False}
SOLVER = dict(BASE, t3_river_solver=True, river_budget_s=0.080, river_box_mult=50, river_max_iters=110)
ARMS = {"base": BASE, "solver": SOLVER,
        "na": dict(SOLVER, t3_river_narrow=True, t3_river_rnr=True, t3_river_shifts=True),
        "narrow": dict(SOLVER, t3_river_narrow=True), "rnr": dict(SOLVER, t3_river_rnr=True)}
CLASSES = ("first", "checked_to", "face_small", "face_big")


def classify(h) -> str:
    if h.tocall <= 0:
        return "checked_to" if any(r.street == 3 and r.actor == OPP for r in h.history) else "first"
    return "face_big" if h.tocall / max(1, h.pot - h.tocall) >= 0.75 else "face_small"


def run_match(job):
    opp, arm, cfg_extra, seed, flip, hands = job
    cfg = dict(ARMS[arm], **cfg_extra)
    recs, narrow, orig_play, orig_nr = {}, [], t3.Tier3Brain.play, t3.Tier3Brain._narrow_range

    def play(self, s, legal, budget_s, p):
        a = orig_play(self, s, legal, budget_s, p)
        h = s.hand
        if h is not None and h.street == 3 and not legal.can_special and id(h) not in recs and h.tocall >= 0:
            fr = self.opponent.spots.spots["fold_river"]
            recs[id(h)] = dict(h=h, cls=classify(h), kind=a.kind, pot0=h.pot - (h.my_bet or 0) - (h.opp_bet or 0),
                               fr_n=fr.n, fr_mean=fr.mean(),
                               ratio=h.tocall / max(1, h.pot - h.tocall) if h.tocall > 0 else 0.0, brain=self)
        return a

    def nr(self, w, rank, h, p):
        out = orig_nr(self, w, rank, h, p)
        if out is not w:
            srt = np.sort(rank)
            pct = (np.searchsorted(srt, rank, "left") + np.searchsorted(srt, rank, "right")) / (2.0 * len(rank))
            top = pct >= 0.7
            narrow.append(dict(h=h, ratio=h.tocall / max(1, h.pot - h.tocall), srt=srt, brain=self,
                               before=float(w[top].sum() / w.sum()), after=float(out[top].sum() / out.sum())))
        return out

    t3.Tier3Brain.play, t3.Tier3Brain._narrow_range = play, nr
    try:
        a = PlayerSpec.brain("tier3x", cfg).build()
        b = PlayerSpec.brain(opp).build()
        m = play_match([a, b] if flip == 0 else [b, a], load_variant("discard_holdem"), seed=seed, hands=hands)
    finally:
        t3.Tier3Brain.play, t3.Tier3Brain._narrow_range = orig_play, orig_nr
    out, hl, last = [], [], None
    for r in recs.values():
        h = r.pop("h")
        brain = last = r.pop("brain")
        hl.append(h)
        if h.delta is None:
            continue
        r.update(delta=h.delta, river_ev=h.delta + r["pot0"] / 2.0, seed=seed, flip=flip)
        # what the hand did after our decision (for action-level tables)
        r["final"] = "fold" if any(x.street == 3 and x.actor == ME and x.action.kind == FOLD for x in h.history) else \
            "oppfold" if any(x.street == 3 and x.actor == OPP and x.action.kind == FOLD for x in h.history) else "showdown"
        out.append(r)
    n, f = truth_from(hl)
    fr = last.opponent.spots.spots["fold_river"] if last is not None else None
    fold = dict(true_n=n, true_f=f, model_n=fr.n if fr else 0, model_mean=fr.mean() if fr else 0.0)
    nout = []
    for r in narrow:
        h = r.pop("h")
        brain = r.pop("brain")
        srt = r.pop("srt")
        if h.opp_cards and len(h.board) == 5 and len(h.opp_cards) == 2:
            hr = hand_ranks(brain.rules.evaluator, np.array([sorted(h.opp_cards)]), np.array(h.board))[0]
            r["actual_pct"] = float((np.searchsorted(srt, hr, "left") + np.searchsorted(srt, hr, "right")) / (2.0 * len(srt)))
        nout.append(r)
    return dict(recs=out, narrow=nout, seed=seed, flip=flip, fold=fold)


def truth_from(h_list):
    n = f = 0
    for h in h_list:
        hist = [x for x in h.history if x.street == 3]
        for i in range(len(hist) - 1):
            if hist[i].actor == ME and hist[i].action.kind == RAISE and hist[i + 1].actor == OPP:
                n += 1
                f += hist[i + 1].action.kind == FOLD
    return n, f


def collect(opp, arm, pairs, first_seed, hands, extra, procs):
    jobs = [(opp, arm, extra, seed, flip, hands) for seed in range(first_seed, first_seed + pairs) for flip in (0, 1)]
    with Pool(procs) as pool:
        res = pool.map(run_match, jobs, chunksize=1)
    recs = [r for x in res for r in x["recs"]]
    narrow = [r for x in res for r in x["narrow"]]
    folds = [x["fold"] for x in res]
    return dict(folds=folds, opp=opp, arm=arm, pairs=pairs, first_seed=first_seed, hands=hands, extra=extra, recs=recs, narrow=narrow)


def se(x):
    x = np.asarray(x, float)
    return x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else 0.0


def report(paths):
    data = [pickle.load(open(p, "rb")) for p in paths]
    for d in data:
        hands = d["pairs"] * 2 * d["hands"]
        print(f"=== {d['opp']} arm={d['arm']} {d['extra'] or ''} pairs={d['pairs']} river hands={len(d['recs'])} / {hands}")
        tot = np.array([r["river_ev"] for r in d["recs"]])
        fo = d.get("folds") or []
        if fo:
            tn, tf = sum(x["true_n"] for x in fo), sum(x["true_f"] for x in fo)
            mm = np.mean([x["model_mean"] for x in fo]); mn = np.mean([x["model_n"] for x in fo])
            pm = np.mean([0.5 * x["model_n"] / (x["model_n"] + 40) if x["model_n"] >= 20 else 0.0 for x in fo])
            print(f"  fold_river: real fold rate to our river bets {tf / max(1, tn):.3f} (n={tn}, {tn / len(fo):.0f}/match); model mean at match end {mm:.3f},"
                  f" n {mn:.0f}/match; RNR weight at match end {pm:.3f} (max {max([0.5 * x['model_n'] / (x['model_n'] + 40) if x['model_n'] >= 20 else 0.0 for x in fo]):.3f})")
        nr = d.get("narrow") or []
        if nr:
            for lo, hi in ((0, .4), (.4, .75), (.75, 1.2), (1.2, 99)):
                g = [r for r in nr if lo <= r["ratio"] < hi]
                sd = [r["actual_pct"] for r in g if "actual_pct" in r]
                if g:
                    print(f"  narrow bet {lo:.2f}-{hi:.2f} pot: n={len(g)} top-30% range mass before {np.mean([r['before'] for r in g]):.2f} after {np.mean([r['after'] for r in g]):.2f};"
                          f" real showdown hands in top 30%: {np.mean([x >= .7 for x in sd]) if sd else float('nan'):.2f} (n={len(sd)}, mean pct {np.mean(sd) if sd else float('nan'):.2f})")
        print(f"  river chips per hand played: {tot.sum() / hands:+.3f}  (SE {se(np.concatenate([tot, np.zeros(hands - len(tot))])):.3f})")
        for c in CLASSES:
            rs = [r for r in d["recs"] if r["cls"] == c]
            if not rs:
                continue
            ev = np.array([r["river_ev"] for r in rs])
            kinds = {}
            for r in rs:
                kinds.setdefault(r["kind"], []).append(r["river_ev"])
            ks = "  ".join(f"{k}:{len(v) / len(rs):.2f}({np.mean(v):+.1f})" for k, v in sorted(kinds.items()))
            print(f"  {c:11} n={len(rs):5} contrib/hand={ev.sum() / hands:+.3f}  mean/spot {ev.mean():+.2f}+-{se(ev):.2f}  {ks}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("opp", nargs="?")
    ap.add_argument("--arm", default="base")
    ap.add_argument("--pairs", type=int, default=25)
    ap.add_argument("--first-seed", type=int, default=73000)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--processes", type=int, default=3)
    ap.add_argument("--extra", default="{}")
    ap.add_argument("--out")
    ap.add_argument("--report", nargs="+")
    a = ap.parse_args()
    if a.opp == "diff":
        return diff_main(a.report)
    if a.report:
        report(a.report)
        return
    d = collect(a.opp, a.arm, a.pairs, a.first_seed, a.hands, json.loads(a.extra), a.processes)
    pickle.dump(d, open(a.out, "wb"))
    report([a.out])




def class_diff(base_path, arm_path):
    """Per-class river chips per hand, arm minus base, with the SE over duplicate pairs (seeds)."""
    out = {}
    for name, path in (("base", base_path), ("arm", arm_path)):
        d = pickle.load(open(path, "rb"))
        per = {c: {} for c in CLASSES + ("all",)}
        for r in d["recs"]:
            for c in (r["cls"], "all"):
                per[c][r["seed"]] = per[c].get(r["seed"], 0.0) + r["river_ev"]
        seeds = range(d["first_seed"], d["first_seed"] + d["pairs"])
        out[name] = {c: np.array([per[c].get(s, 0.0) for s in seeds]) / (2 * d["hands"]) for c in per}
    res = {}
    for c in out["base"]:
        x = out["arm"][c] - out["base"][c]
        res[c] = (out["base"][c].mean(), out["arm"][c].mean(), x.mean(), se(x))
    return res


def diff_main(argv):
    for opp in argv[1:]:
        for arm in argv[0].split(","):
            r = class_diff(f"logs/rf/d1_{opp}_base.pkl", f"logs/rf/d1_{opp}_{arm}.pkl")
            print(f"{opp:16} {arm:7} " + "  ".join(f"{c}: {v[2]:+.2f}+-{v[3]:.2f}" for c, v in r.items()) +
                  f"   (base all {r['all'][0]:+.2f})")


if __name__ == "__main__":
    main()

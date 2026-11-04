"""RD: trace every river solve (ranges in, strategy out) and join it to the hand's showdown, to check the two ranges.

    .venv/bin/python -m lab.rd_trace d_conv_opp3 --pairs 10 --first-seed 70000 --out logs/rd/trace_conv.pkl
    .venv/bin/python -m lab.rd_trace --analyse logs/rd/trace_conv.pkl

Per record: board, our hole, pot/bets, w_opp / w_hero over the full combo lists, the solver's root probs and labels,
the action played, then (after the hand) the opponent's real cards (showdown only) and our chip result.
Calibration (analyse): for showdown hands, the opponent's real combo under w_opp: mean log(N * w) (0 = no better than
uniform; higher = informative) and the PIT of its hand rank (uniform if calibrated); the same for our own hand under w_hero.
"""
import argparse
import pickle

import numpy as np

import bot.brains.tier3 as t3
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec

CFG = {"lock_enabled": False, "t3_river_solver": True, "river_budget_s": 0.080, "river_box_mult": 50, "river_max_iters": 110}


GRID = [(b, g, e) for b in (0.0, 3.0, 6.0) for g in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0) for e in (0.0, 0.2, 0.5)]


def own_grid(rec, hc, idx) -> dict:
    """log(N * w[our real hand]) under the shipped own_range_weights ("new") and the generic Inference defaults ("old")."""
    from bot.sim.inference import DEFAULTS, Inference
    from bot.strategy.own_range import own_range_weights
    rng = np.random.default_rng(1)
    out = {}
    for name, inf in (("new", None), ("old", Inference(dict(DEFAULTS, enabled=True)))):
        w = own_range_weights(rec, hc, rng, inf)
        out[name] = float(np.log(max(w[idx], 1e-12) * (w > 0).sum()))
    return out


def own_feats(rec) -> list:
    """Our own earlier decisions with the strength of our REAL hand then: ('bet', board size, legal kinds, kind, s) or
    ('discard', kept-strength per option, chosen index)."""
    from bot.sim.inference import DEFAULTS, Inference
    inf = Inference(dict(DEFAULTS, enabled=True))
    rng = np.random.default_rng(1)
    m, out = rec.mapping, []
    for d in rec.my_decisions:
        if not all(t in m for t in d.hole) or any(m.get(t) is None for t in d.board):
            continue
        holes = np.array([[m[t] for t in d.hole]], dtype=np.intp)
        board = [m[t] for t in d.board]
        if d.kind == "bet":
            out.append(("bet", len(board), d.legal_kinds, d.action.kind, float(inf.strength(rec, holes, board, rng)[0])))
        elif d.kind == "discard":
            opts = [o for o in d.options if o != "none"]
            ss = []
            for o in opts:
                drop = [int(x) for x in o.split("+")]
                keep = [i for i in range(holes.shape[1]) if i not in drop]
                ss.append(float(inf.strength(rec, holes[:, keep], board, rng)[0]) if keep else 0.0)
            if d.action.choice in opts:
                out.append(("discard", ss, opts.index(d.action.choice)))
    return out


OPP_GRID = [(b, g) for b in (0.0, 3.0, 6.0) for g in (0.0, 0.5, 1.0, 1.5, 3.0, 4.5)]


def opp_grid(rec, oc, actual, ow_shipped) -> dict:
    """log(N * w[opponent's real combo]) at showdown under Inference(beta, gamma) variants (no trust scaling)."""
    from bot.sim.inference import DEFAULTS, Inference
    rng = np.random.default_rng(2)
    hidden = [t for t in rec.state.hole[1 - rec.me] if t not in rec.mapping]
    k = [i for i, c in enumerate(oc) if sorted(c) == sorted(actual)]
    if not k or len(hidden) != 2:
        return {}
    k = k[0]
    seen = np.array(sorted(set(rec.mapping.values())), dtype=np.intp)
    dead = np.isin(oc, seen).any(axis=1)
    out = {}
    for b, g in OPP_GRID:
        lw = Inference(dict(DEFAULTS, enabled=True, beta=b, gamma=g)).log_weights(
            rec, {t: np.asarray(oc)[:, i] for i, t in enumerate(hidden)}, len(oc), rng)
        w = np.ones(len(oc)) if lw is None else np.exp(lw - lw.max())
        w[dead] = 0.0
        w /= w.sum()
        out[(b, g)] = float(np.log(max(w[k], 1e-12) * (w > 0).sum()))
    w = ow_shipped / ow_shipped.sum()
    out["shipped"] = float(np.log(max(w[k], 1e-12) * (w > 0).sum()))
    return out


def run(opp: str, pairs: int, first_seed: int, hands: int, cfg: dict, grid: bool = True, own_g: bool = True, slim: bool = True) -> list[dict]:
    recs: list[dict] = []
    cur: dict = {}
    orig_solve, orig_rs = t3.solve_river, t3.Tier3Brain._river_solve

    def solve(spot, hc, hw, hr, oc, ow, orr, idx, deadline, **kw):
        res = orig_solve(spot, hc, hw, hr, oc, ow, orr, idx, deadline, **kw)
        cur.update(spot=spot, hc=hc, hw=hw.copy(), hr=hr, oc=oc, ow=ow.copy(), orr=orr, idx=idx,
                   probs=None if res is None else res.probs.copy(), labels=None if res is None else res.labels,
                   iters=0 if res is None else res.iterations)
        return res

    def river_solve(self, s, legal, budget_s, p, t0):
        cur.clear()
        a = orig_rs(self, s, legal, budget_s, p, t0)
        if cur:
            if own_g:
                cur["own_ll"] = own_grid(s.rec, cur["hc"], cur["idx"])
            cur["own_dec"] = own_feats(s.rec)
            cur["rec"] = s.rec
            cur.update(hand=s.hand, action=a, board=list(s.hand.board), hole=list(s.hand.hole), who=id(self))
            recs.append(dict(cur))
        return a

    t3.solve_river, t3.Tier3Brain._river_solve = solve, river_solve
    try:
        for seed in range(first_seed, first_seed + pairs):
            for flip in (0, 1):
                a = PlayerSpec.brain("tier3", dict(cfg)).build()
                b = PlayerSpec.brain(opp).build()
                play_match([a, b] if flip == 0 else [b, a], load_variant("discard_holdem"), seed=seed, hands=hands)
                for r in recs:
                    if "seed" not in r:
                        r["seed"], r["flip"] = seed, flip
    finally:
        t3.solve_river, t3.Tier3Brain._river_solve = orig_solve, orig_rs
    out = []
    for r in recs:                       # drop the heavy refs, keep arrays + outcome
        h = r.pop("hand")
        r["opp_cards"] = tuple(h.opp_cards) if h.opp_cards else None
        rec = r.pop("rec")
        r["opp_ll"] = opp_grid(rec, r["oc"], r["opp_cards"], r["ow"]) if r["opp_cards"] and grid else {}
        r["delta"] = h.delta
        r["street_bets"] = [(x.street, x.actor, x.action.kind) for x in h.history if x.street == 3]
        r.pop("who", None)
        if slim:
            for k in ("hc", "hw", "hr", "oc", "ow", "orr", "probs", "labels"):
                r.pop(k, None)
        out.append(r)
    return out


def pit_loglik(w, rank, cards, actual, ):
    """(log(N*w[actual]) , PIT of actual's rank under w)"""
    w = w / w.sum()
    k = [i for i, c in enumerate(cards) if sorted(c) == sorted(actual)]
    if not k:
        return None
    k = k[0]
    lo = w[rank < rank[k]].sum()
    eq = w[rank == rank[k]].sum()
    return float(np.log(max(w[k], 1e-12) * (w > 0).sum())), float(lo + 0.5 * eq)


def analyse(path: str) -> None:
    recs = pickle.load(open(path, "rb"))
    if recs and recs[0].get("opp_ll") is not None:
        ol = [r["opp_ll"] for r in recs if r["opp_ll"]]
        if ol:
            tab = {k: np.mean([o[k] for o in ol]) for k in ol[0]}
            print(f"opp showdown mean log(N*w), n={len(ol)}: shipped {tab['shipped']:+.3f}; grid (beta,gamma):",
                  {k: round(v, 3) for k, v in tab.items() if k != "shipped"})
    if recs and "own_ll" in recs[0]:
        for k in recs[0]["own_ll"]:
            v = np.array([r["own_ll"][k] for r in recs])
            print(f"own hand mean log(N*w) [{k}] over {len(v)} solves: {v.mean():+.3f} +-{v.std() / np.sqrt(len(v)):.3f}")
    sd = [r for r in recs if r["opp_cards"]]
    if recs and "ow" not in recs[0]:
        return
    print(f"{len(recs)} river solves, {len(sd)} with showdown")
    for name, wk, ck, rk, key in (("opp range", "ow", "oc", "orr", "opp_cards"), ("own range", "hw", "hc", "hr", None)):
        ll, pit = [], []
        for r in sd:
            actual = r[key] if key else r["hole"]
            v = pit_loglik(np.asarray(r[wk], float), np.asarray(r[rk]), r[ck], actual)
            if v:
                ll.append(v[0]); pit.append(v[1])
        pit = np.array(pit)
        print(f"{name}: n={len(ll)} mean log(N*w)={np.mean(ll):+.3f} +-{np.std(ll)/np.sqrt(len(ll)):.3f}  "
              f"PIT mean {pit.mean():.3f} (0.5 ok) deciles {np.histogram(pit, bins=5, range=(0,1))[0] / len(pit)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("opp", nargs="?")
    ap.add_argument("--pairs", type=int, default=10)
    ap.add_argument("--first-seed", type=int, default=70000)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--out")
    ap.add_argument("--analyse")
    ap.add_argument("--full", action="store_true", help="keep the range arrays")
    a = ap.parse_args()
    if a.analyse:
        analyse(a.analyse)
    else:
        recs = run(a.opp, a.pairs, a.first_seed, a.hands, dict(CFG), slim=not a.full)
        pickle.dump(recs, open(a.out, "wb"))
        analyse(a.out)

"""River solver benchmark (RA spike, Tier 4): iterations per ms on real river spots.

Plays Tier 3 in-process against some opponents on Discard Hold'em, records every river
decision of ours (the Reconstruction, the street's bets, the stacks), then for each spot
times the whole pipeline the live bot would pay inside its time box:

  ranges   their range = Opponent.range_weights over the 903 combos left after the board, both
           discards and our hand (the same inference Tier 3 uses); ours = uniform over the 990
           combos consistent with our public discard (RB builds the real one)
  ranks    showdown values of all those combos on the board
  setup    tree + index arrays
  solve    CFR+ passes until the deadline

and reports iterations that fit in the box (default 20 ms) with the range building included.

CLI:  .venv/bin/python -m lab.river_bench --spots 200 --box-ms 20
      .venv/bin/python -m lab.river_bench --spots 200 --box-ms 20 --variant reduced
"""
from __future__ import annotations

import argparse
import platform
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from bot.actions import CHECK, RAISE
from bot.brains.tier3 import Tier3Brain
from bot.strategy.river_solver import (INF, RiverSolver, RiverSpot, TreeCfg, _tree_stats, bucket_kernel,
                                       bucket_ranges, hand_ranks, make_kernel, make_solver, solve_river)

# ---------------------------------------------------------------------------- recording


@dataclass
class Captured:
    rec: object                    # bot.sim.replay.Reconstruction at the decision
    spot: RiverSpot
    hole: tuple
    board: tuple
    opponent: object               # the brain's Opponent (inference model + trust)
    rng: object


class _Recorder(Tier3Brain):
    """Tier 3 that remembers every river decision of ours (then plays as usual)."""
    name = "tier3-recorder"

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.captured: list[Captured] = []

    def play(self, s, legal, budget_s, p):
        h = s.hand
        try:
            if h is not None and h.street == 3 and not legal.can_special and len(h.hole) == 2 \
                    and s.rec is not None:
                on = [r for r in h.history if r.street == 3]
                last = on[-1] if on else None
                spot = RiverSpot(
                    pot=float(h.pot), hero_bet=float(h.my_bet or 0), opp_bet=float(h.opp_bet or 0),
                    hero_stack=float(h.my_stack), opp_stack=float(h.opp_stack),
                    last_raise=float(h.tocall) if h.tocall > 0 else 0.0,
                    aggr_so_far=sum(1 for r in on if r.action.kind == RAISE),
                    checked=bool(last is not None and last.action.kind == CHECK))
                self.captured.append(Captured(s.rec, spot, tuple(h.hole), tuple(h.board),
                                              self.opponent, self.rng))
        except Exception:
            pass
        return super().play(s, legal, budget_s, p)


def record_spots(n: int, opponents=("d_new_trapper", "d_conv_opp3", "d_new_lag", "d_new_exploiter"),
                 variant: str = "discard_holdem", hands: int = 200, first_seed: int = 50000
                 ) -> list[Captured]:
    from lab.engine import play_match
    from lab.harness import load_variant
    from lab.players import InProcessPlayer, PlayerSpec
    cfg = load_variant(variant)
    out: list[Captured] = []
    seed = first_seed
    while len(out) < n:
        for opp in opponents:
            rec_brain = _Recorder()
            me = InProcessPlayer(rec_brain, "tier3-recorder")
            other = PlayerSpec.brain(opp).build(cfg)
            players = [me, other] if seed % 2 == 0 else [other, me]
            play_match(players, cfg, seed, hands)
            for p in players:
                try:
                    p.close()
                except Exception:
                    pass
            out.extend(rec_brain.captured)
            seed += 1
            if len(out) >= n:
                break
    return out[:n]


# ---------------------------------------------------------------------------- one spot


def build_inputs(c: Captured, max_opp: Optional[int] = None):
    """Ranges and ranks for one captured spot. Returns (dict, timings dict)."""
    t0 = time.perf_counter()
    rec = c.rec
    ev = rec.state.rules.evaluator
    pool = np.array(sorted(rec.pool), dtype=np.int64)
    i, j = np.triu_indices(len(pool), 1)
    opp_cards = np.stack([pool[i], pool[j]], axis=1)                  # 903 combos
    t1 = time.perf_counter()
    w_opp = c.opponent.range_weights(rec, opp_cards, c.rng)
    t2 = time.perf_counter()
    seen = set(int(x) for x in rec.mapping.values())
    hero_pool = np.array(sorted(set(pool.tolist()) | set(c.hole)), dtype=np.int64)
    i, j = np.triu_indices(len(hero_pool), 1)
    hero_cards = np.stack([hero_pool[i], hero_pool[j]], axis=1)       # 990 combos
    hero_w = np.ones(len(hero_cards))
    board = np.array(c.board, dtype=np.intp)
    hero_rank = hand_ranks(ev, hero_cards, board)
    opp_rank = hand_ranks(ev, opp_cards, board)
    t3 = time.perf_counter()
    hole = tuple(sorted(c.hole))
    idx = next(k for k in range(len(hero_cards)) if tuple(sorted(hero_cards[k].tolist())) == hole)
    return (dict(hero_cards=hero_cards, hero_w=hero_w, hero_rank=hero_rank, opp_cards=opp_cards,
                 opp_w=w_opp, opp_rank=opp_rank, hero_index=idx),
            {"combos": t1 - t0, "inference": t2 - t1, "ranks": t3 - t2})


def prune(inp: dict, keep_mass: float = 0.995, max_n: int = 300) -> dict:
    """Reduced version: drop combos with near-zero weight (keep the top mass, at most max_n,
    and always our own hand)."""
    out = dict(inp)
    for side, extra in (("opp", None), ("hero", inp["hero_index"])):
        w = inp[f"{side}_w"]
        order = np.argsort(-w, kind="stable")
        cum = np.cumsum(w[order]) / w.sum()
        k = int(min(max_n, np.searchsorted(cum, keep_mass) + 1))
        keep = set(order[:k].tolist())
        if extra is not None:
            keep.add(int(extra))
        keep = np.array(sorted(keep))
        out[f"{side}_cards"] = inp[f"{side}_cards"][keep]
        out[f"{side}_w"] = w[keep]
        out[f"{side}_rank"] = inp[f"{side}_rank"][keep]
        if extra is not None:
            out["hero_index"] = int(np.nonzero(keep == extra)[0][0])
    return out


FULL_TREE = TreeCfg()
SMALL_TREE = TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0, INF))      # pot + all-in only
# name -> (tree, prune the ranges first, buckets per player (0 = exact combos))
CONFIGS = {
    "full": (FULL_TREE, False, 0),
    "full/small-tree": (SMALL_TREE, False, 0),
    "pruned300": (FULL_TREE, True, 0),
    "pruned300/small-tree": (SMALL_TREE, True, 0),
    "bucket64": (FULL_TREE, False, 64),
    "bucket64/small-tree": (SMALL_TREE, False, 64),
    "bucket32/small-tree": (SMALL_TREE, False, 32),
    "bucket16/small-tree": (SMALL_TREE, False, 16),
}


def build_solver(c: Captured, inp: dict, name: str, dtype=np.float32, track_all: bool = False):
    """The solver for one config; returns (solver, hero index in its game, mapping info)."""
    tree, do_prune, nb = CONFIGS[name]
    x = prune(inp) if do_prune else inp
    if nb:
        hr, orr = x["hero_rank"], x["opp_rank"]
        hb, hbw = bucket_ranges(hr, x["hero_w"], nb)
        ob, obw = bucket_ranges(orr, x["opp_w"], nb)
        k = bucket_kernel(hr, x["hero_w"], hb, orr, x["opp_w"], ob, dtype)
        s = RiverSolver(c.spot, hbw, obw, k, tree, dtype, track_all)
        return s, int(hb[x["hero_index"]]), (hb, ob)
    s = make_solver(c.spot, x["hero_cards"], x["hero_w"], x["hero_rank"], x["opp_cards"],
                    x["opp_w"], x["opp_rank"], tree, "auto", dtype, track_all)
    return s, x["hero_index"], None


def time_box(c: Captured, inp: dict, timings: dict, name: str, box_s: float, dtype=np.float32) -> dict:
    """Solve one spot inside a box that already spent `timings` on range building."""
    spent = sum(timings.values())
    s0 = time.perf_counter()
    solver, idx, _ = build_solver(c, inp, name, dtype)
    setup = time.perf_counter() - s0
    left = box_s - spent - setup
    n_in_box = 0
    r0 = time.perf_counter()
    if left > 0:
        n_in_box = solver.run(r0 + left)
    run_s = time.perf_counter() - r0
    t_ss = time.perf_counter()                       # steady-state cost of a pass (arrays warm)
    solver.run(1e18, max_iters=5)
    per = (time.perf_counter() - t_ss) / 5
    return {"iters_in_box": n_in_box, "setup": setup, "spent_before": spent, "run_s": run_s,
            "n0": solver.n0, "n1": solver.n1, "solver": solver, "per_iter": per}


def exploit_after(c: Captured, inp: dict, name: str, iters: int, dtype=np.float32) -> dict:
    """Exploitability (pot = 1) of the strategy after `iters` passes: inside the game that was
    solved, and, for a bucketed or pruned-free game, translated back to the full exact game."""
    solver, idx, maps = build_solver(c, inp, name, dtype, track_all=True)
    solver.run(1e18, max_iters=max(iters, 1))
    inner = solver.exploitability()
    out = {"inner": inner}
    if maps is not None:                                  # bucketed: play each combo's bucket strategy
        hb, ob = maps
        avg = solver.average()
        N = max(len(hb), len(ob))
        full = np.zeros((avg.shape[0], avg.shape[1], N))
        for r in range(avg.shape[0]):
            m = hb if solver.actor[r] == 0 else ob
            full[r, :, :len(m)] = avg[r][:, m]
        kern = make_kernel(inp["hero_cards"], inp["hero_rank"], inp["opp_cards"], inp["opp_rank"], "sorted", np.float64)
        out["full_game"] = solver.exploitability(full, kern, (inp["hero_w"], inp["opp_w"]))
    return out


# ---------------------------------------------------------------------------- sensitivity to our range (RB)


def sensitivity(spots: list, iters: int = 150, buckets: int = 64, dtype=np.float32) -> dict:
    """Does the solver's answer depend on our range? Per spot, solve twice with the live recipe (bucketed,
    pot + all-in tree, `iters` passes): our range FLATTENED (uniform over the combos our public discard allows)
    and BUILT (bot/strategy/own_range.py). Returns the per-spot arrays
    ev_flat, ev_built (our hand's root value in pots, last pass, chips won - chips in over the whole hand),
    tv (total-variation distance between the two root strategies) and pot (chips)."""
    from bot.strategy.own_range import own_range_weights
    ev_f, ev_b, tv, pots = [], [], [], []
    for c in spots:
        inp, _ = build_inputs(c)
        hw_built = own_range_weights(c.rec, inp["hero_cards"], c.rng)
        got = []
        for hw in (np.ones(len(hw_built)), hw_built):
            hw = np.maximum(hw, 1e-9 * hw.max())
            res = solve_river(c.spot, inp["hero_cards"], hw, inp["hero_rank"], inp["opp_cards"], inp["opp_w"],
                              inp["opp_rank"], inp["hero_index"], 1e18, cfg=SMALL_TREE, max_iters=iters,
                              keep_solver=True, dtype=dtype, buckets=buckets)
            hb, _ = bucket_ranges(inp["hero_rank"], hw, buckets)
            got.append((float(res.solver.Val[0, 0, int(hb[inp["hero_index"]])]), res.probs, res.solver.tree.unit))
        ev_f.append(got[0][0]); ev_b.append(got[1][0])
        tv.append(0.5 * float(np.abs(got[0][1] - got[1][1]).sum()))
        pots.append(got[0][2])
    return {"ev_flat": np.array(ev_f), "ev_built": np.array(ev_b), "tv": np.array(tv), "pot": np.array(pots)}


def report_sensitivity(r: dict) -> str:
    d = np.abs(r["ev_built"] - r["ev_flat"])               # already in pots (the solver's unit)
    n = len(d)
    se = lambda a: a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else 0.0   # noqa: E731
    over = float((d > 0.20).mean())
    verdict = ("OWN RANGE IS THE WEAK POINT (the mean change is above 20 % of the pot)" if d.mean() > 0.20
               else "own range is not the weak point on average")
    return (f"sensitivity to our range ({n} river spots, root EV of our hand in pots, flat vs built): "
            f"|change| mean {d.mean():.3f} ± {se(d):.3f}, median {np.median(d):.3f}, p90 {np.percentile(d, 90):.3f}, "
            f"share of spots above 0.20 pot {over:.2f} | signed change (built - flat) mean "
            f"{(r['ev_built'] - r['ev_flat']).mean():+.3f} ± {se(r['ev_built'] - r['ev_flat']):.3f} | root strategy "
            f"total-variation distance mean {r['tv'].mean():.3f} ± {se(r['tv']):.3f}, share > 0.25: "
            f"{float((r['tv'] > 0.25).mean()):.2f} | {verdict}")


# ---------------------------------------------------------------------------- CLI


def main(argv: Optional[list[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="River solver speed on real recorded spots.")
    ap.add_argument("--spots", type=int, default=200)
    ap.add_argument("--box-ms", type=float, default=20.0)
    ap.add_argument("--variants", default=",".join(CONFIGS))
    ap.add_argument("--float64", action="store_true")
    ap.add_argument("--expl", type=int, default=0,
                    help="exploitability on this many spots (after the iterations that fit in the box)")
    ap.add_argument("--expl-iters", default="", help="...or after exactly these numbers of passes (comma list)")
    ap.add_argument("--sensitivity", type=int, default=0, metavar="N",
                    help="only: the solver's EV with our range flattened vs built, on N river spots (RB)")
    ap.add_argument("--first-seed", type=int, default=50000, help="first match seed for the recorded spots")
    args = ap.parse_args(argv)
    import os
    cpu = "?"
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name"))
    except Exception:
        pass
    print(f"machine: {cpu}, nproc={os.cpu_count()}")
    t0 = time.perf_counter()
    if args.sensitivity:
        spots = record_spots(args.sensitivity, first_seed=args.first_seed)
        print(f"recorded {len(spots)} river spots in {time.perf_counter() - t0:.0f}s")
        print(report_sensitivity(sensitivity(spots)))
        return
    spots = record_spots(args.spots, first_seed=args.first_seed)
    print(f"recorded {len(spots)} river spots in {time.perf_counter() - t0:.0f}s")
    built = [build_inputs(c) for c in spots]
    inf_t = np.array([b[1]["inference"] for b in built]) * 1e3
    rk_t = np.array([b[1]["ranks"] for b in built]) * 1e3
    cm_t = np.array([b[1]["combos"] for b in built]) * 1e3
    print(f"range building (all variants pay it): combos {np.median(cm_t):.2f} ms, inference "
          f"{np.median(inf_t):.1f} ms (p90 {np.percentile(inf_t, 90):.1f}), ranks {np.median(rk_t):.1f} ms; "
          f"opp weights above 1e-3 of the max: "
          f"{np.median([(b[0]['opp_w'] > 1e-3 * b[0]['opp_w'].max()).sum() for b in built]):.0f} of 903 (median)")
    box = args.box_ms / 1e3
    dt = np.float64 if args.float64 else np.float32
    for name in args.variants.split(","):
        res = [time_box(c, inp, tm, name, box, dt) for c, (inp, tm) in zip(spots, built)]
        its = np.array([r["iters_in_box"] for r in res])
        per = np.array([r["per_iter"] for r in res]) * 1e3
        setup = np.array([r["setup"] for r in res]) * 1e3
        pre = np.array([r["spent_before"] for r in res]) * 1e3
        solo = np.maximum((box * 1e3 - setup) / np.maximum(per, 1e-9), 0)
        print(f"[{name}] passes in a {args.box_ms:.0f} ms box, ranges included: median {np.median(its):.0f}, "
              f"p10 {np.percentile(its, 10):.0f}, p90 {np.percentile(its, 90):.0f}, share >= 100: "
              f"{np.mean(its >= 100):.2f} | ranges {np.median(pre):.1f} ms + setup {np.median(setup):.1f} ms "
              f"+ {np.median(per):.2f} ms/pass | n0/n1 {np.median([r['n0'] for r in res]):.0f}/"
              f"{np.median([r['n1'] for r in res]):.0f} | tree {_tree_stats(res[0]['solver'].tree)['decisions']} "
              f"decisions | passes if ranges were free: {np.median(solo):.0f}")
        if args.expl:
            runs = [int(x) for x in args.expl_iters.split(",")] if args.expl_iters else [0]
            for n_it in runs:
                ex = [exploit_after(c, inp, name, n_it or max(int(r["iters_in_box"]), 1), dt)
                      for c, (inp, tm), r in list(zip(spots, built, res))[:args.expl]]
                inner = np.array([e["inner"] for e in ex])
                se = lambda a: a.std(ddof=1) / np.sqrt(len(a)) if len(a) > 1 else 0.0   # noqa: E731
                line = (f"        after {n_it or 'the in-box number of'} passes: exploitability (pot = 1) in the solved game "
                        f"mean {inner.mean():.4f} ± {se(inner):.4f}, max {inner.max():.4f}")
                if "full_game" in ex[0]:
                    fg = np.array([e["full_game"] for e in ex])
                    line += (f" | translated to the exact full game: mean {fg.mean():.4f} ± {se(fg):.4f}, "
                             f"max {fg.max():.4f}")
                print(line + f" ({len(ex)} spots)")


if __name__ == "__main__":
    main()

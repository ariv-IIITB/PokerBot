"""Glue between our bot and the teammate's river solver (BUILDMAP §10, Phase 10).

botsrc/river_solver.py is the teammate's work, copied unchanged (docs/river_solver.md has the source
commit and sha256). This module only adapts it to our bot: decide(ctx) has the river_api signature,
RiverContext in, a distribution over legal actions out, or None. None means the bot plays the river
all-in rule and the blueprint river for this decision (botsrc/policy.py), so the solver can never
cost us a match.

What it does, per river decision:
  1. Ranges: ctx.my_range_now / ctx.opp_range_now, from our §9.6 range tracking (the opponent's is the
     one the river all-in rule uses), as weights over 2-card combos in the solver's card format.
     Our actual hand is always one of our combos.
  2. Hand ranks: rs.hand_ranks() with Evaluator below (our evaluator, values higher-wins).
  3. The spot from the request: pot, both street bets, both stacks, the last raise, raises so far
     this street, whether they checked, the minimum bet (the big blind), and the raise cap
     (raises so far + raises_left).
  4. solve(): what rs.solve_river(..., auto=True, cfg=TreeCfg(bet_sizes=(1.0, INF), raise_sizes=(1.0,
     INF), ...)) does, the teammate's settings, step by step through the solver's own rs.build_game,
     inside a time box of min(ctx.time_budget_ms, BOX_CAP_MS). Step by step so the glue also reads the
     root strategy of every combo of ours, not only our hand's.
  5. The answer: the root strategy for our hand, each root action mapped to a legal action (raises
     to our nearest legal raise). For every legal action it may take, the probability each combo of
     ours takes it is kept (taken_likelihood): after we play it, our range for the rest of the hand
     counts that action with the solver's own strategy, not the blueprint's RIVER table (policy.py).
  6. F-fold builds (ctx.opp_river_folds set): once the opponent has answered FOLD_MIN_N river bets or
     raises of ours, the solver's fold_obs read (RiverSolver.locked_values at the observed fold rate)
     and the teammate's RNR mix: (1 - w) x the solver's strategy + w x softmax(values / FOLD_TEMP),
     w = FOLD_PMAX x n / (n + FOLD_N0) (their tier3.py rnr_* settings; not their narrow or shifts).
Fallback (None) on an exception, no result, fewer than MIN_PASSES passes, a missed deadline, invalid
output or a root action that is not legal. Anything the solver prints goes to our stderr log.

Card formats: ours is rank * 4 + suit with suits "shdc" (BUILDMAP §4.1); the solver's (the teammate's
bot) is rank * 4 + suit with suits "cdhs". Ranks agree, the suit order is reversed: solver = ours ^ 3,
and the same XOR maps back.

Eval-only settings (tools/build_bot.py refuses them for dist/):
  pinned_passes  seeded eval builds: exactly that many passes, and the solver is told PIN_TIME_LEFT_S
                 is left (so it picks the bucket count of the 2x server's box), whatever the clock
                 says, so a seeded build repeats its results; no deadline check
  slowdown K     the emulated K times slower server: the solver gets 1/K of the box on the wall
                 clock, then the glue waits (K - 1) x what it took
  box_cap_ms     the time box's cap (BOX_CAP_MS by default): measures the passes a smaller box gives
  pin_buckets    pinned builds: the bucket count the solver picks (48, 64 or 96; 64 by default, the 2x
                 server's at an 80 ms box), through the time left it is told (PIN_TIME_LEFT)
"""
import contextlib
import math
import time

import numpy as np

from shared import betting as B
from shared import cards as C
from shared import showdown as SD

from .log import log
from .timeman import wait_ms

BOX_CAP_MS = 80.0          # time box: min(the time manager's solver budget, this)
MIN_PASSES = 20            # fewer passes: fall back (the teammate's river_min_iters)
GUARD_MS = 2.0             # the solver starts no pass this close to the end of the box
PIN_TIME_LEFT_S = 0.040    # pinned (seeded eval) builds: the time left the solver is told (2x server: 80 ms / 2)
PIN_TIME_LEFT = {48: 0.010, 64: PIN_TIME_LEFT_S, 96: 0.100}   # ... per pinned bucket count (auto_buckets'
                           # steps: 48 below 12 ms, 64 below 60 ms, else 96)
FLOOR_REL = 1e-9           # range weights floored at this share of the largest (as in the teammate's hook)
PASS_BIN = 10              # passes histogram bin width in the match-end log
PRINT_LINES = 5            # what the solver prints: the first this many lines reach stderr, the rest are counted
FOLD_MIN_N = 20            # F-fold: answered river bets of ours before the fold read is used (rnr_min_n)
FOLD_PMAX = 0.5            # ... mixing weight FOLD_PMAX * n / (n + FOLD_N0) (rnr_pmax, rnr_n0)
FOLD_N0 = 40.0
FOLD_TEMP = 0.05           # ... soft best response: softmax of the root action values / this, pot units (rnr_temp)
FOLD_RESERVE_MS = 1.0      # ... box time kept back for the fold read after the passes (RiverSolver.locked_values:
                           # about 0.3 ms, at most 0.35 ms on the M4 at 96 buckets, 5 Nov)

_rs = None                 # the solver module (botsrc.river_solver), set by setup()
_settings = {"pinned_passes": None, "slowdown": 1.0, "box_cap_ms": BOX_CAP_MS, "pin_time_left_s": PIN_TIME_LEFT_S}
STATS = {}
LAST = {}                  # the last answered decision: {"token": (hand id, river actions so far), "lik": {...}}


def reset_stats():
    STATS.clear()
    STATS.update({"calls": 0, "answered": 0, "fallback": {}, "passes_hist": {}, "buckets": {}, "ms_sum": 0.0,
                  "ms_max": 0.0, "box_sum": 0.0, "printed": 0, "passes": [], "fold_mixed": 0})
    LAST.clear()


reset_stats()


def setup(pinned_passes=None, slowdown=1.0, solver=None, box_cap_ms=None, pin_buckets=None):
    """Import the solver (or use `solver`, a module with the same API: tests) and set the eval-only
    switches. Raises if the solver cannot be imported; the caller then keeps the stub."""
    global _rs
    if solver is None:
        with contextlib.redirect_stdout(_ToLog()):
            from . import river_solver as solver
    if pinned_passes is not None and int(pinned_passes) < MIN_PASSES:
        raise ValueError(f"pinned passes {pinned_passes} < {MIN_PASSES}")
    _rs = solver
    _settings["pinned_passes"] = None if pinned_passes is None else int(pinned_passes)
    _settings["slowdown"] = max(1.0, float(slowdown or 1.0))
    cap = BOX_CAP_MS if box_cap_ms is None else float(box_cap_ms)
    if not 1.0 <= cap <= BOX_CAP_MS:
        raise ValueError(f"box cap {box_cap_ms} ms outside [1, {BOX_CAP_MS:g}]")
    _settings["box_cap_ms"] = cap
    if pin_buckets is not None and int(pin_buckets) not in PIN_TIME_LEFT:
        raise ValueError(f"pinned bucket count {pin_buckets} not in {sorted(PIN_TIME_LEFT)}")
    _settings["pin_time_left_s"] = PIN_TIME_LEFT[int(pin_buckets)] if pin_buckets is not None else PIN_TIME_LEFT_S
    reset_stats()


class _ToLog:
    """File-like object for redirect_stdout: what the solver prints goes to our capped stderr log."""

    def write(self, s):
        if s and s.strip():
            STATS["printed"] = STATS.get("printed", 0) + 1
            if STATS["printed"] <= PRINT_LINES:               # the stderr log has a 20 KB cap
                log("river solver printed: " + s.rstrip()[:300])
        return len(s)

    def flush(self):
        pass


# ---------------------------------------------------------------- cards and hand values

def to_solver(cards):
    """Our card ids -> the solver's (suits shdc -> cdhs): c ^ 3. Works on ints and int arrays."""
    if isinstance(cards, (int, np.integer)):
        return int(cards) ^ 3
    return np.asarray(cards, dtype=np.int64) ^ 3


from_solver = to_solver        # the map is its own inverse


class Evaluator:
    """The evaluator rs.hand_ranks() needs: evaluate_batch(hole (n, 2), board (5,)), cards in the
    solver's format, -> int64 values, higher wins, equal values split. A value is the dense rank of
    our hand value (BUILDMAP §4.4, shared.showdown.river_values) among all hands on that board: the
    same wins, losses and ties as our showdown code, and small numbers (the solver's sorted kernel
    needs values below 2**26; ours go up to 2**29). Cached for the last board."""

    def __init__(self):
        self.board = None
        self.rank = None

    def evaluate_batch(self, hole, board):
        ours = sorted(int(c) ^ 3 for c in np.asarray(board).ravel())
        if len(ours) != 5 or len(set(ours)) != 5:
            raise ValueError(f"need a 5-card board, got {ours}")
        if self.board != tuple(ours):
            vals = SD.river_values(ours)                      # int64[1326]; -1 where a combo hits the board
            live = vals >= 0
            rank = np.full(1326, -1, dtype=np.int64)
            rank[live] = np.unique(vals[live], return_inverse=True)[1].reshape(-1)
            self.board, self.rank = tuple(ours), rank
        h = np.asarray(hole, dtype=np.int64).reshape(-1, 2) ^ 3
        lo, hi = np.minimum(h[:, 0], h[:, 1]), np.maximum(h[:, 0], h[:, 1])
        out = self.rank[hi * (hi - 1) // 2 + lo]
        if (lo == hi).any() or (out < 0).any():
            raise ValueError("a combo repeats a card or shares one with the board")
        return out


EVALUATOR = Evaluator()


def range_combos(weights, must=None):
    """Combos with positive weight in a float64[1326] idx2 range (plus idx2 `must`, our own hand) ->
    (cards (n, 2) in the solver's format, weights floored at FLOOR_REL of the largest, idx2s)."""
    w = np.asarray(weights, dtype=np.float64)
    if w.shape != (1326,) or not np.isfinite(w).all() or (w < 0).any() or w.sum() <= 0:
        raise ValueError("bad range")
    keep = w > 0
    if must is not None:
        keep[must] = True
    K = np.nonzero(keep)[0]
    ww = np.maximum(w[K], FLOOR_REL * float(w.max()))
    return to_solver(C.COMBO[K]), ww, K


# ---------------------------------------------------------------- the spot

def street_state(ctx):
    """(last raise size, bets and raises so far, opponent has acted) from this street's history."""
    bets = {"me": 0, "opp": 0}
    last = raises = 0
    opp_acted = False
    for e in ctx.river_history:
        who, a = e.get("actor"), e.get("action")
        if who not in bets:
            raise ValueError(f"bad actor {who!r}")
        other = "opp" if who == "me" else "me"
        opp_acted = opp_acted or who == "opp"
        if a == "raise":
            amount = int(e["amount"])
            last, bets[who], raises = amount - bets[other], amount, raises + 1
        elif a == "call":
            bets[who] = bets[other]
        elif a not in ("check", "fold"):
            raise ValueError(f"bad action {a!r}")
    if bets["me"] != ctx.my_bet or bets["opp"] != ctx.opp_bet:
        raise ValueError(f"river history bets {bets} disagree with the request ({ctx.my_bet}, {ctx.opp_bet})")
    return last, raises, opp_acted


def spot_and_cfg(ctx, rs):
    last, raises, opp_acted = street_state(ctx)
    if "raise" in ctx.legal_actions and ctx.min_raise is not None and ctx.max_raise is not None \
            and ctx.min_raise < ctx.max_raise and ctx.min_raise != ctx.opp_bet + max(last, B.BIG_BLIND):
        raise ValueError(f"min_raise {ctx.min_raise} does not follow from the last raise {last}")
    spot = rs.RiverSpot(pot=float(ctx.pot), hero_bet=float(ctx.my_bet), opp_bet=float(ctx.opp_bet),
                        hero_stack=float(ctx.my_stack), opp_stack=float(ctx.opp_stack), last_raise=float(last),
                        aggr_so_far=int(raises), checked=bool(ctx.to_call == 0 and opp_acted))
    # min_raise == max_raise: only the shove is a legal raise (the engine's short stacks, where the pot
    # size collapses to all-in anyway, or the policy's shove-only spots): all-in is the only size
    allin_only = ctx.min_raise is not None and ctx.max_raise is not None and ctx.min_raise == ctx.max_raise
    sizes = (rs.INF,) if allin_only else (1.0, rs.INF)
    cfg = rs.TreeCfg(bet_sizes=sizes, raise_sizes=sizes, max_aggr=int(raises) + int(ctx.raises_left),
                     min_bet=float(B.BIG_BLIND))
    return spot, cfg


# ---------------------------------------------------------------- the answer

class Fallback(Exception):
    """A reason to play the blueprint + river rule for this decision."""


def legal_key(kind, level, ctx, rs):
    """A root action -> (legal action, raise-to amount or None), or None when it has no legal counterpart."""
    legal = ctx.legal_actions
    if kind == rs.FOLD and "fold" in legal:
        return ("fold", None)
    if kind == rs.CALL and "call" in legal:
        return ("call", None)
    if kind == rs.CHECK and "check" in legal:
        return ("check", None)
    if kind == rs.RAISE and "raise" in legal and ctx.min_raise is not None and ctx.max_raise is not None:
        if not math.isfinite(float(level)):
            raise Fallback("invalid")
        return ("raise", int(min(max(int(round(float(level))), int(ctx.min_raise)), int(ctx.max_raise))))
    return None


def answer(res, ctx, rs):
    """The solver's root strategy -> the §10 distribution over legal actions. Fallback if it is not a
    distribution or one of its actions (p > 0) has no legal counterpart."""
    return _mapped(res, ctx, rs)[0]


def _mapped(res, ctx, rs):
    """(the §10 distribution, the legal key of every root action: None for an action without one)."""
    probs = np.asarray(res.probs, dtype=np.float64)
    labels = list(res.labels)
    if probs.shape != (len(labels),) or not len(labels) or not np.isfinite(probs).all() or (probs < -1e-9).any() \
            or abs(float(probs.sum()) - 1.0) > 1e-6:
        raise Fallback("invalid")
    out, keys = {}, []
    for (kind, level), p in zip(labels, probs):
        try:
            key = legal_key(kind, level, ctx, rs)
        except Fallback:
            if p > 0:
                raise
            key = None
        keys.append(key)
        if p <= 0:
            continue
        if key is None:
            raise Fallback("unmapped")
        out[key] = out.get(key, 0.0) + float(p)
    if not out:
        raise Fallback("invalid")
    return [{"action": a, "amount": amt, "p": p} for (a, amt), p in out.items()], keys


def taken_by_combo(res, keys, dist, hero_K):
    """{legal key: float64[1326]}: for each legal action of the answer, the probability that each combo
    of ours (idx2 order, 0 off our range) takes it under the solver's root strategy (all root actions
    that map to it summed). The policy keeps the one it plays: our range for the rest of the hand."""
    combos = np.asarray(res.combos, dtype=np.float64)
    if combos.shape != (len(hero_K), len(keys)) or not np.isfinite(combos).all() or (combos < -1e-9).any():
        raise Fallback("invalid")
    out = {}
    for e in dist:
        key = (e["action"], e["amount"])
        v = np.zeros(1326)
        v[hero_K] = np.clip(combos[:, [i for i, k in enumerate(keys) if k == key]].sum(axis=1), 0.0, 1.0)
        out[key] = v
    return out


def taken_likelihood(hand_id, n_river, action, amount):
    """After the policy has played the solver's answer: the probability that each combo of ours takes
    that action (float64[1326]), or None (not the last answered decision, or an action it did not give)."""
    if LAST.get("token") != (hand_id, n_river):
        return None
    key = ("raise", int(amount)) if action == "raise" else (action, None)
    v = (LAST.get("lik") or {}).get(key)
    return None if v is None else v.copy()


def fold_read(folds):
    """F-fold: (fold_obs, mixing weight) from the opponent's (answered, folds) to our river bets and
    raises in this leg, or (None, 0.0) below FOLD_MIN_N answered (the teammate's RNR settings)."""
    if folds is None:
        return None, 0.0
    n, f = int(folds[0]), int(folds[1])
    if n < FOLD_MIN_N or not 0 <= f <= n:
        return None, 0.0
    return f / n, FOLD_PMAX * n / (n + FOLD_N0)


# ---------------------------------------------------------------- solve

class Solved:
    """solve()'s result: the root actions, our hand's strategy, every combo's (rows in our combo order)."""

    def __init__(self, labels, probs, combos, iterations, mixed):
        self.labels, self.probs, self.combos = labels, probs, combos
        self.iterations, self.mixed = iterations, mixed


def solve(rs, spot, cfg, hero, opp, hero_index, deadline, max_iters=10 ** 9, min_iters=0, fold_obs=None, pmix=0.0):
    """rs.solve_river(spot, ..., auto=True), step by step through the solver's own rs.build_game, so we
    can also read the root strategy of every combo of ours (through its bucket) and, with fold_obs, the
    values of every bucket. The same choices as solve_river: the bucket count from the time left at the
    start, None when the setup takes the box (unless min_iters) or not a single pass runs.
    hero, opp: (cards (n, 2) in the solver's format, weights > 0, ranks)."""
    hero_cards, hero_w, hero_rank = hero
    opp_cards, opp_w, opp_rank = opp
    t0 = time.perf_counter()
    s, idx, buckets = rs.build_game(spot, hero_cards, hero_w, hero_rank, opp_cards, opp_w, opp_rank, hero_index,
                                    cfg=cfg, track_all=fold_obs is not None, auto=True, time_left=deadline - t0)
    if time.perf_counter() >= deadline and min_iters <= 0:
        return None
    n = s.run(deadline, max_iters=max_iters, min_iters=min_iters)
    if n == 0:
        return None
    of = np.arange(len(hero_w)) if buckets is None else np.asarray(buckets[0], dtype=np.int64)
    if len(of) != len(hero_w) or (buckets is None and s.n0 != len(hero_w)) or int(of[hero_index]) != int(idx):
        raise ValueError("the solver's hands do not line up with our range")
    strat = np.array([s.root_strategy(j) for j in range(s.n0)], dtype=np.float64)   # (hands or buckets, actions)
    mixed = False
    if fold_obs is not None and pmix > 0:
        v, _, _ = s.locked_values(float(fold_obs))
        if v is not None:
            z = np.asarray(v, dtype=np.float64).T                                    # (hands or buckets, actions)
            br = np.exp((z - z.max(axis=1, keepdims=True)) / FOLD_TEMP)
            strat = (1.0 - pmix) * strat + pmix * br / br.sum(axis=1, keepdims=True)
            mixed = True
    return Solved(list(s.tree.root_labels), strat[idx], strat[of], n, mixed)


# ---------------------------------------------------------------- decide

def _count(reason):
    STATS["fallback"][reason] = STATS["fallback"].get(reason, 0) + 1


def decide(ctx):
    t0 = time.perf_counter()
    STATS["calls"] += 1
    LAST.clear()
    out = None
    try:
        with contextlib.redirect_stdout(_ToLog()):
            out = _decide(ctx, t0)
    except Fallback as f:
        _count(str(f))
    except Exception as e:
        _count("error")
        if STATS["fallback"]["error"] <= 3:
            log(f"river solver glue error: {type(e).__name__}: {e}")
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    k = _settings["slowdown"]
    if k > 1.0:
        wait_ms((k - 1.0) * elapsed_ms)                    # eval builds: a K times slower server
        elapsed_ms *= k
    STATS["ms_sum"] += elapsed_ms
    STATS["ms_max"] = max(STATS["ms_max"], elapsed_ms)
    if out is not None:
        STATS["answered"] += 1
    return out


def _decide(ctx, t0):
    rs = _rs
    if rs is None:
        raise Fallback("no_solver")
    pinned = _settings["pinned_passes"]
    box_ms = min(float(ctx.time_budget_ms), _settings["box_cap_ms"])
    if not box_ms > 0:
        raise Fallback("no_budget")
    STATS["box_sum"] += box_ms
    wall_end = t0 + box_ms / 1000.0 / _settings["slowdown"]
    board = [int(c) for c in ctx.board]
    hole = sorted(int(c) for c in ctx.hole)
    if len(board) != 5 or len(hole) != 2:
        raise Fallback("invalid_input")
    mine = ctx.my_range_now if ctx.my_range_now is not None else ctx.my_range
    theirs = ctx.opp_range_now if ctx.opp_range_now is not None else ctx.opp_range
    h = C.idx2(*hole)
    hero_cards, hero_w, hero_K = range_combos(mine, must=h)
    opp_cards, opp_w, _ = range_combos(theirs)
    hero_index = int(np.searchsorted(hero_K, h))
    sboard = to_solver(np.asarray(board, dtype=np.int64))
    hero_rank = rs.hand_ranks(EVALUATOR, hero_cards, sboard)
    opp_rank = rs.hand_ranks(EVALUATOR, opp_cards, sboard)
    spot, cfg = spot_and_cfg(ctx, rs)
    fold_obs, pmix = fold_read(getattr(ctx, "opp_river_folds", None))
    hero, opp = (hero_cards, hero_w, hero_rank), (opp_cards, opp_w, opp_rank)
    if pinned is not None:
        pin_left = _settings["pin_time_left_s"]
        deadline = time.perf_counter() + pin_left
        key = _bucket_key(rs, pin_left, hero_w, opp_w)
        STATS["buckets"][key] = STATS["buckets"].get(key, 0) + 1
        res = solve(rs, spot, cfg, hero, opp, hero_index, deadline, max_iters=pinned, min_iters=pinned,
                    fold_obs=fold_obs, pmix=pmix)
    else:
        deadline = wall_end - (GUARD_MS + (FOLD_RESERVE_MS if fold_obs is not None else 0.0)) / 1000.0
        left = deadline - time.perf_counter()
        if left <= 0:
            raise Fallback("no_time")
        key = _bucket_key(rs, left, hero_w, opp_w)
        STATS["buckets"][key] = STATS["buckets"].get(key, 0) + 1
        res = solve(rs, spot, cfg, hero, opp, hero_index, deadline, fold_obs=fold_obs, pmix=pmix)
    passes = 0 if res is None else int(res.iterations)
    STATS["passes"].append(passes)
    b = passes // PASS_BIN * PASS_BIN
    STATS["passes_hist"][b] = STATS["passes_hist"].get(b, 0) + 1
    if res is None:
        raise Fallback("none")
    if passes < MIN_PASSES:
        raise Fallback("few_passes")
    if pinned is None and time.perf_counter() > wall_end:
        raise Fallback("late")
    dist, keys = _mapped(res, ctx, rs)
    lik = taken_by_combo(res, keys, dist, hero_K)
    STATS["fold_mixed"] += int(res.mixed)
    LAST.update(token=(ctx.hand_id, len(ctx.river_history)), lik=lik)
    return dist


def _bucket_key(rs, time_left_s, hero_w, opp_w):
    """What auto=True plays at this time left: 'exact' or the bucket count (for the log only)."""
    try:
        n = rs.auto_buckets(time_left_s)
        return "exact" if max(len(hero_w), len(opp_w)) <= n else int(n)
    except Exception:
        return "?"


def summary():
    """One dict for the match-end log line "river solver: {...}"."""
    p = sorted(STATS["passes"])
    q = (lambda f: p[min(len(p) - 1, int(f * len(p)))] if p else None)
    return {"calls": STATS["calls"], "answered": STATS["answered"], "fallback": dict(STATS["fallback"]),
            "passes_p10": q(0.1), "passes_p50": q(0.5), "passes_p90": q(0.9), "passes_min": p[0] if p else None,
            "passes_max": p[-1] if p else None, "passes_hist": dict(sorted(STATS["passes_hist"].items())),
            "buckets": dict(STATS["buckets"]), "ms_sum": round(STATS["ms_sum"], 1), "ms_max": round(STATS["ms_max"], 1),
            "box_sum": round(STATS["box_sum"], 1), "printed": STATS["printed"], "fold_mixed": STATS["fold_mixed"],
            "pinned": _settings["pinned_passes"], "slowdown": _settings["slowdown"], "box_cap_ms": _settings["box_cap_ms"]}

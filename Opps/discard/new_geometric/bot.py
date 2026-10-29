#!/usr/bin/env python3
"""Geometric / theory-minded Discard Hold'em bot.

Run with:  python3.11 bot.py        (stdin/stdout JSON lines, see protocol spec)

Design in one paragraph
-----------------------
* Strength: Monte Carlo equity against a uniform opponent range (card removal for
  our cards, the board and both exposed discards).  The opponent's pair is
  re-weighted softly by "would a sensible player have discarded that exposed card
  from these three?" (the only public information about the range).  On the river
  the equity is computed exactly by enumerating all opponent holdings.
  Equity against a uniform range is a percentile of our hand inside the range; the
  decision code works on this "rank" in [0, 1].
* Bet sizing from pot geometry: with effective stack S, pot P and n streets left,
  the bet fraction f = ((1 + 2S/P)^(1/n) - 1) / 2 puts the stack in by the river
  when every street is bet and called.  Fractions are clamped to [0.5, 1.3] pots and
  a bet that would commit >= 55 % of what is left becomes an all-in.
* Polarised betting: a bet of size B into pot P is made with the top MDF/2 of the
  range for value (MDF = P / (P + B), the value hands beat the opponent's calling
  range more than half the time) plus bluffs in the ratio B : (P + B) of the value
  hands, taken from the weakest hands and from draws (semi-bluffs).
* Defence: facing a bet we continue with (at least) the minimum defence frequency
  MDF = P0 / (P0 + B), widened against opponents whose observed betting frequency
  (per node and bet size) is higher than a balanced range would have, and
  tightened against clear nits.  Strong hands raise (same geometric sizing).
* Discard: the card to throw away is chosen by Monte Carlo equity of the three
  possible two-card hands (common random numbers), opponent keeps its best two of
  three by a flop heuristic.
* Safety: every handler is wrapped, every action is validated against
  legal_actions / min_raise / max_raise, time use is paced from time_left_ms and
  falls back to cheap rules when the bank is low.
"""
import os

for _k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_k, "1")

import sys
import json
import math
import random
import time
import itertools

import numpy as np

np.seterr(all="ignore")

# --------------------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------------------
RANKS = "23456789TJQKA"
SUITS = "shdc"


def c2i(s):
    """'As' -> int 0..51 (rank * 4 + suit)."""
    return RANKS.index(s[0].upper()) * 4 + SUITS.index(s[1].lower())


def i2c(i):
    return RANKS[i >> 2] + SUITS[i & 3]


# --------------------------------------------------------------------------------------
# Vectorised hand evaluator (works for 5, 6 or 7 cards per row)
# --------------------------------------------------------------------------------------
_CATBASE = 14 ** 5
_BIT = np.array([1 << r for r in range(13)], dtype=np.int32)
_AR13 = np.arange(13, dtype=np.int16)
_AR4 = np.arange(4, dtype=np.int16)
_AR5 = np.arange(5, dtype=np.int16)
_W5 = np.array([14 ** 4, 14 ** 3, 14 ** 2, 14, 1], dtype=np.int32)
# number of tie-break entries that matter per category (HC, pair, 2p, trips, -, -, FH, quads, -)
_REL = np.array([5, 4, 3, 3, 0, 0, 2, 2, 0], dtype=np.int16)
KEEP = np.array([[1, 2], [0, 2], [0, 1]], dtype=np.int64)  # cards kept when discarding j


def _build_tables():
    straight = np.full(8192, -1, dtype=np.int8)
    flushval = np.zeros(8192, dtype=np.int32)
    wins = []
    for hi in range(4, 13):
        m = 0
        for r in range(hi - 4, hi + 1):
            m |= 1 << r
        wins.append((m, hi))
    wheel = (1 << 12) | 0b1111
    for m in range(8192):
        best = -1
        for wm, hi in wins:
            if m & wm == wm:
                best = hi
        if best < 0 and (m & wheel) == wheel:
            best = 3
        straight[m] = best
        if bin(m).count("1") >= 5:
            v = 0
            cnt = 0
            for r in range(12, -1, -1):
                if (m >> r) & 1:
                    v = v * 14 + r + 1
                    cnt += 1
                    if cnt == 5:
                        break
            flushval[m] = v
    return straight, flushval


_STRAIGHT, _FLUSHVAL = _build_tables()


def evaluate(cards):
    """Score hands: cards is an int array (N, k), k in 5..7, card = rank*4 + suit.
    Returns int array (N,) - higher is better, equal means a tie.
    Categories: 0 high card .. 8 straight flush; score = category * 14^5 + tie-break."""
    cards = np.asarray(cards)
    n, k = cards.shape
    ranks = cards >> 2
    suits = cards & 3
    rows = np.arange(n)
    bit = _BIT[ranks]
    rmask = np.bitwise_or.reduce(bit, axis=1)
    rowoff = rows[:, None]
    counts = np.bincount((rowoff * 13 + ranks).ravel(), minlength=n * 13).reshape(n, 13)
    sidx = (rowoff * 4 + suits).ravel()
    sc = np.bincount(sidx, minlength=n * 4).reshape(n, 4)
    fs = sc.argmax(axis=1)
    flush = sc[rows, fs] >= 5
    smask = np.bincount(sidx, weights=bit.ravel(), minlength=n * 4).reshape(n, 4).astype(np.int32)
    fmask = np.where(flush, smask[rows, fs], 0)
    st = _STRAIGHT[rmask].astype(np.int32)
    stf = _STRAIGHT[fmask].astype(np.int32)

    c = counts
    has4 = (counts == 4).any(axis=1)
    if has4.any():
        # with quads only the best single kicker matters
        c = np.where(has4[:, None], np.where(counts == 4, 4, np.minimum(counts, 1)), counts)
    if k >= 6:
        pm = c == 2
        cs = np.cumsum(pm[:, ::-1], axis=1)[:, ::-1]
        # three pairs: the lowest pair only supplies a kicker
        c = np.where(pm & (cs > 2), 1, c)
    n4 = (c == 4).sum(axis=1)
    n3 = (c == 3).sum(axis=1)
    n2 = (c == 2).sum(axis=1)
    cat_p = np.where(
        n4 > 0, 7,
        np.where((n3 >= 2) | ((n3 == 1) & (n2 >= 1)), 6,
                 np.where(n3 == 1, 3, np.where(n2 >= 2, 2, np.where(n2 == 1, 1, 0)))))

    keys = c.astype(np.int16) * 16 + _AR13
    top = np.sort(np.partition(keys, 8, axis=1)[:, 8:], axis=1)[:, ::-1]
    tr = (top & 15).astype(np.int32)
    tc = top >> 4
    rel = _REL[cat_p]
    mask = (_AR5 < rel[:, None]) & (tc > 0)
    tbp = ((tr + 1) * mask * _W5).sum(axis=1)

    cat = np.maximum(cat_p, np.where(st >= 0, 4, 0))
    cat = np.maximum(cat, np.where(flush, 5, 0))
    cat = np.maximum(cat, np.where(stf >= 0, 8, 0))
    tb = np.where(cat == 8, stf + 1,
                  np.where(cat == 5, _FLUSHVAL[fmask],
                           np.where(cat == 4, st + 1, tbp)))
    return cat.astype(np.int64) * _CATBASE + tb


# --------------------------------------------------------------------------------------
# Discard heuristic (flop-based), used for the opponent model and preflop simulation
# --------------------------------------------------------------------------------------
def _hand_value5(c5, hole):
    """Heuristic value of 5 cards (2 hole + flop): made hand + draw bonuses."""
    sc = evaluate(c5)
    cat = sc // _CATBASE
    made = sc / (9.0 * _CATBASE)
    ranks = c5 >> 2
    suits = c5 & 3
    rm = np.bitwise_or.reduce(_BIT[ranks], axis=1)
    cand = rm[:, None] | _BIT[None, :]
    new = (rm[:, None] & _BIT[None, :]) == 0
    nout = ((_STRAIGHT[cand] >= 0) & new).sum(axis=1)
    sd = np.where(cat <= 3, 0.036 * np.minimum(nout, 2), 0.0)
    sc4 = (suits[:, :, None] == _AR4).sum(axis=1)
    fd4 = sc4.max(axis=1) == 4
    fsuit = sc4.argmax(axis=1)
    hole_in = ((hole & 3) == fsuit[:, None]).sum(axis=1)
    fd = np.where(fd4 & (cat <= 4), 0.03 + 0.025 * hole_in, 0.0)
    return made + sd + fd


def keep_values(h3, flop):
    """h3 (N,3), flop (N,3) -> (N,3): heuristic value of the kept pair when discarding j."""
    out = np.empty((h3.shape[0], 3))
    for j in range(3):
        kept = h3[:, KEEP[j]]
        out[:, j] = _hand_value5(np.concatenate([kept, flop], axis=1), kept)
    return out


def _kept(h3, j):
    return np.take_along_axis(h3, KEEP[j], axis=1)


# --------------------------------------------------------------------------------------
# Monte Carlo helpers
# --------------------------------------------------------------------------------------
def _unseen(dead):
    d = set(dead)
    return np.array([c for c in range(52) if c not in d], dtype=np.int16)


def _draw(rng, unseen, n, k):
    keys = rng.random((n, unseen.shape[0]), dtype=np.float32)
    idx = np.argpartition(keys, k - 1, axis=1)[:, :k]
    return unseen[idx]


def _tile(cards, n):
    return np.tile(np.asarray(cards, dtype=np.int16), (n, 1))


def _cmp(a, b, w=None):
    r = (a > b) * 1.0 + (a == b) * 0.5
    if w is None:
        return float(r.mean())
    s = float(w.sum())
    return float((r * w).sum() / s) if s > 0 else float(r.mean())


W_MISS = 0.3  # weight of an opponent holding for which the exposed discard looks "wrong"


def _opp_weights(opp2, opp_disc, flop):
    """Soft weights: would the exposed discard be the heuristic choice from these 3 cards?"""
    m = opp2.shape[0]
    if opp_disc is None:
        return np.ones(m)
    h3 = np.concatenate([opp2, np.full((m, 1), opp_disc, dtype=opp2.dtype)], axis=1)
    vals = keep_values(h3, _tile(flop, m))
    ok = vals[:, 2] >= vals.max(axis=1) - 0.004
    return np.where(ok, 1.0, W_MISS)


def analyze_pre(hero3, n, rng):
    """Preflop equity of a 3-card hand vs a random 3-card hand; both keep 2 of 3 on the flop."""
    unseen = _unseen(hero3)
    d = _draw(rng, unseen, n, 8)
    opp3 = d[:, 0:3]
    flop = d[:, 3:6]
    tr = d[:, 6:8]
    h3 = _tile(hero3, n)
    hk = _kept(h3, keep_values(h3, flop).argmax(axis=1))
    ok = _kept(opp3, keep_values(opp3, flop).argmax(axis=1))
    board = np.concatenate([flop, tr], axis=1)
    hs = evaluate(np.concatenate([hk, board], axis=1))
    os_ = evaluate(np.concatenate([ok, board], axis=1))
    return _cmp(hs, os_)


def analyze_flop_pre(hero3, flop, n, rng):
    """Flop before the discard: returns (equity per discard option, hand strength of best option)."""
    unseen = _unseen(list(hero3) + list(flop))
    d = _draw(rng, unseen, n, 5)
    opp3 = d[:, 0:3]
    tr = d[:, 3:5]
    fl = _tile(flop, n)
    ok = _kept(opp3, keep_values(opp3, fl).argmax(axis=1))
    board = np.concatenate([fl, tr], axis=1)
    os7 = evaluate(np.concatenate([ok, board], axis=1))
    eqs = []
    for j in range(3):
        keep = [hero3[i] for i in range(3) if i != j]
        h7 = evaluate(np.concatenate([_tile(keep, n), board], axis=1))
        eqs.append(_cmp(h7, os7))
    jb = int(np.argmax(eqs))
    keep = [hero3[i] for i in range(3) if i != jb]
    os5 = evaluate(np.concatenate([ok, fl], axis=1))
    h5 = evaluate(np.concatenate([_tile(keep, n), fl], axis=1))
    return eqs, _cmp(h5, os5)


def analyze_post(hero2, board, opp_disc, n, rng, my_disc=None):
    """After the discard.  Returns (equity, hand strength now).  River is exact."""
    m = len(board)
    dead = list(hero2) + list(board)
    if opp_disc is not None:
        dead.append(opp_disc)
    if my_disc is not None:
        dead.append(my_disc)
    unseen = _unseen(dead)
    flop = list(board[:3])
    if m == 5:
        iu = np.triu_indices(unseen.shape[0], 1)
        opp2 = np.stack([unseen[iu[0]], unseen[iu[1]]], axis=1)
        if n < opp2.shape[0]:  # short on time: random subset of the opponent holdings
            opp2 = opp2[rng.choice(opp2.shape[0], size=n, replace=False)]
        cnt = opp2.shape[0]
        w = _opp_weights(opp2, opp_disc, flop)
        osc = evaluate(np.concatenate([opp2, _tile(board, cnt)], axis=1))
        hsc = evaluate(np.array([list(hero2) + list(board)], dtype=np.int16))
        eq = _cmp(hsc, osc, w)
        return eq, eq
    d = _draw(rng, unseen, n, 2 + (5 - m))
    opp2 = d[:, 0:2]
    extra = d[:, 2:]
    bd = _tile(board, n)
    full = np.concatenate([bd, extra], axis=1)
    w = _opp_weights(opp2, opp_disc, flop)
    hero_full = np.concatenate([_tile(hero2, n), full], axis=1)
    osc = evaluate(np.concatenate([opp2, full], axis=1))
    hsc = evaluate(hero_full)
    eq = _cmp(hsc, osc, w)
    hnow = evaluate(np.concatenate([_tile(hero2, n), bd], axis=1))
    onow = evaluate(np.concatenate([opp2, bd], axis=1))
    return eq, _cmp(hnow, onow, w)


# Quantiles (0, 5, ..., 100 %) of the preflop equity of a random 3-card hand, from simulation
# (analyze_pre, 700 samples, 2500 random hands).  Used to turn an equity into a percentile rank.
PRE_Q = np.array([0.2907, 0.3729, 0.3979, 0.4121, 0.4236, 0.4364, 0.4464, 0.4586, 0.4700,
                  0.4800, 0.4886, 0.4993, 0.5086, 0.5200, 0.5300, 0.5429, 0.5571, 0.5721,
                  0.5936, 0.6686, 0.8100])
PRE_P = np.linspace(0.0, 1.0, len(PRE_Q))


def pre_pct(eq):
    return float(np.interp(eq, PRE_Q, PRE_P))


def emergency_rank(hole, board):
    """Cheap strength estimate without simulation (time almost out)."""
    try:
        if len(board) >= 3 and len(hole) >= 2:
            if len(hole) == 3:
                flop = np.array([board[:3]] * 3, dtype=np.int16)
                h3 = np.array([hole] * 3, dtype=np.int16)
                # best two by heuristic
                v = keep_values(h3[:1], flop[:1])[0]
                hole = [hole[i] for i in range(3) if i != int(np.argmax(v))]
            sc = int(evaluate(np.array([list(hole) + list(board)], dtype=np.int16))[0])
            cat, tb = divmod(sc, _CATBASE)
            base = [0.18, 0.55, 0.80, 0.88, 0.92, 0.94, 0.97, 0.99, 1.0][cat]
            return min(1.0, base + 0.15 * (tb / _CATBASE) * (1 if cat < 8 else 0))
        rs = sorted([c >> 2 for c in hole], reverse=True)
        r = (rs[0] + rs[1]) / 24.0 * 0.6 + 0.15
        if len(set(rs)) < len(rs):
            r += 0.2
        return min(1.0, r)
    except Exception:
        return 0.4


# --------------------------------------------------------------------------------------
# Strategy constants
# --------------------------------------------------------------------------------------
DEBUG = bool(os.environ.get("BOT_DEBUG"))
STREETS_LEFT = {"preflop": 4, "flop": 3, "turn": 2, "river": 1}
F_MIN, F_MAX = 0.5, 1.3
COMMIT_FRAC = 0.55
SB_RAISE_CUT = 0.25  # button raises preflop with the top 75 % of hands (limps the rest)
REF_BETA = {"pre_open": 0.6, "pre_raise": 0.25, "post_bet": 0.35, "post_raise": 0.2}
SIZE_EDGES = (0.45, 0.9, 1.8, 4.0)


def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def size_bucket(ratio):
    for i, e in enumerate(SIZE_EDGES):
        if ratio < e:
            return i
    return len(SIZE_EDGES)


def geo_fraction(pot, eff, n):
    """Pot fraction f so that n bets of f*pot, each called, put the stack `eff` in."""
    if pot <= 0 or eff <= 0:
        return 0.0
    return ((1.0 + 2.0 * eff / pot) ** (1.0 / max(1, n)) - 1.0) / 2.0


def _discard_fallback(cards):
    """The engine's own default: lowest rank; ties broken by suit order s,h,d,c."""
    return min(cards, key=lambda c: (RANKS.index(c[0].upper()), SUITS.index(c[1].lower())))


class Strength:
    __slots__ = ("eq", "hs", "rank")

    def __init__(self, eq, hs, rank):
        self.eq = eq
        self.hs = hs
        self.rank = rank


# --------------------------------------------------------------------------------------
# The bot
# --------------------------------------------------------------------------------------
class Bot:
    def __init__(self):
        seed = os.environ.get("BOT_SEED")
        if seed is not None:
            self.rng = np.random.default_rng(int(seed))
            self.py = random.Random(int(seed))
        else:
            self.rng = np.random.default_rng()
            self.py = random.Random()
        self.total_hands = 400
        self.time_bank_ms = 60000
        self.time_left_ms = 60000
        self.hand_id = 0
        self.seat = "button"
        self.hole = []
        self.board = []
        self.my_disc = None
        self.opp_disc = None
        self.range_frac = 1.0
        self.cache = {}
        self.disc_choice = None
        self.pre_cache = {}
        self.scale = 1.0
        self.cost_ema = None
        self.hand_time = 0.0
        # opponent statistics: node -> [bets, opportunities]; priors are weak
        self.node = {"pre_open": [3.6, 6.0], "pre_raise": [0.9, 6.0],
                     "post_bet": [1.8, 6.0], "post_raise": [0.9, 6.0]}
        self.sizes = {k: [0.5] * 5 for k in self.node}
        self.fold_to_bet = [2.4, 6.4]  # [folds, bets faced] postflop
        self._perms = list(itertools.permutations(range(4)))

    # ---------------------------------------------------------------- message dispatch
    def handle(self, msg):
        t = msg.get("type")
        t0 = time.perf_counter()
        try:
            if t == "init":
                self.on_init(msg)
            elif t == "new_hand":
                self.on_new_hand(msg)
            elif t == "action_request":
                return self.on_action(msg)
            elif t == "discard_request":
                return self.on_discard(msg)
            elif t == "discard_result":
                self.on_discard_result(msg)
            elif t == "hand_result":
                self.on_hand_result(msg)
        finally:
            if t in ("action_request", "discard_request"):
                self.hand_time += time.perf_counter() - t0
        return None

    def on_init(self, m):
        self.total_hands = int(m.get("total_hands", 400) or 400)
        self.time_bank_ms = int(m.get("time_bank_ms", 60000) or 60000)
        self.time_left_ms = self.time_bank_ms

    def on_new_hand(self, m):
        self.hand_id = int(m.get("hand_id", self.hand_id + 1))
        self.seat = m.get("seat", "button")
        self.hole = [c2i(c) for c in m.get("hole_cards", [])]
        self.board = []
        self.my_disc = None
        self.opp_disc = None
        self.range_frac = 1.0
        self.cache = {}
        self.disc_choice = None
        self.hand_time = 0.0

    def on_discard_result(self, m):
        try:
            self.my_disc = c2i(m["my_discard"])
            self.opp_disc = c2i(m["opp_discard"])
            hc = m.get("hole_cards")
            if hc:
                self.hole = [c2i(c) for c in hc]
        except Exception:
            pass

    def on_hand_result(self, m):
        try:
            self.learn(m.get("history", []))
        except Exception:
            pass
        try:
            self.pace()
        except Exception:
            pass

    # ---------------------------------------------------------------- pacing
    def pace(self):
        hands_left = max(1, self.total_hands - self.hand_id)
        avail = self.time_left_ms / 1000.0 / hands_left
        target = 0.35 * avail
        cost = max(self.hand_time, 1e-4)
        self.cost_ema = cost if self.cost_ema is None else 0.8 * self.cost_ema + 0.2 * cost
        ratio = clamp(target / self.cost_ema, 0.6, 1.4)
        self.scale = clamp(self.scale * ratio, 0.12, 2.0)
        if DEBUG and self.hand_id % 20 == 0:
            sys.stderr.write("hand %d scale %.2f cost_ema %.3f target %.3f left %d\n" % (
                self.hand_id, self.scale, self.cost_ema, target, self.time_left_ms))

    def n_for(self, base):
        return max(100, int(base * self.scale))

    def low_time(self):
        """True when simulation is no longer affordable: use the cheap rules."""
        if self.time_left_ms < 1500:
            return True
        hands_left = max(1, self.total_hands - self.hand_id + 1)
        return self.time_left_ms / float(hands_left) < 20.0

    # ---------------------------------------------------------------- history replay
    def replay(self, history):
        """Rebuild per-action context (facing a bet?, chips added, pot before) from history."""
        ev = []
        button_actor = "me" if self.seat == "button" else "opp"
        street = None
        settled = 0
        commit = {"me": 0, "opp": 0}
        nact = 0
        for h in history or []:
            if not isinstance(h, dict):
                continue
            s, actor, act = h.get("street"), h.get("actor"), h.get("action")
            if actor not in ("me", "opp") or act not in ("fold", "check", "call", "raise"):
                continue
            if s != street:
                if street is not None:
                    settled += commit["me"] + commit["opp"]
                street = s
                if s == "preflop":
                    commit = {"me": 1 if button_actor == "me" else 2,
                              "opp": 1 if button_actor == "opp" else 2}
                else:
                    commit = {"me": 0, "opp": 0}
                nact = 0
            other = "opp" if actor == "me" else "me"
            facing = commit[other] > commit[actor]
            pot_before = settled + commit["me"] + commit["opp"]
            is_open = (s == "preflop" and actor == button_actor and nact == 0)
            added = 0
            if act in ("call", "raise"):
                amt = int(h.get("amount", commit[actor]))
                added = max(0, amt - commit[actor])
                commit[actor] = amt
            ev.append({"street": s, "actor": actor, "action": act, "facing": facing,
                       "added": added, "pot_before": pot_before, "open": is_open})
            nact += 1
        return ev

    @staticmethod
    def node_of(e):
        if e["street"] == "preflop":
            return "pre_open" if e["open"] else "pre_raise"
        return "post_raise" if e["facing"] else "post_bet"

    # ---------------------------------------------------------------- opponent learning
    def learn(self, history):
        ev = self.replay(history)
        for i, e in enumerate(ev):
            if e["actor"] == "opp":
                node = self.node_of(e)
                self.node[node][1] += 1.0
                if e["action"] == "raise":
                    self.node[node][0] += 1.0
                    ratio = e["added"] / max(1.0, e["pot_before"])
                    self.sizes[node][size_bucket(ratio)] += 1.0
            elif e["action"] == "raise" and e["street"] != "preflop":
                if i + 1 < len(ev) and ev[i + 1]["actor"] == "opp" and ev[i + 1]["street"] == e["street"]:
                    self.fold_to_bet[1] += 1.0
                    if ev[i + 1]["action"] == "fold":
                        self.fold_to_bet[0] += 1.0

    # ---------------------------------------------------------------- strength
    def canon_key(self, hand):
        best = None
        for p in self._perms:
            key = tuple(sorted(((c >> 2), p[c & 3]) for c in hand))
            if best is None or key < best:
                best = key
        return best

    def strength(self, req, board):
        street = req["street"]
        key = (self.hand_id, street, len(self.hole), len(board))
        if key in self.cache:
            return self.cache[key]
        hole = list(self.hole)
        if self.low_time():
            r = emergency_rank(hole, board)
            res = Strength(r, None, r)
            self.cache[key] = res
            return res
        if street == "preflop" or len(board) == 0:
            ck = self.canon_key(hole)
            if ck in self.pre_cache:
                eq = self.pre_cache[ck]
            else:
                eq = analyze_pre(hole, self.n_for(700), self.rng)
                self.pre_cache[ck] = eq
            res = Strength(eq, None, pre_pct(eq))
        elif len(hole) == 3 and len(board) == 3:
            eqs, hs = analyze_flop_pre(hole, board, self.n_for(900), self.rng)
            eq = max(eqs)
            self.disc_choice = (self.hand_id, tuple(hole), tuple(board), eqs)
            res = Strength(eq, hs, clamp(0.4 * hs + 0.6 * eq, 0.0, 1.0))
        else:
            if len(hole) == 3:  # discard result missed: assume the heuristic keep
                fl = np.array([board[:3]], dtype=np.int16)
                v = keep_values(np.array([hole], dtype=np.int16), fl)[0]
                hole = [hole[i] for i in range(3) if i != int(np.argmax(v))]
            eq, hs = analyze_post(hole, board, self.opp_disc, self.n_for(1100), self.rng, self.my_disc)
            res = Strength(eq, hs, clamp(0.4 * hs + 0.6 * eq, 0.0, 1.0))
        self.cache[key] = res
        return res

    # ---------------------------------------------------------------- sizing
    def plan_raise(self, req):
        """Geometric raise: returns (raise_to, extra_over_call, pot_after_call) or None."""
        c = req["to_call"]
        pot2 = req["pot"] + c
        eff2 = min(req["my_stack"] - c, req["opp_stack"])
        if eff2 <= 0 or "raise" not in req["legal_actions"]:
            return None
        n = STREETS_LEFT.get(req["street"], 1)
        f = clamp(geo_fraction(pot2, eff2, n), F_MIN, F_MAX)
        extra = f * pot2
        if extra >= COMMIT_FRAC * eff2:
            extra = eff2
        lo = int(req.get("min_raise", 0))
        hi = int(req.get("max_raise", lo))
        amount = int(round(req["opp_bet"] + extra))
        amount = max(lo, min(hi, amount))
        extra_real = max(1, amount - req["opp_bet"])
        return amount, extra_real, pot2

    def bet_multipliers(self, B, pot2):
        alpha = B / float(pot2 + B)
        fold_est = self.fold_to_bet[0] / self.fold_to_bet[1]
        bluffmult = clamp(fold_est / max(alpha, 1e-6), 0.35, 2.0)
        valmult = clamp(1.0 + 0.8 * (alpha - fold_est), 0.85, 1.4)
        return alpha, bluffmult, valmult

    # ---------------------------------------------------------------- decisions
    def on_action(self, req):
        try:
            self.time_left_ms = int(req.get("time_left_ms", self.time_left_ms))
        except Exception:
            pass
        try:
            action, amount = self.decide(req)
        except Exception as exc:  # never let anything escape
            sys.stderr.write("decide error: %r\n" % (exc,))
            action, amount = self.safe_action(req)
        return self.finalize(req, action, amount)

    def safe_action(self, req):
        legal = req.get("legal_actions", [])
        if "check" in legal:
            return "check", None
        c = req.get("to_call", 0)
        if "call" in legal and c <= max(2, 0.12 * req.get("pot", 0)):
            return "call", None
        if "fold" in legal:
            return "fold", None
        return legal[0] if legal else "check", None

    def finalize(self, req, action, amount):
        legal = req.get("legal_actions", [])
        if action == "raise":
            if "raise" in legal and amount is not None:
                lo = int(req.get("min_raise", amount))
                hi = int(req.get("max_raise", amount))
                if hi < lo:
                    lo = hi
                amt = max(lo, min(hi, int(amount)))
                return {"type": "action", "action": "raise", "amount": amt}
            action = "call" if "call" in legal else "check"
        if action == "call" and "call" not in legal:
            action = "check" if "check" in legal else "fold"
        if action == "check" and "check" not in legal:
            action = "fold" if "fold" in legal else ("call" if "call" in legal else "check")
        if action == "fold" and "fold" not in legal:
            action = "check" if "check" in legal else "call"
        return {"type": "action", "action": action}

    def decide(self, req):
        legal = req["legal_actions"]
        street = req["street"]
        board = [c2i(c) for c in req.get("board", [])]
        self.board = board
        if not self.hole:
            return self.safe_action(req)
        c = req["to_call"]
        ev = self.replay(req.get("history", []))
        cur = [e for e in ev if e["street"] == street]
        st = self.strength(req, board)

        # preflop, button, first action: raise (geometric open) or complete the blind
        if street == "preflop" and self.seat == "button" and not cur and c > 0:
            if "raise" in legal and st.rank >= SB_RAISE_CUT:
                plan = self.plan_raise(req)
                if plan is not None:
                    self.range_frac = min(self.range_frac, 1.0 - SB_RAISE_CUT)
                    return "raise", plan[0]
            return "call", None

        if c == 0:
            return self.decide_open(req, st, cur)
        return self.decide_facing(req, st, cur)

    def decide_open(self, req, st, cur):
        """No bet to face: polarised geometric bet or check."""
        plan = self.plan_raise(req)
        if plan is None:
            return "check", None
        amount, B, pot2 = plan
        street = req["street"]
        mdf = pot2 / float(pot2 + B)
        alpha, bluffmult, valmult = self.bet_multipliers(B, pot2)
        v = 0.5 * mdf * valmult  # fraction of the range that bets for value
        value_cut = 1.0 - v
        bluff_total = v * alpha * bluffmult  # bluffs : value = B : (P + B)
        rank = st.rank
        if rank >= value_cut:
            if street in ("flop", "turn") and rank >= 0.93 and self.py.random() < 0.12:
                return "check", None  # a little slow-play protects the checking range
            return "raise", amount
        weak = st.hs if st.hs is not None else rank
        draw = max(0.0, (st.eq - st.hs) if st.hs is not None else 0.0)
        bl_cut = min(0.45, bluff_total + 0.6 * max(0.0, draw - 0.03))
        if weak < bl_cut and self.py.random() < 0.9:
            return "raise", amount
        return "check", None

    def decide_facing(self, req, st, cur):
        legal = req["legal_actions"]
        street = req["street"]
        c = req["to_call"]
        pot = req["pot"]
        last = None
        for e in reversed(cur):
            if e["actor"] == "opp" and e["action"] == "raise":
                last = e
                break
        if last is not None and 0 < last["added"] <= pot:
            added = last["added"]
            node = self.node_of(last)
        else:
            added = c
            node = "pre_raise" if street == "preflop" else "post_bet"
        pot_before = max(1, pot - added)
        mdf = pot_before / float(pot_before + added)
        bets, opps = self.node[node]
        beta_node = bets / opps
        sz = self.sizes[node]
        share = sz[size_bucket(added / float(pot_before))] / sum(sz)
        beta_b = beta_node * share
        req_eq = c / float(pot + c)
        tight = 1.0
        if opps >= 30 and beta_node < REF_BETA[node]:
            tight = clamp(math.sqrt(beta_node / REF_BETA[node]), 0.7, 1.0)
        df_mdf = mdf * tight * (0.5 + 0.5 * self.range_frac)
        df_obs = beta_b * (1.0 - req_eq)
        thresh = 1.0 - max(df_mdf, df_obs)
        rank = st.rank

        # raising: value (top of the continuing range) and polarising bluffs
        if "raise" in legal:
            plan = self.plan_raise(req)
            if plan is not None:
                amount, B, pot2 = plan
                my_raises = sum(1 for e in cur if e["actor"] == "me" and e["action"] == "raise")
                m = pot2 / float(pot2 + B)
                alpha, bluffmult, valmult = self.bet_multipliers(B, pot2)
                cont = max(0.0, 1.0 - thresh)
                v = 0.5 * m * cont * valmult
                cut = 1.0 - v
                if rank >= cut and rank >= 0.7:
                    return "raise", amount
                if my_raises == 0 and req.get("raises_left", 0) >= 2 and rank < thresh:
                    weak = st.hs if st.hs is not None else rank
                    draw = max(0.0, (st.eq - st.hs) if st.hs is not None else 0.0)
                    bl_cut = v * alpha * bluffmult + 0.4 * max(0.0, draw - 0.05)
                    if weak < min(0.3, bl_cut) and self.py.random() < 0.8:
                        return "raise", amount
        if rank >= thresh:
            self.range_frac = min(self.range_frac, max(0.05, 1.0 - thresh))
            return "call", None
        return "fold", None

    # ---------------------------------------------------------------- discard
    def on_discard(self, req):
        try:
            self.time_left_ms = int(req.get("time_left_ms", self.time_left_ms))
        except Exception:
            pass
        cards = req.get("hole_cards", [])
        try:
            card = self.choose_discard(req)
        except Exception as exc:
            sys.stderr.write("discard error: %r\n" % (exc,))
            card = None
        if card not in cards:
            card = _discard_fallback(cards)
        try:
            ci = c2i(card)
            self.my_disc = ci
            self.hole = [c2i(c) for c in cards if c != card]
        except Exception:
            pass
        return {"type": "discard", "card": card}

    def choose_discard(self, req):
        cards = req["hole_cards"]
        hole = [c2i(c) for c in cards]
        board = [c2i(c) for c in req.get("board", [])]
        if len(hole) != 3:
            return _discard_fallback(cards)
        eqs = None
        dc = self.disc_choice
        if dc is not None and dc[0] == self.hand_id and dc[1] == tuple(hole) and dc[2] == tuple(board):
            eqs = dc[3]
        elif self.low_time() or len(board) != 3:
            fl = np.array([board[:3]] * 1, dtype=np.int16)
            v = keep_values(np.array([hole], dtype=np.int16), fl)[0]
            eqs = list(v)
        else:
            eqs, _ = analyze_flop_pre(hole, board, self.n_for(1100), self.rng)
        best, bj = None, 0
        for j in range(3):
            score = eqs[j] + 1e-4 * (12 - (hole[j] >> 2))  # tie-break: throw the lower card
            if best is None or score > best:
                best, bj = score, j
        return cards[bj]


# --------------------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------------------
def main():
    out = sys.stdout
    sys.stdout = sys.stderr  # stray prints can never corrupt the protocol stream

    def send(obj):
        out.write(json.dumps(obj, separators=(",", ":")) + "\n")
        out.flush()

    bot = Bot()
    # warm-up (table builds are already done at import): keeps the first hand fast
    try:
        evaluate(np.array([[0, 5, 10, 15, 20, 25, 30]], dtype=np.int16))
        analyze_pre([0, 5, 10], 120, bot.rng)
    except Exception:
        pass

    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            break
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        t = msg.get("type")
        if t == "match_end":
            break
        try:
            reply = bot.handle(msg)
        except Exception as exc:
            sys.stderr.write("handler error: %r\n" % (exc,))
            reply = None
            if t == "action_request":
                try:
                    a, amt = bot.safe_action(msg)
                    reply = bot.finalize(msg, a, amt)
                except Exception:
                    reply = {"type": "action", "action": "check"}
            elif t == "discard_request":
                try:
                    reply = {"type": "discard", "card": _discard_fallback(msg["hole_cards"])}
                except Exception:
                    reply = None
        if reply is not None:
            try:
                send(reply)
            except Exception:
                break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass

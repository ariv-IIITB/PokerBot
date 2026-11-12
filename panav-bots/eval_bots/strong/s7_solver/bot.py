"""s7_solver: equity-vs-range play before the river, a small online river solver on the river.

River: build the betting tree of the street (own bet sizes, caps), track both ranges as weights over all 2-card hands
(prior from earlier actions and the exposed discards), bucket the hands by showdown strength, and run vector CFR+ in
numpy for as long as the time budget allows. The actions already taken on the river are walked through the tree, so
the opponent's range is conditioned on them by the solved strategy itself. Hero's strategy at the current node is
read for the exact hand held (a singleton bucket) and sampled.
Cards: c = rank * 4 + suit.
"""
import os
import sys
import time

for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = "1"
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BaseBot, run, score, card_to_int, log  # noqa: E402

BUDGET = 0.024            # seconds of CFR per river decision
NB = 40                   # strength buckets
BET_FRACS = (0.5, 1.0)
RAISE_FRACS = (0.8,)


class Nd:
    __slots__ = ("actor", "cH", "cV", "raises", "term", "pay", "kids", "idx", "depth", "parent", "kind", "amt")

    def __init__(self):
        self.kids = []
        self.term = None
        self.pay = 0.0


class Solver:
    """One river subgame. Player 0 = hero, player 1 = villain."""

    def __init__(self, P, S, first_actor, path):
        self.P = float(P)                 # pot before the street
        self.S = int(S)                   # effective stack at street start (all-in total)
        self.path = path                  # list of (actor, action, amount) already played on this street
        self.cur = None
        self.root = self.build(first_actor, 0, 0, 0, True, 0, 0)

    def terminal(self, kind, cH, cV, folder=None):
        n = Nd()
        n.term = kind
        n.cH, n.cV = cH, cV
        if kind == "f":
            n.pay = -(self.P / 2 + cH) if folder == 0 else (self.P / 2 + cV)
        else:
            n.pay = self.P / 2 + cH
        return n

    def raise_targets(self, mine, oth, raises, extra):
        S = self.S
        if S <= oth:
            return []
        pot_after = self.P + 2 * oth
        if raises == 0:
            fr = BET_FRACS
        elif raises == 1:
            fr = RAISE_FRACS
        else:
            fr = ()
        minr = min(S, oth + max(oth - mine, 2))
        t = []
        for f in fr:
            a = int(round(oth + f * pot_after))
            a = max(a, minr)
            if a >= 0.62 * S or S - a <= 4:
                a = S
            t.append(a)
        t.append(S)
        t = sorted(set(t))
        if extra is not None:
            t = [a for a in t if abs(a - extra) > max(1, 0.06 * extra)]
            t.append(extra)
            t = sorted(set(t))
        return t

    def build(self, actor, cH, cV, raises, first, pos, depth):
        n = Nd()
        n.actor, n.cH, n.cV, n.raises, n.depth = actor, cH, cV, raises, depth
        c = [cH, cV]
        mine, oth = c[actor], c[1 - actor]
        tocall = oth - mine
        on_path = pos is not None and pos < len(self.path)
        if pos is not None and pos == len(self.path):
            self.cur = n
        want = None
        extra = None
        if on_path:
            who, act, amt = self.path[pos]
            if who != actor:
                raise ValueError("actor mismatch")
            want = act
            if act == "raise":
                extra = int(amt)
        np_ = (pos + 1) if on_path else None

        def sub(a_kind):
            return np_ if (on_path and want == a_kind) else None

        if tocall > 0:
            n.kids.append(("fold", 0, self.terminal("f", cH, cV, folder=actor)))
            n.kids.append(("call", oth, self.terminal("s", oth, oth)))
        else:
            if first:
                n.kids.append(("check", 0, self.build(1 - actor, cH, cV, raises, False, sub("check"), depth + 1)))
            else:
                n.kids.append(("check", 0, self.terminal("s", mine, mine)))
        if raises < 4:
            for a in self.raise_targets(mine, oth, raises, extra):
                nc = [cH, cV]
                nc[actor] = a
                if on_path and want == "raise" and a == extra:
                    p2 = np_
                else:
                    p2 = None
                if a >= self.S and True:
                    # all-in: the other side can only fold or call
                    pass
                n.kids.append(("raise", a, self.build(1 - actor, nc[0], nc[1], raises + 1, False, p2, depth + 1)))
        return n

    # ---------------------------------------------------------------- flatten
    def flatten(self):
        order = [self.root]
        self.root.depth = 0
        i = 0
        while i < len(order):
            nd = order[i]
            i += 1
            for kind, amt, ch in nd.kids:
                ch.parent = nd
                ch.kind = kind
                ch.amt = amt
                order.append(ch)
        # kids contiguous per parent in BFS order; depth levels contiguous
        for k, nd in enumerate(order):
            nd.idx = k
        self.nodes = order
        N = len(order)
        self.N = N
        par = np.zeros(N, dtype=np.int64)
        actH = np.zeros(N, dtype=bool)         # parent is a hero node (edge acts for hero)
        depth = np.zeros(N, dtype=np.int64)
        for nd in order[1:]:
            par[nd.idx] = nd.parent.idx
            actH[nd.idx] = nd.parent.actor == 0
            depth[nd.idx] = nd.parent.depth + 1
            nd.depth = depth[nd.idx]
        self.par = par[1:]
        self.aH = actH[1:, None].astype(np.float64)       # per edge (child idx - 1)
        self.aV = 1.0 - self.aH
        E = N - 1
        self.E = E
        # segments (parents with kids)
        starts = [0]
        for e in range(1, E):
            if self.par[e] != self.par[e - 1]:
                starts.append(e)
        self.starts = np.array(starts, dtype=np.int64)
        cnt = np.diff(np.append(self.starts, E))
        self.cnt = cnt
        self.cntrep = np.repeat(cnt, cnt).astype(np.float64)[:, None]
        # levels: edges (child indices) by depth
        self.levels = []
        maxd = int(depth.max())
        for d in range(1, maxd + 1):
            ids = np.nonzero(depth == d)[0]
            lo, hi = int(ids[0]), int(ids[-1]) + 1
            pl = par[lo:hi]
            st = [0]
            for e in range(1, hi - lo):
                if pl[e] != pl[e - 1]:
                    st.append(e)
            st = np.array(st, dtype=np.int64)
            self.levels.append((lo, hi, pl, st, pl[st]))
        sd = [nd for nd in order if nd.term == "s"]
        fd = [nd for nd in order if nd.term == "f"]
        self.sd = np.array([nd.idx for nd in sd], dtype=np.int64)
        self.sd_s = np.array([nd.pay for nd in sd])[:, None]
        self.fd = np.array([nd.idx for nd in fd], dtype=np.int64)
        self.fd_p = np.array([nd.pay for nd in fd])[:, None]

    def solve(self, massH, massV, W, t_end, min_it=30, max_it=800):
        """massH, massV: root reach (K,), W (K,K) average showdown sign hero-bucket vs villain-bucket."""
        self.flatten()
        N, E = self.N, self.E
        K = len(massH)
        Rg = np.zeros((E, K))
        SS = np.zeros((E, K))
        reachH = np.zeros((N, K))
        reachV = np.zeros((N, K))
        cfvH = np.zeros((N, K))
        cfvV = np.zeros((N, K))
        reachH[0] = massH
        reachV[0] = massV
        WT = W.T.copy()
        starts, cntrep, par, aH, aV = self.starts, self.cntrep, self.par, self.aH, self.aV
        sd, fd = self.sd, self.fd
        it = 0
        perf = time.perf_counter
        while True:
            it += 1
            if it >= max_it or (it >= min_it and perf() > t_end):
                break
            den = np.add.reduceat(Rg, starts, axis=0)
            den = np.repeat(den, self.cnt, axis=0)
            sig = np.where(den > 1e-12, Rg / np.maximum(den, 1e-12), 1.0 / cntrep)
            mH = aH * sig + (1.0 - aH)
            mV = aV * sig + (1.0 - aV)
            for lo, hi, pl, st, up in self.levels:
                reachH[lo:hi] = reachH[pl] * mH[lo - 1:hi - 1]
                reachV[lo:hi] = reachV[pl] * mV[lo - 1:hi - 1]
            # terminals
            if len(sd):
                cfvH[sd] = self.sd_s * (reachV[sd] @ WT)
                cfvV[sd] = -self.sd_s * (reachH[sd] @ W)
            if len(fd):
                cfvH[fd] = self.fd_p * reachV[fd].sum(1, keepdims=True)
                cfvV[fd] = -self.fd_p * reachH[fd].sum(1, keepdims=True)
            for lo, hi, pl, st, up in reversed(self.levels):
                vH = (aH[lo - 1:hi - 1] * sig[lo - 1:hi - 1] + (1.0 - aH[lo - 1:hi - 1])) * cfvH[lo:hi]
                vV = (aV[lo - 1:hi - 1] * sig[lo - 1:hi - 1] + (1.0 - aV[lo - 1:hi - 1])) * cfvV[lo:hi]
                cfvH[up] = np.add.reduceat(vH, st, axis=0)
                cfvV[up] = np.add.reduceat(vV, st, axis=0)
            incH = cfvH[1:] - cfvH[par]
            incV = cfvV[1:] - cfvV[par]
            Rg = np.maximum(Rg + aH * incH + aV * incV, 0.0)
            ra = aH * reachH[par] + aV * reachV[par]
            SS += it * ra * sig
            # note: strategy used this iteration was sig (computed from Rg before the update)
        self.iters = it
        den = np.add.reduceat(SS, starts, axis=0)
        den = np.repeat(den, self.cnt, axis=0)
        self.avg = np.where(den > 1e-12, SS / np.maximum(den, 1e-12), 1.0 / cntrep)
        return self.avg


# ---------------------------------------------------------------- the bot
class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self._rv_key = None
        self._rv = None
        self.tmax = 0.0
        self.tsum = 0.0
        self.tn = 0
        self.skip = 0

    def on_new_hand(self, msg):
        super().on_new_hand(msg)
        self._rv_key = None

    # prior narrowing of one player's range from the actions taken before the river
    def prior_p(self, req, who):
        p = 0.0
        for e in req.get("history", []):
            if e.get("actor") != who or e.get("street") == "river":
                continue
            a, s = e.get("action"), e.get("street")
            if s == "preflop":
                if a == "raise":
                    p += 0.25
            elif a == "raise":
                p += 0.55 if s == "flop" else 0.8
            elif a == "call":
                p += 0.2
            elif a == "check":
                p -= 0.1
        if who == "opp":
            agg = (0.30 / max(0.10, self.opp.bet_rate)) ** 0.6
            p *= min(1.3, max(0.45, agg))
        return max(0.0, min(4.0, p))

    def universe(self, req):
        dead = set(self.board) | ({self.my_discard} if self.my_discard is not None else set()) \
            | ({self.opp_discard} if self.opp_discard is not None else set())
        return [c for c in range(52) if c not in dead]

    def hands_data(self, req):
        key = (tuple(self.board), tuple(self.hole), self.my_discard, self.opp_discard)
        if self._rv_key == key:
            return self._rv
        cards = self.universe(req)
        n = len(cards)
        ia, ib = np.triu_indices(n, 1)
        ca = np.array(cards)[ia]
        cb = np.array(cards)[ib]
        board = self.board
        flop = board[:3]
        sc = np.array([score([int(a), int(b)] + board) for a, b in zip(ca, cb)], dtype=np.int64)
        cons_o = np.ones(len(ca))
        cons_m = np.ones(len(ca))
        if len(flop) == 3:
            fs = np.array([score([int(a), int(b)] + flop) for a, b in zip(ca, cb)], dtype=np.int64)
            for d, cons in ((self.opp_discard, cons_o), (self.my_discard, cons_m)):
                if d is None:
                    continue
                pc = {c: score([c, d] + flop) for c in cards}
                alt = np.maximum(np.array([pc[int(a)] for a in ca]), np.array([pc[int(b)] for b in cb]))
                cons[alt > fs] = 0.25
        self._rv_key = key
        self._rv = (ca, cb, sc, cons_o, cons_m)
        return self._rv

    def river(self, req):
        t0 = time.perf_counter()
        ca, cb, sc, cons_o, cons_m = self.hands_data(req)
        H = len(ca)
        hole = self.hole
        hmask_cards = set(hole)
        # percentile strength
        srt = np.sort(sc)
        u = (np.searchsorted(srt, sc, "left") + np.searchsorted(srt, sc, "right")) / (2.0 * H)
        po, pm = self.prior_p(req, "opp"), self.prior_p(req, "me")
        wo = (0.03 + u ** po) * cons_o
        wm = (0.03 + u ** pm) * cons_m
        blocked = np.isin(ca, list(hmask_cards)) | np.isin(cb, list(hmask_cards))
        wo = np.where(blocked, 0.0, wo)
        hh = int(np.nonzero((np.isin(ca, hole)) & (np.isin(cb, hole)))[0][0])
        wm[hh] = 0.0
        wo /= wo.sum()
        wm /= wm.sum()
        # buckets: equal combined mass along strength order
        order = np.argsort(sc, kind="stable")
        mass = 0.5 * (wo + wm)
        cum = np.cumsum(mass[order]) - 0.5 * mass[order]
        bsorted = np.minimum((cum * NB).astype(np.int64), NB - 1)
        bucket = np.empty(H, dtype=np.int64)
        bucket[order] = bsorted
        Po = np.zeros((H, NB))
        Pm = np.zeros((H, NB))
        Po[np.arange(H), bucket] = wo
        Pm[np.arange(H), bucket] = wm
        mo = Po.sum(0)
        mm = Pm.sum(0)
        # win minus loss against the villain weights, by hand, summed per villain bucket
        Po_s = Po[order]
        pref = np.vstack([np.zeros((1, NB)), np.cumsum(Po_s, axis=0)])
        ssc = sc[order]
        left = np.searchsorted(ssc, sc, "left")
        right = np.searchsorted(ssc, sc, "right")
        tot = pref[-1]
        G = pref[left] - (tot - pref[right])           # (H, NB): sum over villain hands of sign(mine - theirs) * w
        Nn = Pm.T @ G                                  # (NB, NB)
        D = np.outer(mm, mo)
        Wb = np.where(D > 1e-15, Nn / np.maximum(D, 1e-15), 0.0)
        K = NB + 1
        W = np.zeros((K, K))
        W[:NB, :NB] = Wb
        W[NB, :NB] = np.where(mo > 1e-12, G[hh] / np.maximum(mo, 1e-12), 0.0)
        W[:NB, NB] = 0.0
        massH = np.zeros(K)
        massV = np.zeros(K)
        massH[:NB] = mm
        massH[NB] = 1.0 / NB
        massV[:NB] = mo
        # tree
        hist = [e for e in req.get("history", []) if e.get("street") == "river"]
        path = [(0 if e["actor"] == "me" else 1, e["action"], e.get("amount")) for e in hist
                if e["action"] in ("check", "call", "raise", "fold")]
        P = req["pot"] - req["my_bet"] - req["opp_bet"]
        S = min(req["my_stack"] + req["my_bet"], req["opp_stack"] + req["opp_bet"])
        first = 0 if self.seat == "big_blind" else 1
        sv = Solver(P, S, first, path)
        if sv.cur is None or sv.cur.actor != 0:
            raise ValueError("no hero node")
        used = time.perf_counter() - t0
        avg = sv.solve(massH, massV, W, time.perf_counter() + max(0.006, BUDGET - used * 0.3))
        kids = sv.cur.kids
        probs = np.array([avg[ch.idx - 1, NB] for _, _, ch in kids])
        probs = np.where(probs < 0.04, 0.0, probs)
        if probs.sum() <= 0:
            probs = np.array([avg[ch.idx - 1, NB] for _, _, ch in kids])
        probs = probs / probs.sum()
        r = self.rng.random()
        acc = 0.0
        pick = len(kids) - 1
        for i, p in enumerate(probs):
            acc += p
            if r < acc:
                pick = i
                break
        kind, amt, _ = kids[pick]
        self.last_info = (sv.iters, [(k, a, round(float(p), 2)) for (k, a, _), p in zip(kids, probs)])
        if kind == "raise":
            return ("raise", amt)
        return kind

    def postflop(self, req, P):
        if req["street"] == "river" and len(self.board) == 5 and len(self.hole) == 2:
            t0 = time.perf_counter()
            try:
                d = self.river(req)
                dt = time.perf_counter() - t0
                self.tmax = max(self.tmax, dt)
                self.tsum += dt
                self.tn += 1
                return d
            except Exception as exc:
                self.skip += 1
                log("river solver error:", repr(exc))
        return super().postflop(req, P)


if __name__ == "__main__":
    run(Bot)

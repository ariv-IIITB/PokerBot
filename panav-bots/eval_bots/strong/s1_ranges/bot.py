"""s1_ranges: Bayesian range tracker for Discard Hold'em heads-up.

Keeps a weight for every hand the opponent could hold (all 22,100 three-card hands preflop; sampled three-card
particles on the flop; every two-card kept pair after the exposed discard), updates it after each opponent action with
an action-likelihood model (fold / call / raise as a function of the hand's percentile inside the current range, with
the fold and raise rates and the bluff share learned per opponent), and decides by expected value against the tracked
range, including the opponent's modelled reaction to each bet size.
Built from this file by build.py (the preflop table is embedded). Python 3.11 + numpy, stdlib only.
"""
import base64
import json
import os
import random
import sys
import time
import zlib

import numpy as np

RANKS = "23456789TJQKA"
SUITS = "shdc"


def c2i(s):
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])


def i2c(c):
    return RANKS[c >> 2] + SUITS[c & 3]


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ vectorised evaluator
AR13 = np.arange(13)
POP = np.array([bin(m).count("1") for m in range(8192)], dtype=np.int16)
STRT = np.full(8192, -1, dtype=np.int16)
for _m in range(8192):
    for _top in range(12, 3, -1):
        _need = 31 << (_top - 4)
        if _m & _need == _need:
            STRT[_m] = _top
            break
    else:
        if _m & 0x100F == 0x100F:
            STRT[_m] = 3
_NSIG = np.array([5, 4, 3, 3, 0, 0, 2, 2, 0])          # significant ranks per category (non-flush ordering)
_SHIFT = np.array([16, 12, 8, 4, 0])


def evalv(C):
    """Scores of N hands of 5-7 cards (array N x k of card ints); bigger is better."""
    N, k = C.shape
    r = C >> 2
    s = C & 3
    one = (1 << r)
    rc = np.zeros((N, 13), dtype=np.int16)
    for j in range(k):
        rc[np.arange(N), r[:, j]] += 1
    allm = ((rc > 0) * (1 << AR13)).sum(1)
    sm = np.stack([np.bitwise_or.reduce(np.where(s == j, one, 0), axis=1) for j in range(4)], axis=1)
    pc = POP[sm]
    isfl = pc.max(1) >= 5
    fm = sm[np.arange(N), pc.argmax(1)]
    key = np.where(rc > 0, rc * 16 + AR13, -1)
    kk = -np.sort(-key, axis=1)[:, :5]
    ranks = np.where(kk >= 0, kk & 15, 0)
    cnt = np.where(kk >= 0, kk >> 4, 0)
    n1, n2 = cnt[:, 0], cnt[:, 1]
    cat = np.zeros(N, dtype=np.int64)
    cat = np.where(n1 == 2, 1, cat)
    cat = np.where((n1 == 2) & (n2 == 2), 2, cat)
    cat = np.where(n1 == 3, 3, cat)
    cat = np.where((n1 == 3) & (n2 >= 2), 6, cat)
    cat = np.where(n1 == 4, 7, cat)
    nsig = _NSIG[cat]
    mask = (np.arange(5)[None, :] < nsig[:, None])
    packed = (ranks * mask * (1 << _SHIFT)[None, :]).sum(1)
    sc = (cat << 20) | packed
    st = STRT[allm]
    sc = np.where((st >= 0) & (cat < 4), (4 << 20) | st, sc)
    if isfl.any():
        fk = np.where(((fm[:, None] >> AR13) & 1) > 0, AR13, -1)
        fr = -np.sort(-fk, axis=1)[:, :5]
        fpack = (np.where(fr >= 0, fr, 0) * (1 << _SHIFT)[None, :]).sum(1)
        sc = np.where(isfl & (cat < 5), (5 << 20) | fpack, sc)
        sf = STRT[fm]
        sc = np.where(isfl & (sf >= 0), (8 << 20) | sf, sc)
    return sc


def draw_flag(H, board):
    """H: N x 2 kept pairs; flush draw (4 to a suit using a hole card) or straight draw (4 of 5 in a window using a
    hole card), as a bool array."""
    N = H.shape[0]
    b = np.array(board, dtype=np.int64)
    out = np.zeros(N, dtype=bool)
    hs = H & 3
    bs = b & 3
    for j in range(4):
        nb = int((bs == j).sum())
        nh = (hs == j).sum(1)
        out |= (nh >= 1) & (nb + nh == 4)
    bm = 0
    for c in board:
        bm |= 1 << (c >> 2)
    hm = (1 << (H[:, 0] >> 2)) | (1 << (H[:, 1] >> 2))
    allm = hm | bm
    for top in range(3, 13):
        win = (31 << (top - 4)) if top >= 4 else 0x100F
        got = allm & win
        out |= (POP[got] == 4) & ((hm & win) != 0)
    return out


def keys2(H, board, draws=True):
    """Strength keys of N kept pairs on a board (3-5 cards)."""
    N = H.shape[0]
    C = np.concatenate([H, np.broadcast_to(np.array(board, dtype=np.int64), (N, len(board)))], axis=1)
    sc = evalv(C)
    if draws and len(board) < 5:
        d = draw_flag(H, board)
        sc = np.where(d & (sc < (4 << 20)), sc + (1 << 19), sc)
    return sc


def keys3(T, board):
    """Best keep key of N three-card hands on a flop; also returns the three keep keys."""
    ks = []
    for a, b in ((0, 1), (0, 2), (1, 2)):
        ks.append(keys2(T[:, [a, b]], board))
    ks = np.stack(ks, axis=1)
    return ks.max(1), ks


# ------------------------------------------------------------------ preflop table (embedded)
_PRE_B64 = "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"
_arr = np.frombuffer(zlib.decompress(base64.b64decode(_PRE_B64)), dtype=np.uint16).reshape(-1, 2)
E3 = _arr[:, 0].astype(np.float64) / 1000.0
PCT3 = _arr[:, 1].astype(np.float64) / 1000.0
_cl = []
for _a in range(52):
    for _b in range(_a + 1, 52):
        for _c in range(_b + 1, 52):
            _cl.append((_a, _b, _c))
TC3 = np.array(_cl, dtype=np.int64)
IDX3 = np.full((52, 52, 52), -1, dtype=np.int32)
IDX3[TC3[:, 0], TC3[:, 1], TC3[:, 2]] = np.arange(len(TC3))
LOGIT3 = np.log(np.clip(E3, 0.02, 0.98) / (1 - np.clip(E3, 0.02, 0.98)))
_PAIRS = np.array([(a, b) for a in range(52) for b in range(a + 1, 52)], dtype=np.int64)


def sig(x):
    return 1.0 / (1.0 + np.exp(-x))


# ------------------------------------------------------------------ likelihood model
def snap(keys, w):
    o = np.argsort(keys, kind="stable")
    cw = np.concatenate(([0.0], np.cumsum(w[o])))
    tot = cw[-1]
    if tot <= 0:
        cw = np.linspace(0.0, 1.0, len(cw))
    else:
        cw = cw / tot
    return keys[o], cw


def u_from(sn, keys):
    sk, cw = sn
    l = np.searchsorted(sk, keys, "left")
    r = np.searchsorted(sk, keys, "right")
    return 0.5 * (cw[l] + cw[r])


def gsize(f):
    if f is None:
        return 1.0
    return min(1.8, max(0.5, (0.7 / (0.2 + max(0.0, f))) ** 0.6))


def lik(u, pf, pr, beta, f=None):
    """Probabilities (fold, call, raise) of a hand at percentile u in its range."""
    pr_e = min(0.92, max(0.01, pr * gsize(f)))
    pv = pr_e * (1 - beta)
    pb = pr_e * beta
    V = sig((u - (1 - pv)) / 0.05)
    B = min(1.0, pb / 0.5) * (1 - sig((u - 0.5) / 0.06))
    PR = np.clip(V + B, 0.0, 1.0)
    xf = min(0.95, pf / max(0.05, 1 - pr_e))
    FF = 1 - sig((u - xf) / 0.05)
    return (1 - PR) * FF, (1 - PR) * (1 - FF), PR


def floor(L):
    return 0.02 + 0.98 * L


def bucket(f):
    return 0 if f < 0.45 else 1 if f < 0.9 else 2


PRIORS = {}


def prior(key):
    if key[0] == "p":
        nr, fc = key[1], key[2]
        if nr == 0:
            return (0.12, 0.28, 0.60) if fc else (0.0, 0.62, 0.38)
        if nr == 1:
            return (0.38, 0.47, 0.15)
        if nr == 2:
            return (0.35, 0.45, 0.20)
        return (0.35, 0.55, 0.10)
    st, nr, b = key
    if nr == 0:
        return (0.0, 0.62, 0.38) if st == "flop" else (0.0, 0.66, 0.34)
    if nr == 1:
        return ((0.20, 0.72, 0.08), (0.34, 0.58, 0.08), (0.48, 0.45, 0.07))[b]
    return (0.40, 0.50, 0.10)


class Stats:
    def __init__(self):
        self.n = {}
        self.shown = {"flop": [0.0, 0], "turn": [0.0, 0], "river": [0.0, 0]}
        self.best_n = [0, 0]          # [kept best, total]
        self.hands = 0

    def add(self, key, action):
        v = self.n.setdefault(key, [0, 0, 0])
        v[0 if action == "fold" else 2 if action == "raise" else 1] += 1

    def probs(self, key, m=6.0):
        p = prior(key)
        v = self.n.get(key, (0, 0, 0))
        t = float(sum(v))
        return tuple((v[i] + m * p[i]) / (t + m) for i in range(3))

    def beta(self, st):
        s, n = self.shown[st]
        ev = 0.925
        mp = 0.8 * ev + 0.2 * 0.25
        m = (s + 3.0 * mp) / (n + 3.0)
        return min(0.6, max(0.02, (ev - m) / (ev - 0.25)))

    def pbest(self):
        return (self.best_n[0] + 0.85 * 6.0) / (self.best_n[1] + 6.0)


def walk(history, seat):
    lev = {"me": 1, "opp": 2} if seat == "button" else {"me": 2, "opp": 1}
    com = dict(lev)
    street = None
    nr = 0
    out = []
    for i, e in enumerate(history or []):
        st, who, a = e.get("street"), e.get("actor"), e.get("action")
        amt = e.get("amount") or 0
        oth = "opp" if who == "me" else "me"
        if st != street:
            street = st
            nr = 0
            if st != "preflop":
                lev = {"me": 0, "opp": 0}
        pot = com["me"] + com["opp"]
        tc = lev[oth] - lev[who]
        f = None
        fb = None
        if tc > 0 and st != "preflop":
            fb = tc / max(1.0, pot - tc)
        if a == "raise":
            f = amt / max(1.0, pot) if lev[oth] == 0 else (amt - lev[oth]) / max(1.0, pot + tc)
        out.append(dict(i=i, street=st, actor=who, action=a, pot=pot, tc=tc, nr=nr, f=f, fb=fb, amt=amt))
        if a == "raise":
            com[who] += amt - lev[who]
            lev[who] = amt
            nr += 1
        elif a == "call":
            com[who] += tc
            lev[who] = lev[oth]
    return out


def ctx_key(rec):
    st = rec["street"]
    if st == "preflop":
        return ("p", min(rec["nr"], 3), 1 if rec["tc"] > 0 else 0)
    nr = min(rec["nr"], 2)
    return (st, nr, bucket(rec["fb"]) if (nr >= 1 and rec["fb"] is not None) else 0)


# ------------------------------------------------------------------ the bot
STREET_N = {"flop": 3, "turn": 4, "river": 5}
R_BASE = {"preflop": 0.88, "flop": 0.90, "turn": 0.94, "river": 1.0}
BET_FR = (0.33, 0.5, 0.75, 1.0, 1.5)


class Bot:
    def __init__(self):
        self.rng = random.Random(int.from_bytes(os.urandom(8), "big"))
        self.nrng = np.random.default_rng(int.from_bytes(os.urandom(8), "big") % (2 ** 63))
        self.stats = Stats()
        self.seat = None
        self.total_hands = 200
        self.tms = []
        self.new_state()

    def new_state(self):
        self.hole = []
        self.board = []
        self.my_discard = None
        self.opp_discard = None
        self.done = 0
        self.w3 = None            # weights over the 22,100 triples (preflop tracked)
        self.pre_snap_cache = None
        self.part = None          # flop particles: dict(T, w, keys, ks)
        self.flop_specs = []      # list of (snapshot, pf, pr, beta, f, action)
        self.pair = None          # pair range: dict(H, w)
        self.res_cache = {}
        self.hist = []

    # ---- events
    def on_init(self, msg):
        self.total_hands = int(msg.get("total_hands", 200))

    def on_new_hand(self, msg):
        self.new_state()
        self.seat = msg.get("seat")
        self.hole = [c2i(c) for c in msg.get("hole_cards", [])]
        w = np.ones(len(TC3))
        for c in self.hole:
            w[(TC3 == c).any(1)] = 0.0
        self.w3 = w

    def on_discard_result(self, msg):
        self.hole = [c2i(c) for c in msg.get("hole_cards", [])]
        self.my_discard = c2i(msg["my_discard"]) if msg.get("my_discard") else None
        self.opp_discard = c2i(msg["opp_discard"]) if msg.get("opp_discard") else None
        self.res_cache = {}

    def on_hand_result(self, msg):
        self.stats.hands += 1
        try:
            hist = walk(msg.get("history"), self.seat)
            for rec in hist:
                if rec["actor"] == "opp":
                    self.stats.add(ctx_key(rec), rec["action"])
            if msg.get("result") == "showdown" and msg.get("opp_hole_cards"):
                self.learn_showdown(msg, hist)
        except Exception as exc:
            log("learn error", repr(exc))

    def learn_showdown(self, msg, hist):
        oh = np.array([c2i(c) for c in msg["opp_hole_cards"]], dtype=np.int64)
        board = [c2i(c) for c in msg["board"]]
        for rec in hist:
            if rec["actor"] != "opp" or rec["action"] != "raise" or rec["street"] == "preflop":
                continue
            st = rec["street"]
            b = board[:STREET_N[st]]
            if len(b) < STREET_N[st]:
                continue
            known = set(b)
            H = _PAIRS[[not (p[0] in known or p[1] in known) for p in _PAIRS]]
            kall = keys2(H, b, st != "river")
            kh = keys2(oh[None, :], b, st != "river")[0]
            u = ((kall < kh).sum() + 0.5 * (kall == kh).sum()) / len(kall)
            s = self.stats.shown[st]
            s[0] += float(u)
            s[1] += 1
        od = msg.get("opp_discard")
        if od:
            T = np.array([sorted(list(oh) + [c2i(od)])], dtype=np.int64)
            _, ks = keys3(T, board[:3])
            T0 = T[0]
            ki = [i for i, (a, b) in enumerate(((0, 1), (0, 2), (1, 2))) if set((T0[a], T0[b])) == set(oh.tolist())]
            if ki:
                self.stats.best_n[1] += 1
                self.stats.best_n[0] += int(ks[0, ki[0]] >= ks[0].max())

    # ---- range tracking
    def beta(self, st):
        return self.stats.beta(st) if st in self.stats.shown else 0.2

    def sync(self, req):
        """Process opponent events not yet seen."""
        hist = walk(req.get("history"), self.seat)
        for rec in hist:
            if rec["i"] < self.done:
                continue
            self.done = rec["i"] + 1
            if rec["actor"] != "opp" or rec["action"] == "fold":
                continue
            st = rec["street"]
            if st != "preflop" and len(self.board) < STREET_N[st]:
                continue
            key = ctx_key(rec)
            pf, pc, pr = self.stats.probs(key)
            beta = self.beta(st)
            if st == "preflop":
                keys = PCT3
                sn = snap(keys, self.w3)
                u = u_from(sn, keys)
                L = lik(u, pf, pr, beta, rec["f"])
                L = L[2] if rec["action"] == "raise" else L[1]
                self.w3 = self.w3 * floor(L)
            elif st == "flop":
                self.ensure_particles()
                p = self.part
                sn = snap(p["keys"], p["w"])
                u = u_from(sn, p["keys"])
                L = lik(u, pf, pr, beta, rec["f"])
                L = L[2] if rec["action"] == "raise" else L[1]
                p["w"] = p["w"] * floor(L)
                self.flop_specs.append((sn, pf, pr, beta, rec["f"], rec["action"]))
                self.res_cache = {}
            else:
                self.ensure_pair()
                b = self.board[:STREET_N[st]]
                pr_ = self.pair
                valid = np.array([not (h[0] in b or h[1] in b) for h in pr_["H"]], dtype=bool) \
                    if len(b) > 3 else np.ones(len(pr_["H"]), dtype=bool)
                kk = keys2(pr_["H"], b, st != "river")
                pr_["w"] = pr_["w"] * valid
                sn = snap(kk, pr_["w"])
                u = u_from(sn, kk)
                L = lik(u, pf, pr, beta, rec["f"])
                L = L[2] if rec["action"] == "raise" else L[1]
                pr_["w"] = pr_["w"] * floor(L)
                self.res_cache = {}

    NPART = 700

    def ensure_particles(self):
        if self.part is not None:
            return
        board = self.board[:3]
        w = self.w3.copy()
        for c in board:
            w[(TC3 == c).any(1)] = 0.0
        self.w3 = w
        tot = w.sum()
        if tot <= 0:
            w = np.ones(len(TC3))
            for c in self.hole + board:
                w[(TC3 == c).any(1)] = 0.0
            tot = w.sum()
        idx = self.nrng.choice(len(TC3), size=self.NPART, p=w / tot)
        T = TC3[idx]
        keys, ks = keys3(T, board)
        self.part = dict(T=T, w=np.ones(self.NPART), keys=keys, ks=ks)

    def ensure_pair(self):
        if self.pair is not None:
            return
        self.ensure_particles()
        board = self.board[:3]
        d = self.opp_discard
        known = set(self.hole) | set(board) | {d}
        if self.my_discard is not None:
            known.add(self.my_discard)
        H = _PAIRS[[not (p[0] in known or p[1] in known) for p in _PAIRS]]
        if d is None:
            self.pair = dict(H=H, w=np.ones(len(H)))
            return
        T = np.sort(np.concatenate([H, np.full((len(H), 1), d)], axis=1), axis=1)
        w = self.w3[IDX3[T[:, 0], T[:, 1], T[:, 2]]].copy()
        if w.sum() <= 0:
            w = np.ones(len(H))
        key3, ks = keys3(np.concatenate([H, np.full((len(H), 1), d)], axis=1), board)
        # keep chosen is columns (0,1) of this arrangement
        kept = ks[:, 0]
        pb = self.stats.pbest()
        cons = np.where(kept >= key3, pb, (1 - pb) / 2.0)
        w = w * cons
        # flop-action replay
        for sn, pf, pr, beta, f, action in self.flop_specs:
            u = u_from(sn, key3)
            L = lik(u, pf, pr, beta, f)
            L = L[2] if action == "raise" else L[1]
            w = w * floor(L)
        self.pair = dict(H=H, w=w)

    # ---- equity of my hand against each element of the current range
    def my_res_pre(self):
        e = E3[IDX3[tuple(sorted(self.hole))]] if len(self.hole) == 3 else 0.5
        e = min(0.98, max(0.02, e))
        s = np.log(e / (1 - e))
        return sig(s - LOGIT3), self.w3

    def flop_res(self, mykeeps, K=4):
        """Equity of each of my keeps vs each particle. Returns array (len(mykeeps), M)."""
        p = self.part
        board = self.board[:3]
        M = len(p["T"])
        T = p["T"]
        # opponent keep: best key pair per particle
        best = p["ks"].argmax(1)
        cols = np.array([(0, 1), (0, 2), (1, 2)])
        OH = np.stack([T[np.arange(M), cols[best, 0]], T[np.arange(M), cols[best, 1]]], axis=1)
        known = np.concatenate([T, np.broadcast_to(np.array(self.hole + board), (M, len(self.hole) + 3))], axis=1)
        rr = self.nrng.integers(0, 52, size=(M, K, 2))
        ok = rr[:, :, 0] != rr[:, :, 1]
        for j in range(known.shape[1]):
            ok &= (rr[:, :, 0] != known[:, j, None]) & (rr[:, :, 1] != known[:, j, None])
        fb = np.broadcast_to(np.array(board), (M * K, 3))
        runs = rr.reshape(M * K, 2)
        opp = evalv(np.concatenate([np.repeat(OH, K, axis=0), fb, runs], axis=1))
        okf = ok.reshape(-1).astype(np.float64)
        den = ok.sum(1) + 1e-9
        out = []
        for mk in mykeeps:
            me = evalv(np.concatenate([np.broadcast_to(np.array(mk), (M * K, 2)), fb, runs], axis=1))
            win = ((me > opp) + 0.5 * (me == opp)) * okf
            out.append(win.reshape(M, K).sum(1) / den)
        return np.array(out)

    def turn_res(self, mk, board, K=10):
        pr_ = self.pair
        H = pr_["H"]
        known = set(self.hole) | set(board)
        if self.my_discard is not None:
            known.add(self.my_discard)
        if self.opp_discard is not None:
            known.add(self.opp_discard)
        rest = [c for c in range(52) if c not in known]
        cs = self.rng.sample(rest, min(K, len(rest)))
        N = len(H)
        num = np.zeros(N)
        den = np.zeros(N)
        mkk = np.array(mk, dtype=np.int64)
        bl = np.array(board, dtype=np.int64)
        for c in cs:
            ok = (H[:, 0] != c) & (H[:, 1] != c)
            full = np.concatenate([bl, [c]])
            opp = evalv(np.concatenate([H, np.broadcast_to(full, (N, 5))], axis=1))
            me = evalv(np.concatenate([mkk, full])[None, :])[0]
            num += ok * ((me > opp) + 0.5 * (me == opp))
            den += ok
        return num / np.maximum(den, 1)

    def river_res(self, mk, board):
        H = self.pair["H"]
        N = len(H)
        opp = evalv(np.concatenate([H, np.broadcast_to(np.array(board, dtype=np.int64), (N, 5))], axis=1))
        me = evalv(np.array([list(mk) + list(board)], dtype=np.int64))[0]
        return (me > opp) + 0.5 * (me == opp)

    # ---- decision machinery
    def model_arrays(self, st):
        """(res, w, u) for the current street; u is each range element's percentile in the current range."""
        board = self.board
        if st == "preflop":
            res, w = self.my_res_pre()
            u = u_from(snap(PCT3, w), PCT3)
            return res, w, u
        if st == "flop":
            self.ensure_particles()
            p = self.part
            ck = ("flop", len(self.hole))
            if ck not in self.res_cache:
                if len(self.hole) == 3:
                    h = self.hole
                    keeps = [[h[1], h[2]], [h[0], h[2]], [h[0], h[1]]]
                    R = self.flop_res(keeps)
                    wn = p["w"] / max(1e-9, p["w"].sum())
                    ev = (R * wn[None, :]).sum(1)
                    res = R[int(ev.argmax())]
                else:
                    res = self.flop_res([self.hole])[0]
                self.res_cache[ck] = res
            res = self.res_cache[ck]
            w = p["w"]
            u = u_from(snap(p["keys"], w), p["keys"])
            return res, w, u
        self.ensure_pair()
        pr_ = self.pair
        b = board[:STREET_N[st]]
        ck = (st, tuple(b))
        if ck not in self.res_cache:
            if st == "turn":
                r = self.turn_res(self.hole, b)
            else:
                r = self.river_res(self.hole, b)
            self.res_cache[ck] = r
        res = self.res_cache[ck]
        valid = np.array([not (h[0] in b or h[1] in b) for h in pr_["H"]], dtype=bool)
        w = pr_["w"] * valid
        kk = keys2(pr_["H"], b, st != "river")
        u = u_from(snap(kk, w), kk)
        return res, w, u

    def resp(self, st, nr_after, f_my, res, w, u):
        """Opponent's modelled response to my aggressive action; returns (pf, pc, pr, e_c, e_r)."""
        if st == "preflop":
            key = ("p", min(nr_after, 3), 1)
        else:
            key = (st, min(nr_after, 2), bucket(f_my) if nr_after >= 1 else 0)
            key = (st, min(nr_after, 2), bucket(f_my))
        pf, pc, pr = self.stats.probs(key)
        beta = self.beta(st)
        Lf, Lc, Lr = lik(u, pf, pr, beta, None)
        Lf, Lc, Lr = floor(Lf) * 0 + Lf, Lc, Lr
        W = w.sum() + 1e-12
        Pf = float((w * Lf).sum() / W)
        Pc = float((w * Lc).sum() / W)
        Pr = float((w * Lr).sum() / W)
        ec = float((w * Lc * res).sum() / max(1e-12, (w * Lc).sum())) if Pc > 1e-6 else 0.5
        er = float((w * Lr * res).sum() / max(1e-12, (w * Lr).sum())) if Pr > 1e-6 else 0.5
        return Pf, Pc, Pr, ec, er

    def act(self, req):
        t0 = time.perf_counter()
        st = req["street"]
        self.board = [c2i(c) for c in req.get("board", [])]
        self.sync(req)
        res, w, u = self.model_arrays(st)
        tw = w.sum()
        if tw <= 0:
            w = np.ones(len(w))
            tw = w.sum()
        e_all = float((w * res).sum() / tw)
        P = float(req["pot"])
        c = float(req["to_call"])
        mb = float(req["my_bet"])
        ob = float(req["opp_bet"])
        legal = req["legal_actions"]
        can_raise = "raise" in legal
        ip = self.seat == "button"
        Rb = R_BASE[st] + (0.03 if ip and st != "preflop" else 0.0) + (0.03 if ip and st == "preflop" else 0.0)
        nr = sum(1 for e in req.get("history", []) if e.get("street") == st and e.get("action") == "raise")
        best = ("check" if c == 0 else "fold", 0.0)
        if c > 0:
            ev_call = min(1.0, Rb) * e_all * (P + c) - c
            if st == "river":
                ev_call = e_all * (P + c) - c
            best = ("call", ev_call) if ev_call > 0 else ("fold", 0.0)
            ev_base = max(0.0, ev_call)
        else:
            ev_base = min(1.0, Rb) * e_all * P if st != "river" else e_all * P
            best = ("check", ev_base)
        cand = None
        if can_raise:
            lo, hi = req["min_raise"], req["max_raise"]
            sizes = set()
            if st == "preflop":
                if ob <= 2:
                    base = [5, 6, 8]
                else:
                    base = [int(round(ob * 2.5)), int(round(ob * 3.2)), int(round(ob * 4.5))]
                for x in base:
                    sizes.add(int(max(lo, min(hi, x))))
                sizes.add(int(hi)) if hi <= 60 else None
            else:
                for fr in BET_FR:
                    x = ob + c + fr * (P + c) if c > 0 else fr * P
                    if c > 0:
                        x = ob + fr * (P + c)
                    sizes.add(int(max(lo, min(hi, round(x)))))
                if c > 0:
                    sizes = {s for s in sizes if s <= hi}
            for tot in sorted(sizes):
                y = tot - mb                       # chips I add
                f_my = (tot - ob) / max(1.0, P + c) if (c > 0 or st == "preflop") else tot / max(1.0, P)
                Pf, Pc, Pr, ec, er = self.resp(st, nr + 1, f_my, res, w, u)
                Rbet = min(1.0, Rb + 0.04) if st != "river" else 1.0
                add = y - c if c > 0 else y        # chips the opponent must add to call (their matching amount)
                opp_add = tot - ob
                potc = P + y + max(0.0, (tot - ob))   # pot after opp calls: P + my add + their add
                ev_c = Rbet * ec * potc - y
                # opponent re-raises: assume to 2.5x; I fold or call
                y2 = 1.5 * (tot - mb) * 0.0
                ev_rr_call = er * Rbet * (potc + 3.0 * (tot - ob) + 0.0) - (y + 1.5 * (tot - ob))
                ev_rr = max(-y, ev_rr_call)
                ev = Pf * P + Pc * ev_c + Pr * ev_rr
                if ev > (cand[1] if cand else -1e9):
                    cand = (("raise", tot), ev, f_my)
        if cand is not None:
            margin = 0.025 * P + 0.3
            is_bluff = e_all < 0.38
            if cand[1] > best[1] + margin:
                ok = True
                if is_bluff:
                    cap = 0.55
                    if st == "river":
                        cap = 0.5
                    ok = self.rng.random() < cap
                if ok:
                    best = (cand[0], cand[1])
        self.tms.append(time.perf_counter() - t0)
        return best[0]

    def discard(self, req):
        hole = [c2i(c) for c in req["hole_cards"]]
        self.board = [c2i(c) for c in req["board"]]
        self.hole = hole
        self.ensure_particles()
        p = self.part
        keeps = [[hole[1], hole[2]], [hole[0], hole[2]], [hole[0], hole[1]]]
        R = self.flop_res(keeps, K=6)
        wn = p["w"] / max(1e-9, p["w"].sum())
        ev = (R * wn[None, :]).sum(1)
        i = int(ev.argmax())
        return hole[i]


# ------------------------------------------------------------------ protocol loop
def legalize(req, d):
    legal = req["legal_actions"]
    tc = req.get("to_call", 0)
    if isinstance(d, tuple) and d[0] == "raise":
        if "raise" in legal and "min_raise" in req:
            amt = int(max(req["min_raise"], min(req["max_raise"], int(d[1]))))
            return {"type": "action", "action": "raise", "amount": amt}
        d = "call" if tc > 0 else "check"
    if d == "fold" and "check" in legal:
        d = "check"
    if d == "check" and "check" not in legal:
        d = "call" if "call" in legal else "fold"
    if d == "call" and "call" not in legal:
        d = "check" if "check" in legal else "fold"
    if d not in legal:
        d = "check" if "check" in legal else "call" if "call" in legal else "fold"
    return {"type": "action", "action": d}


def fallback(req):
    return legalize(req, "check" if "check" in req["legal_actions"] else "fold")


def main():
    bot = Bot()
    out = sys.stdout
    for line in sys.stdin:
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
        reply = None
        try:
            if t == "action_request":
                try:
                    reply = legalize(msg, bot.act(msg))
                except Exception as exc:
                    log("act error", repr(exc))
                    reply = fallback(msg)
            elif t == "discard_request":
                try:
                    card = i2c(bot.discard(msg))
                    if card not in msg["hole_cards"]:
                        raise ValueError("bad discard")
                except Exception as exc:
                    log("discard error", repr(exc))
                    card = min(msg["hole_cards"], key=lambda c: RANKS.index(c[0]))
                reply = {"type": "discard", "card": card}
            elif t == "match_end":
                break
            elif t == "init":
                bot.on_init(msg)
            elif t == "new_hand":
                bot.on_new_hand(msg)
            elif t == "discard_result":
                bot.on_discard_result(msg)
            elif t == "hand_result":
                bot.on_hand_result(msg)
        except Exception as exc:
            log("event error", t, repr(exc))
            if t == "action_request":
                reply = fallback(msg)
        if reply is not None:
            out.write(json.dumps(reply) + "\n")
            out.flush()


if __name__ == "__main__":
    main()

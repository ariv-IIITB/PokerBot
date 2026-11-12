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
_PRE_B64 = "@@DATA@@"
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

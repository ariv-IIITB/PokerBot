"""s2_rollout: decisions by expected-value rollouts.
For each legal action (fold, call/check, a few raise sizes) the EV is estimated over sampled opponent hands drawn from
a weighted range; the opponent's fold probability depends on bet size and street (theory prior, scaled online by what
this opponent actually did in this leg); the continuation value is win share with a realisation factor. numpy
vectorised (own 5-7 card evaluator). Preflop, protocol loop, opponent counters: core.py (own copy of spar/common.py)."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
from core import (BaseBot, run, POP, STR, card_to_int, log, pre_pct, board_wet, has_draw)  # noqa: E402

# ------------------------------------------------------------------ vectorised evaluator
_POP = np.array(POP, dtype=np.int64)
_STR = np.array(STR, dtype=np.int64)
_HB = np.full(8192, 0, dtype=np.int64)
_T2 = np.zeros(8192, dtype=np.int64)
_T3 = np.zeros(8192, dtype=np.int64)
_T5 = np.zeros(8192, dtype=np.int64)
for _m in range(1, 8192):
    _rs = [r for r in range(12, -1, -1) if _m >> r & 1]
    _HB[_m] = _rs[0]
    for _tab, _k in ((_T2, 2), (_T3, 3), (_T5, 5)):
        v = 0
        for r in _rs[:_k]:
            v = (v << 4) | r
        _tab[_m] = v
_AR13 = np.arange(13)
_PW = (1 << _AR13).astype(np.int64)


def evalv(c):
    """Scores of hands: c is an int array (N, k), k >= 5; bigger is better (not comparable with core.score)."""
    r = c >> 2
    s = c & 3
    bits = np.left_shift(1, r).astype(np.int64)
    allm = np.bitwise_or.reduce(bits, axis=1)
    rc = (r[:, :, None] == _AR13).sum(1)
    sm = np.stack([(bits * (s == i)).sum(1) for i in range(4)], axis=1)
    fm = np.where(_POP[sm] >= 5, sm, 0).max(1)
    pm = ((rc == 2) * _PW).sum(1)
    tm = ((rc == 3) * _PW).sum(1)
    qm = ((rc == 4) * _PW).sum(1)
    out = _T5[allm].copy()
    # pair
    a = _HB[pm]
    out = np.where(pm > 0, (1 << 20) | (a << 12) | _T3[allm & ~(1 << a)], out)
    # two pair
    pm2 = pm & ~(1 << a)
    b = _HB[pm2]
    kick = _HB[allm & ~(1 << a) & ~(1 << b)]
    out = np.where(pm2 > 0, (2 << 20) | (a << 8) | (b << 4) | kick, out)
    # trips
    t = _HB[tm]
    out = np.where(tm > 0, (3 << 20) | (t << 8) | _T2[allm & ~(1 << t)], out)
    # straight, flush
    st = _STR[allm]
    out = np.where(st >= 0, (4 << 20) | st, out)
    out = np.where(fm > 0, (5 << 20) | _T5[fm], out)
    # full house
    rest = (tm & ~(1 << t)) | pm
    out = np.where((tm > 0) & (rest > 0), (6 << 20) | (t << 4) | _HB[rest], out)
    # quads
    q = _HB[qm]
    out = np.where(qm > 0, (7 << 20) | (q << 4) | _HB[allm & ~(1 << q)], out)
    # straight flush
    sf = _STR[fm]
    out = np.where((fm > 0) & (sf >= 0), (8 << 20) | sf, out)
    return out


_WIN = [(31 << (top - 4)) if top >= 4 else 0x100F for top in range(12, 2, -1)]


def draws(hole, board):
    """Vector (N,) bool: four to a flush or a straight draw using a hole card. hole (N,2), board (N,b)."""
    allc = np.concatenate([hole, board], axis=1)
    hs = hole & 3
    fl = np.zeros(len(hole), dtype=bool)
    for sx in range(4):
        n = ((allc & 3) == sx).sum(1)
        fl |= (n >= 4) & ((hs == sx).any(1))
    mask = np.bitwise_or.reduce(np.left_shift(1, allc >> 2), axis=1)
    hm = np.bitwise_or.reduce(np.left_shift(1, hole >> 2), axis=1)
    sd = np.zeros(len(hole), dtype=bool)
    for w in _WIN:
        got = mask & w
        sd |= (_POP[got] == 4) & ((got & hm) > 0)
    return fl | sd


STREET_R = {"flop": 0.90, "turn": 0.94, "river": 1.0}
SI = {"flop": 0, "turn": 1, "river": 2}
N_SAMPLES = 450


class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.np_rng = np.random.default_rng(int.from_bytes(os.urandom(8), "big"))
        self.fm = {}                       # (street index, kind) -> [folds, expected folds]
        self.fm_all = [0.0, 0.0]
        self.times = []

    # ---------------------------------------------------------------- opponent fold model
    @staticmethod
    def f_theory(f, kind):
        base = f / (1.0 + f)
        return base * (0.7 if kind else 0.85)

    def kmul(self, si, kind):
        a = (self.fm_all[0] + 3.0) / (self.fm_all[1] + 3.0)
        o = self.fm.get((si, kind), (0.0, 0.0))
        return (o[0] + 8.0 * a) / (o[1] + 8.0)

    def fold_prob(self, st, f, kind):
        k = self.kmul(SI[st], kind)
        return min(0.92, max(0.04, self.f_theory(f, kind) * min(1.6, max(0.4, k))))

    def on_hand_result(self, msg):
        super().on_hand_result(msg)
        try:
            self.learn_folds(msg)
        except Exception as exc:
            log("fold learn error:", repr(exc))

    def learn_folds(self, msg):
        me = 1 if self.seat == "button" else 2
        com = {"me": me, "opp": 3 - me}
        lev = dict(com)
        street = None
        hist = msg.get("history") or []
        for i, e in enumerate(hist):
            st, who, a = e.get("street"), e.get("actor"), e.get("action")
            oth = "opp" if who == "me" else "me"
            if st != street:
                street = st
                if st != "preflop":
                    lev = {"me": 0, "opp": 0}
            pot = com["me"] + com["opp"]
            if a == "raise":
                amt = e.get("amount") or 0
                to_call = lev[oth] - lev[who]
                kind = 0 if lev[oth] == 0 else 1
                frac = amt / max(1, pot) if kind == 0 else (amt - lev[oth]) / max(1, pot + to_call)
                if who == "me" and st in SI and i + 1 < len(hist):
                    nx = hist[i + 1]
                    if nx.get("actor") == "opp" and nx.get("street") == st:
                        folded = 1.0 if nx.get("action") == "fold" else 0.0
                        expf = self.f_theory(frac, kind)
                        o = self.fm.setdefault((SI[st], kind), [0.0, 0.0])
                        o[0] += folded
                        o[1] += expf
                        self.fm_all[0] += folded
                        self.fm_all[1] += expf
                com[who] += amt - lev[who]
                lev[who] = amt
            elif a == "call":
                add = lev[oth] - lev[who]
                com[who] += add
                lev[who] = lev[oth]

    # ---------------------------------------------------------------- sampling
    def sample(self, req, n):
        board = np.array(self.board, dtype=np.int64)
        st = req["street"]
        known = set(self.hole) | set(self.board)
        if self.opp_discard is not None:
            known.add(self.opp_discard)
        if self.my_discard is not None:
            known.add(self.my_discard)
        rest = np.array([c for c in range(52) if c not in known], dtype=np.int64)
        need = 5 - len(board)
        k_opp = 3 if (len(self.hole) == 3) else 2
        m = k_opp + need
        idx = np.argsort(self.np_rng.random((n, len(rest))), axis=1)[:, :m]
        draw = rest[idx]
        return board, draw[:, :k_opp], draw[:, k_opp:], need

    def rollout_data(self, req, n=N_SAMPLES):
        """Returns weights w (n,), weighted percentile u (n,), and per keep win vectors (n,) outcome in {0,.5,1}."""
        board, oh, run_, need = self.sample(req, n)
        pre = len(self.hole) == 3
        N = len(oh)
        brd = np.broadcast_to(board, (N, len(board)))
        # opponent keep and current strength
        if oh.shape[1] == 3:
            keeps = [oh[:, [1, 2]], oh[:, [0, 2]], oh[:, [0, 1]]]
            cur_all = []
            for kp in keeps:
                sc = evalv(np.concatenate([kp, brd], axis=1)) + (draws(kp, brd) * (1 << 19) if need else 0)
                cur_all.append(sc)
            cur_all = np.stack(cur_all, axis=1)
            j = cur_all.argmax(1)
            ohk = np.where((j == 0)[:, None], keeps[0], np.where((j == 1)[:, None], keeps[1], keeps[2]))
            cur = cur_all.max(1)
        else:
            ohk = oh
            cur = evalv(np.concatenate([ohk, brd], axis=1))
            if need:
                cur = cur + draws(ohk, brd) * (1 << 19)
        full = np.concatenate([brd, run_], axis=1)
        theirs = evalv(np.concatenate([ohk, full], axis=1))
        # my outcomes per keep
        if pre:
            h = self.hole
            mk = [[h[1], h[2]], [h[0], h[2]], [h[0], h[1]]]
        else:
            mk = [self.hole]
        outs = []
        for kp in mk:
            kk = np.broadcast_to(np.array(kp, dtype=np.int64), (N, 2))
            mine = evalv(np.concatenate([kk, full], axis=1))
            outs.append(np.where(mine > theirs, 1.0, np.where(mine == theirs, 0.5, 0.0)))
        win = max(outs, key=lambda o: o.mean())
        # weights
        p = min(6.0, 1.3 * self.pressure(req))
        order = np.argsort(cur, kind="stable")
        u0 = np.empty(N)
        u0[order] = (np.arange(N) + 0.5) / N
        w = u0 ** p if p > 0.05 else np.ones(N)
        if self.opp_discard is not None and len(board) >= 3:
            fl = np.broadcast_to(board[:3], (N, 3))
            d = np.full((N, 1), self.opp_discard, dtype=np.int64)
            kept = evalv(np.concatenate([ohk, fl], axis=1))
            a1 = evalv(np.concatenate([ohk[:, :1], d, fl], axis=1))
            a2 = evalv(np.concatenate([ohk[:, 1:], d, fl], axis=1))
            w = w * np.where(np.maximum(a1, a2) > kept, 0.25, 1.0)
        # weighted percentile within the range
        ws = w[order]
        cw = np.cumsum(ws)
        tot = cw[-1]
        uw = np.empty(N)
        uw[order] = (cw - 0.5 * ws) / max(tot, 1e-9)
        return w, uw, win

    # ---------------------------------------------------------------- decision
    def postflop(self, req, P):
        import time
        t0 = time.perf_counter()
        r = self.decide(req)
        self.times.append(time.perf_counter() - t0)
        return r

    def candidates(self, req):
        legal = req["legal_actions"]
        pot, tc = req["pot"], req["to_call"]
        out = []
        if "raise" in legal and "min_raise" in req:
            mn, mx = req["min_raise"], req["max_raise"]
            if tc == 0:
                base = req["my_bet"]
                fr = (0.33, 0.55, 0.8, 1.1)
                tos = [base + int(round(f * pot)) for f in fr]
            else:
                fr = (0.7, 1.1, 2.0)
                tos = [req["opp_bet"] + int(round(f * (pot + tc))) for f in fr]
            if mx <= 2.5 * pot + req["my_bet"] + 10:
                tos.append(mx)
            seen = set()
            for T in tos:
                T = int(max(mn, min(mx, T)))
                if T not in seen:
                    seen.add(T)
                    out.append(T)
        return out

    def decide(self, req):
        st = req["street"]
        pot, tc = float(req["pot"]), float(req["to_call"])
        w, uw, win = self.rollout_data(req)
        ip = self.in_position()
        R = STREET_R[st] + (0.04 if ip else -0.02)
        if st == "river":
            R = 1.0
        wsum = w.sum()
        evs = {}
        evs["call" if tc > 0 else "check"] = (R * (w * win).sum() / wsum) * (pot + tc) - tc
        if tc > 0:
            evs["fold"] = 0.0
        raised_before = self.raises_this_street(req)
        for T in self.candidates(req):
            x = T - req["my_bet"]
            y = max(0.0, T - req["opp_bet"])
            frac = (x - tc) / max(1.0, pot + tc) if tc > 0 else x / max(1.0, pot)
            kind = 1 if tc > 0 else 0
            F = self.fold_prob(st, frac, kind)
            tau = F
            fold = 1.0 / (1.0 + np.exp(-(tau - uw) / 0.04))
            pf = (w * fold).sum() / wsum
            cont = w * (1.0 - fold)
            ev_call_branch = (R - 0.04 - 0.03 * (raised_before > 0)) * (cont * win).sum() / wsum * (pot + x + y) - x * (cont.sum() / wsum)
            evs[("raise", T)] = pf * pot + ev_call_branch
        # choose
        keys = list(evs.keys())
        vals = np.array([evs[k] for k in keys])
        temp = 0.015 * (pot + tc) + 0.10
        best = vals.max()
        pr = np.exp((vals - best) / temp)
        pr /= pr.sum()
        k = keys[int(self.np_rng.choice(len(keys), p=pr))]
        self.last_evs = evs
        if isinstance(k, tuple):
            return ("raise", k[1])
        return k

    # ---------------------------------------------------------------- discard
    def discard(self, req):
        hole = [card_to_int(c) for c in req["hole_cards"]]
        board = np.array([card_to_int(c) for c in req["board"]], dtype=np.int64)
        known = set(hole) | set(board.tolist())
        rest = np.array([c for c in range(52) if c not in known], dtype=np.int64)
        n = 500
        idx = np.argsort(self.np_rng.random((n, len(rest))), axis=1)[:, :4]
        d = rest[idx]
        # opponent: 3 cards unknown at discard time is modelled by a random kept pair: use first 2 of 3 + keep best
        full = np.concatenate([np.broadcast_to(board, (n, 3)), d[:, 2:4]], axis=1)
        opp = evalv(np.concatenate([d[:, :2], full], axis=1))
        scores = []
        for i in range(3):
            kp = [hole[j] for j in range(3) if j != i]
            kk = np.broadcast_to(np.array(kp, dtype=np.int64), (n, 2))
            mine = evalv(np.concatenate([kk, full], axis=1))
            win = np.where(mine > opp, 1.0, np.where(mine == opp, 0.5, 0.0)).mean()
            scores.append(win)
        i = int(np.argmax(scores))
        return hole[i]


if __name__ == "__main__":
    run(Bot)

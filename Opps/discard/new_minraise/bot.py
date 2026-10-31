#!/usr/bin/env python3.11
"""Small-ball Discard Hold'em bot (Pokerbots protocol 1.0, stdin/stdout JSON lines).

Style
  * opens with min-raises, re-raises by the minimum;
  * bets about 25-35 % of the pot, and only with very strong hands bets more
    (50-75 % of the pot);
  * calls a lot of small bets (the call threshold is close to the pot odds);
  * only cheap closed-form computations (rank counting, simple draw detection);
    no simulation.

Safety
  * every decision is wrapped in try/except and falls back to a safe legal
    action (check, else cheap call, else fold);
  * every action is validated and clamped against legal_actions / min_raise /
    max_raise before it is sent;
  * stdout carries protocol messages only (flushed after each); diagnostics
    go to stderr and are capped well below the 64 KB limit;
  * standard library only, no files, no sockets, no subprocesses.
"""
import json
import random
import sys
from bisect import bisect_right
from itertools import combinations

# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------
RANK_CHARS = "23456789TJQKA"
RANK_OF = {c: i + 2 for i, c in enumerate(RANK_CHARS)}
SUIT_ORDER = "shdc"


def parse_card(s):
    """'Kd' -> (13, 'd')."""
    return (RANK_OF[s[0]], s[1])


def parse_cards(lst):
    return [parse_card(c) for c in lst]


def card_str(c):
    return RANK_CHARS[c[0] - 2] + c[1]


def lowest_card(cards):
    """Engine's default discard: lowest rank, ties by suit order s, h, d, c."""
    return min(cards, key=lambda c: (c[0], SUIT_ORDER.index(c[1])))


# --------------------------------------------------------------------------
# Hand evaluation (any number of cards, best five used)
# --------------------------------------------------------------------------
def straight_high(rank_set):
    """Highest card of a straight within the rank set, or 0 (ace plays low too)."""
    rs = set(rank_set)
    if 14 in rs:
        rs.add(1)
    for high in range(14, 4, -1):
        if all((high - i) in rs for i in range(5)):
            return high
    return 0


def evaluate(cards):
    """Comparable tuple: (category, tiebreaks...).  8 = straight flush ... 0 = high card."""
    counts = {}
    suits = {}
    for r, s in cards:
        counts[r] = counts.get(r, 0) + 1
        suits.setdefault(s, []).append(r)
    flush_ranks = None
    for rs in suits.values():
        if len(rs) >= 5:
            flush_ranks = sorted(rs, reverse=True)
    if flush_ranks:
        sf = straight_high(flush_ranks)
        if sf:
            return (8, sf)
    groups = sorted(((c, r) for r, c in counts.items()), reverse=True)
    top_count, top_rank = groups[0]
    if top_count == 4:
        kick = max([r for r in counts if r != top_rank] or [0])
        return (7, top_rank, kick)
    if top_count == 3 and len(groups) > 1 and groups[1][0] >= 2:
        return (6, top_rank, groups[1][1])
    if flush_ranks:
        return (5,) + tuple(flush_ranks[:5])
    sh = straight_high(counts)
    if sh:
        return (4, sh)
    if top_count == 3:
        kick = sorted((r for r in counts if r != top_rank), reverse=True)[:2]
        return (3, top_rank) + tuple(kick)
    if top_count == 2:
        if len(groups) > 1 and groups[1][0] == 2:
            pairs = sorted((r for c, r in groups if c == 2), reverse=True)[:2]
            kick = max([r for r in counts if r not in pairs] or [0])
            return (2, pairs[0], pairs[1], kick)
        kicks = sorted((r for r in counts if r != top_rank), reverse=True)[:3]
        return (1, top_rank) + tuple(kicks)
    return (0,) + tuple(sorted(counts, reverse=True)[:5])


# --------------------------------------------------------------------------
# Post-flop strength (rough "equity vs a random hand" in 0..1)
# --------------------------------------------------------------------------
def draw_info(hole, board):
    """(flush_draw, straight_draw) with straight_draw 0 none / 1 one out rank / 2 open-ended.

    Only draws that use at least one hole card count.
    """
    allc = hole + board
    suit_cnt = {}
    for _, s in allc:
        suit_cnt[s] = suit_cnt.get(s, 0) + 1
    hole_suits = {s for _, s in hole}
    fd = any(c == 4 and s in hole_suits for s, c in suit_cnt.items())
    ranks = {r for r, _ in allc}
    hranks = {r for r, _ in hole}
    if 14 in ranks:
        ranks.add(1)
    if 14 in hranks:
        hranks.add(1)
    outs = set()
    for low in range(1, 11):
        window = set(range(low, low + 5))
        if len(window & ranks) == 4 and (window & hranks):
            miss = (window - ranks).pop()
            outs.add(14 if miss == 1 else miss)
    sd = 2 if len(outs) >= 2 else len(outs)
    return fd, sd


def board_penalty(board):
    """How scary the board is for one-pair / two-pair / trips type hands."""
    pen = 0.0
    suit_cnt = {}
    for _, s in board:
        suit_cnt[s] = suit_cnt.get(s, 0) + 1
    mx = max(suit_cnt.values()) if suit_cnt else 0
    if mx >= 3:
        pen += 0.06 if mx == 3 else 0.10
    if len(board) >= 4:
        ranks = {r for r, _ in board}
        if 14 in ranks:
            ranks.add(1)
        best = 0
        for low in range(1, 11):
            best = max(best, len(set(range(low, low + 5)) & ranks))
        if best >= 4:
            pen += 0.05
    return pen


def made_strength(hole, board):
    """(strength 0..1 for the made hand only, category)."""
    hr = sorted((c[0] for c in hole), reverse=True)
    br = sorted((c[0] for c in board), reverse=True)
    ev = evaluate(hole + board)
    cat = ev[0]
    n = len(board)
    top = br[0]
    ub = sorted(set(br), reverse=True)
    second = ub[1] if len(ub) > 1 else 0
    plays_board = n == 5 and evaluate(board) == ev

    if plays_board and cat >= 4:
        return 0.35, cat
    if plays_board and cat >= 1:
        s = 0.12 + (0.06 if hr[0] >= 13 else 0.0)
        return s, cat

    if cat == 0:
        over = sum(1 for h in hr if h > top)
        s = 0.12 + 0.05 * over + (0.10 * (hr[0] - 8) / 6.0 if hr[0] > 8 else 0.0)
        return s, cat

    if cat == 1:
        p = ev[1]
        if hr[0] == hr[1] == p:  # pocket pair
            if p > top:
                s = 0.70 + 0.10 * (p - 2) / 12.0
            elif p > second:
                s = 0.50
            else:
                s = 0.42
        elif p in hr:  # one hole card pairs the board
            kick = hr[1] if hr[0] == p else hr[0]
            if p == top:
                s = 0.58 + 0.14 * (kick - 2) / 12.0
            elif p == second:
                s = 0.44 + (0.04 if kick >= 11 else 0.0)
            else:
                s = 0.36
        else:  # pair sits on the board only
            s = 0.14 + (0.06 if hr[0] >= 13 else 0.0)
    elif cat == 2:
        pr = (ev[1], ev[2])
        m = sum(1 for p in pr if p in hr)
        if m == 2:
            s = 0.84 + (0.04 if pr[0] == top else 0.0)
        elif m == 1:
            p = pr[0] if pr[0] in hr else pr[1]
            other = pr[1] if p == pr[0] else pr[0]
            if hr[0] == hr[1]:  # pocket pair next to a board pair
                s = 0.62 if p > other else 0.50
            else:
                s = 0.52 + (0.04 if p == top else 0.0)
        else:
            s = 0.18
    elif cat == 3:
        k = hr.count(ev[1])
        if k == 2:
            s = 0.90
        elif k == 1:
            other = hr[1] if hr[0] == ev[1] else hr[0]
            s = 0.80 + (0.04 if other >= 11 else 0.0)
        else:
            s = 0.25 + (0.10 if hr[0] >= 13 else 0.0)
    elif cat == 4:
        s = 0.93 + (0.02 if ev[1] == 14 else 0.0)
    elif cat == 5:
        s = 0.92 + (0.04 if ev[1] >= 13 else 0.0)
    elif cat == 6:
        s = 0.96
    else:
        s = 0.99

    if 1 <= cat <= 4:
        s = max(0.05, s - board_penalty(board))
    return s, cat


def keep_value(keep, board):
    """(strength incl. draw bonus, draw bonus) for a specific two-card holding."""
    s, cat = made_strength(keep, board)
    n = len(board)
    bonus = 0.0
    if n < 5 and cat < 4:
        fd, sd = draw_info(keep, board)
        flop = n == 3
        if fd:
            bonus += 0.22 if flop else 0.14
        if sd == 2:
            bonus += 0.18 if flop else 0.11
        elif sd == 1:
            bonus += 0.08 if flop else 0.05
        bonus = min(bonus, 0.30)
    return min(0.97, s + bonus), bonus


def strength(hole, board):
    """Strength of our holding.  With three hole cards (flop betting) we use the best keep."""
    if len(hole) <= 2:
        return keep_value(hole, board)
    best_s, best_d = -1.0, 0.0
    for pair in combinations(hole, 2):
        s, d = keep_value(list(pair), board)
        if s > best_s:
            best_s, best_d = s, d
    # both players still hold three cards on the flop: everything looks a bit stronger
    return max(0.05, best_s - 0.04), best_d


def choose_discard(hole_strs, board):
    """Index of the card to throw away (keep the best two-card holding)."""
    hole = parse_cards(hole_strs)
    best_i, best_score = 0, -1e9
    for i in range(len(hole)):
        keep = [c for j, c in enumerate(hole) if j != i]
        s, _ = keep_value(keep, board)
        score = s + 0.001 * sum(c[0] for c in keep)
        if score > best_score:
            best_i, best_score = i, score
    return best_i


# --------------------------------------------------------------------------
# Pre-flop strength: Chen-style score of the best pairs among the 3 cards,
# turned into a percentile among all 22100 three-card hands.
# --------------------------------------------------------------------------
_CHEN_HIGH = {14: 10.0, 13: 8.0, 12: 7.0, 11: 6.0}


def chen2(a, b):
    hi, lo = max(a[0], b[0]), min(a[0], b[0])
    sc = _CHEN_HIGH.get(hi, hi / 2.0)
    if hi == lo:
        return max(5.0, sc * 2.0)
    if a[1] == b[1]:
        sc += 2.0
    gap = hi - lo - 1
    sc -= (0, 1, 2, 4, 5)[min(gap, 4)]
    if gap <= 1 and hi < 12:
        sc += 1.0
    return sc


def pf_score(cards):
    c0, c1, c2 = cards
    combos = sorted((chen2(c0, c1), chen2(c0, c2), chen2(c1, c2)), reverse=True)
    score = combos[0] + 0.3 * combos[1]
    if c0[1] == c1[1] == c2[1]:
        score += 1.5
    rs = sorted(c[0] for c in cards)
    if len(set(rs)) == 3 and rs[2] - rs[0] <= 4:
        score += 1.0
    if rs[0] == rs[2]:
        score += 1.0
    return score


# Score at each 1 % quantile of all 22100 three-card hands (pf_score above).
PF_TABLE = [
    0.5, 1.85, 2.3, 2.5, 2.6, 2.8, 3.0, 3.3, 3.5, 3.6,
    3.75, 3.9, 3.9, 3.9, 4.2, 4.3, 4.4, 4.6, 4.6, 4.75,
    4.9, 4.9, 4.95, 5.0, 5.1, 5.25, 5.35, 5.45, 5.6, 5.6,
    5.75, 5.8, 5.9, 5.9, 5.9, 6.05, 6.2, 6.2, 6.3, 6.35,
    6.45, 6.5, 6.5, 6.5, 6.5, 6.5, 6.6, 6.7, 6.9, 6.9,
    6.9, 7.05, 7.2, 7.3, 7.4, 7.5, 7.5, 7.6, 7.7, 7.85,
    7.9, 7.9, 8.05, 8.2, 8.4, 8.5, 8.5, 8.5, 8.5, 8.65,
    8.8, 8.9, 8.9, 9.15, 9.3, 9.5, 9.5, 9.5, 9.75, 9.8,
    10.1, 10.25, 10.5, 10.5, 10.65, 10.9, 11.1, 11.4, 11.5, 11.5,
    12.0, 12.3, 12.5, 12.9, 13.5, 14.4, 15.0, 16.4, 17.5, 21.5,
]


def pf_quantile(cards):
    """Fraction (0..1) of three-card starting hands that score at or below ours."""
    return bisect_right(PF_TABLE, pf_score(cards)) / float(len(PF_TABLE))


# --------------------------------------------------------------------------
# Action helpers
# --------------------------------------------------------------------------
def act(kind, amount=None):
    d = {"type": "action", "action": kind}
    if kind == "raise":
        d["amount"] = int(amount)
    return d


def passive(legal):
    if "check" in legal:
        return act("check")
    if "call" in legal:
        return act("call")
    return act("fold")


def can_raise_of(req, legal):
    return "raise" in legal and "min_raise" in req and "max_raise" in req


def make_raise(req, legal, target):
    """Raise to `target`, clamped to the legal range; passive if raising is impossible."""
    if can_raise_of(req, legal):
        lo = int(req["min_raise"])
        hi = int(req["max_raise"])
        t = min(hi, max(lo, int(round(target))))
        return act("raise", t)
    return passive(legal)


def fallback_action(req):
    """Last-resort legal action: check, cheap call, else fold."""
    try:
        legal = list(req.get("legal_actions") or [])
        if "check" in legal:
            return act("check")
        to_call = int(req.get("to_call", 0))
        pot = int(req.get("pot", 0))
        if "call" in legal and to_call * 4 <= pot:
            return act("call")
        if "fold" in legal:
            return act("fold")
        if "call" in legal:
            return act("call")
    except Exception:
        pass
    return act("check")


def street_info(history, street):
    my_r = opp_r = 0
    opp_checked = False
    pf_aggr = False
    for e in history:
        if not isinstance(e, dict):
            continue
        st, who, a = e.get("street"), e.get("actor"), e.get("action")
        if st == street:
            if a == "raise":
                if who == "me":
                    my_r += 1
                else:
                    opp_r += 1
            elif a == "check" and who == "opp":
                opp_checked = True
        if st == "preflop" and a == "raise":
            pf_aggr = who == "me"
    return {"my_raises": my_r, "opp_raises": opp_r, "opp_checked": opp_checked, "pf_aggr": pf_aggr}


# --------------------------------------------------------------------------
# The bot
# --------------------------------------------------------------------------
class Bot:
    def __init__(self):
        self.rng = random.Random()
        self.total_hands = 400
        self.time_bank = 60000
        self.hole = []
        self.seat = "button"
        self.hand_id = 0
        # opponent model (counts over the whole match)
        self.o_bet = 0   # opponent post-flop bets / raises
        self.o_pass = 0  # opponent post-flop checks / calls
        self.f_fold = 0  # opponent folds when we raised
        self.f_cont = 0  # opponent continues when we raised
        self.hands_seen = 0
        self.jam_hands = 0   # hands where the opponent raised pre-flop to 20+ chips
        self.jammy = False
        self.call_mult = 1.0
        self.bluff_mult = 1.0
        self.value_mult = 1.0
        self.err_logged = 0

    # ---- plumbing --------------------------------------------------------
    def log_err(self, exc):
        if self.err_logged < 20:
            self.err_logged += 1
            try:
                sys.stderr.write("bot error: %r\n" % (exc,))
                sys.stderr.flush()
            except Exception:
                pass

    def handle(self, msg):
        """Process one engine message; returns a reply dict for requests, else None."""
        t = msg.get("type")
        if t == "action_request":
            try:
                return self.decide(msg)
            except Exception as exc:  # never let an exception escape
                self.log_err(exc)
                return fallback_action(msg)
        if t == "discard_request":
            return self.on_discard(msg)
        if t == "init":
            self.total_hands = int(msg.get("total_hands", 400) or 400)
            self.time_bank = int(msg.get("time_bank_ms", 60000) or 60000)
        elif t == "new_hand":
            self.hand_id = msg.get("hand_id", 0)
            self.seat = msg.get("seat", "button")
            self.hole = parse_cards(msg.get("hole_cards") or [])
        elif t == "discard_result":
            hc = msg.get("hole_cards")
            if hc:
                self.hole = parse_cards(hc)
        elif t == "hand_result":
            self.learn(msg)
        return None

    # ---- discard ---------------------------------------------------------
    def on_discard(self, req):
        cards = list(req.get("hole_cards") or [])
        try:
            board = parse_cards(req.get("board") or [])
            if len(cards) >= 2 and board:
                i = choose_discard(cards, board)
                return {"type": "discard", "card": cards[i]}
        except Exception as exc:
            self.log_err(exc)
        try:
            if cards:
                return {"type": "discard", "card": card_str(lowest_card(parse_cards(cards)))}
        except Exception as exc:
            self.log_err(exc)
        if cards:
            return {"type": "discard", "card": cards[0]}
        return {"type": "discard", "card": "2s"}

    # ---- opponent model --------------------------------------------------
    def learn(self, msg):
        hist = msg.get("history") or []
        prev = None
        last_fold_recorded = False
        self.hands_seen += 1
        try:
            if any(isinstance(e, dict) and e.get("actor") == "opp" and e.get("street") == "preflop"
                   and e.get("action") == "raise" and int(e.get("amount", 0)) >= 20 for e in hist):
                self.jam_hands += 1
        except Exception:
            pass
        for e in hist:
            if not isinstance(e, dict):
                continue
            who, a, st = e.get("actor"), e.get("action"), e.get("street")
            if who == "opp":
                if st != "preflop":
                    if a == "raise":
                        self.o_bet += 1
                    elif a in ("call", "check"):
                        self.o_pass += 1
                if prev is not None and prev.get("actor") == "me" and prev.get("action") == "raise":
                    if a == "fold":
                        self.f_fold += 1
                        last_fold_recorded = True
                    elif a in ("call", "raise"):
                        self.f_cont += 1
            prev = e
        # folds may not be listed in the history: infer from the result
        try:
            if (msg.get("result") == "fold" and int(msg.get("net", 0)) > 0 and not last_fold_recorded
                    and prev is not None and prev.get("actor") == "me" and prev.get("action") == "raise"):
                self.f_fold += 1
        except Exception:
            pass
        self.update_mults()

    def update_mults(self):
        self.jammy = self.hands_seen >= 20 and self.jam_hands > 0.25 * self.hands_seen
        tot = self.o_bet + self.o_pass
        self.call_mult = 1.0
        if tot >= 40:
            ag = self.o_bet / float(tot)
            if ag > 0.40:
                self.call_mult = 0.88      # they bet a lot: more bluffs, call wider
            elif ag < 0.15:
                self.call_mult = 1.15      # they rarely bet: respect their bets
        n = self.f_fold + self.f_cont
        self.bluff_mult = 1.0
        self.value_mult = 1.0
        if n >= 30:
            fr = self.f_fold / float(n)
            if fr > 0.50:
                self.bluff_mult = 1.7
            elif fr > 0.40:
                self.bluff_mult = 1.3
            elif fr < 0.20:
                self.bluff_mult = 0.2
            elif fr < 0.30:
                self.bluff_mult = 0.6
            if fr < 0.25:
                self.value_mult = 1.25

    # ---- decisions -------------------------------------------------------
    def decide(self, req):
        legal = list(req.get("legal_actions") or [])
        to_call = int(req.get("to_call", 0))
        pot = int(req.get("pot", 0))
        time_left = req.get("time_left_ms")
        if (isinstance(time_left, (int, float)) and time_left < 400) or not self.hole:
            # nearly out of time (or state missing): trivial cheap policy
            if "check" in legal:
                return act("check")
            if "call" in legal and to_call * 4 <= pot:
                return act("call")
            return act("fold") if "fold" in legal else passive(legal)
        if req.get("street") == "preflop":
            return self.preflop(req, legal)
        return self.postflop(req, legal)

    def preflop(self, req, legal):
        q = pf_quantile(self.hole)
        pot = int(req["pot"])
        to_call = int(req["to_call"])
        opp_bet = int(req["opp_bet"])
        hist = [e for e in (req.get("history") or []) if isinstance(e, dict) and e.get("street") == "preflop"]
        my_raises = sum(1 for e in hist if e.get("actor") == "me" and e.get("action") == "raise")
        opp_raises = sum(1 for e in hist if e.get("actor") == "opp" and e.get("action") == "raise")
        can_raise = can_raise_of(req, legal)
        rng = self.rng.random()
        rng2 = self.rng.random()

        if to_call <= 0:
            # big blind with the option after a limp
            if can_raise and q >= 0.45 and rng < 0.85:
                if q >= 0.93 and rng2 < 0.5:
                    return make_raise(req, legal, 3 * opp_bet)
                return make_raise(req, legal, int(req["min_raise"]))
            return act("check") if "check" in legal else passive(legal)

        if to_call == 1 and not hist and self.seat == "button":
            # small blind, first to act: min-raise wide, limp the middle, fold the dregs
            if q >= 0.16 and can_raise and rng < 0.97:
                return make_raise(req, legal, int(req["min_raise"]))
            if q >= 0.06 or not can_raise:
                return act("call")
            return act("fold")

        r = to_call / float(pot + to_call)
        thr = 0.02 + 1.15 * r + 0.07 * max(0, opp_raises - 1)
        thr *= self.call_mult
        if to_call >= 30:
            thr = max(thr, 0.72)
        if to_call >= 80:
            thr = max(thr, 0.88)
        thr = min(thr, 0.93)
        if self.jammy:
            thr = min(thr, 0.55)  # opponent shoves a lot pre-flop: defend much wider

        if can_raise and opp_bet <= 30 and my_raises < 2:
            if q >= 0.95 and rng < 0.9:
                if rng2 < 0.5:
                    return make_raise(req, legal, int(req["min_raise"]))
                return make_raise(req, legal, 3 * opp_bet)
            if q >= 0.80 and rng < 0.55:
                return make_raise(req, legal, int(req["min_raise"]))
            if (q >= 0.45 and opp_raises == 1 and my_raises == 0 and opp_bet <= 4
                    and rng < 0.10 * self.bluff_mult):
                return make_raise(req, legal, int(req["min_raise"]))  # light min 3-bet
        if q >= thr:
            return act("call")
        return act("fold")

    def postflop(self, req, legal):
        street = req.get("street")
        board = parse_cards(req.get("board") or [])
        pot = int(req["pot"])
        to_call = int(req["to_call"])
        opp_bet = int(req["opp_bet"])
        s, dr = strength(self.hole, board)
        info = street_info(req.get("history") or [], street)
        ip = self.seat == "button"
        can_raise = can_raise_of(req, legal)
        rng = self.rng.random()

        if to_call <= 0:
            if not can_raise:
                return passive(legal)
            u = self.rng.uniform
            bet = False
            frac = 0.30
            if s >= 0.85:
                bet = rng < 0.85
                frac = u(0.50, 0.75)  # the only place we bet big
            elif s >= 0.60:
                bet = rng < 0.80
                frac = u(0.28, 0.35)
            elif s >= 0.42:
                bet = rng < min(0.9, 0.40 * self.value_mult)
                frac = u(0.25, 0.30)
            elif dr >= 0.10 and street != "river":
                bet = rng < min(0.6, 0.30 * self.bluff_mult)
                frac = u(0.28, 0.34)
            else:
                p = 0.08
                if ip and info["opp_checked"]:
                    p = 0.20
                if street == "flop" and info["pf_aggr"]:
                    p = max(p, 0.25)
                if street == "river":
                    p *= 0.6
                bet = rng < min(0.5, p * self.bluff_mult)
                frac = u(0.25, 0.33)
            if not bet:
                return passive(legal)
            return make_raise(req, legal, opp_bet + max(2, int(round(frac * pot))))

        # facing a bet
        r = to_call / float(pot + to_call)
        war = info["my_raises"] >= 1 and info["opp_raises"] >= 1
        s_eff = s - (0.06 if war else 0.0) - 0.03 * max(0, info["opp_raises"] - 1)
        mult = {"flop": 1.0, "turn": 1.1, "river": 1.2}.get(street, 1.1) * self.call_mult
        thr = 0.06 + r * mult
        if to_call >= 40:
            thr += 0.05
        if to_call >= 100:
            thr += 0.08
        if can_raise:
            r2 = self.rng.random()
            if s_eff >= 0.85 and rng < 0.88:
                if r2 < 0.4:
                    return make_raise(req, legal, opp_bet + int(round(0.6 * (pot + to_call))))
                return make_raise(req, legal, int(req["min_raise"]))
            if s_eff >= 0.62 and not war and r <= 0.25 and r2 < 0.25:
                return make_raise(req, legal, int(req["min_raise"]))
            if (dr >= 0.12 and street != "river" and not war and r <= 0.22
                    and r2 < 0.15 * self.bluff_mult):
                return make_raise(req, legal, int(req["min_raise"]))
        if s_eff >= thr:
            return act("call") if "call" in legal else passive(legal)
        return act("fold") if "fold" in legal else passive(legal)


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
def main():
    bot = Bot()
    out = sys.stdout
    while True:
        try:
            raw = sys.stdin.buffer.readline()
        except (KeyboardInterrupt, OSError, ValueError):
            break
        if not raw:  # EOF
            break
        line = raw.decode("utf-8", "replace").strip()
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
            bot.log_err(exc)
            reply = None
            if t == "action_request":
                reply = fallback_action(msg)
            elif t == "discard_request":
                try:
                    cards = list(msg.get("hole_cards") or [])
                    reply = {"type": "discard", "card": cards[0] if cards else "2s"}
                except Exception:
                    reply = {"type": "discard", "card": "2s"}
        if reply is None:
            continue
        try:
            out.write(json.dumps(reply, separators=(",", ":")) + "\n")
            out.flush()
        except (BrokenPipeError, OSError, ValueError):
            break


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Discard Hold'em bot: a pure rule-based design.

No Monte Carlo, no equity calculation.  Every decision comes from fixed rules:

* Preflop: a hand-score formula for the 3 hole cards (Chen-style points of the
  three 2-card subsets plus a small flexibility bonus) compared with fixed
  thresholds for opening, defending, 3-betting and 4-betting.
* Postflop: the hand is classified into a strength class (high card, pair
  types, two pair, trips, straight, flush, full house, ...) and a draw class
  (flush draw, open-ended / gutshot straight draw, overcards).  The board is
  classified for texture (wet / dry, paired, flush and straight threats).
  Fixed bet sizes (1/3, 1/2, 3/4 pot, ...) and fixed pot-odds thresholds do
  the rest.
* Discard: each of the three possible 2-card holdings is scored with the same
  classifier (plus small backdoor / connectedness bonuses); the card whose
  removal leaves the best holding is discarded.
* A very light opponent profile (postflop aggression, preflop raise rate and
  how often the opponent folds to our bets) shifts a few thresholds.

Only the standard library is used.  stdout carries protocol JSON lines only.
"""
import json
import random
import sys

RANKS = "23456789TJQKA"
RANK_VAL = {ch: i + 2 for i, ch in enumerate(RANKS)}
SUIT_ORDER = {"s": 0, "h": 1, "d": 2, "c": 3}
BB = 2

# ---------------------------------------------------------------------------
# Preflop thresholds on the hand score (see preflop_score).  They were chosen
# from the score percentiles of random 3-card hands:
#   p8 = 3.5, p38 = 6.5, p40 = 6.7, p60 = 8.25, p80 = 10.6, p90 = 12.7,
#   p95 = 14.9, p97 = 17.3, p98 = 19.
# ---------------------------------------------------------------------------
OPEN_RAISE = 6.5      # button: raise to 3 bb with the top ~62 %
LIMP_MIN = 3.5        # button: complete the blind with the next ~30 %, fold the rest
ISO_RAISE = 8.2       # big blind vs a limp: raise with the top ~40 %
ISO_BIG = 12.7        # ... and raise bigger with the top ~10 %
DEF_TINY = 5.0        # defend vs a min-raise (opp bet <= 4)
DEF_SMALL = 6.2       # defend vs an open to <= 4 bb (opp bet <= 8)
DEF_MED = 8.2         # vs a raise to 5-7 bb (opp bet <= 14)
DEF_BIG = 10.6        # vs a 3-bet sized raise (opp bet <= 30)
DEF_HUGE = 14.9       # vs a 4-bet sized raise (opp bet <= 80)
DEF_SHOVE = 17.3      # vs a shove-sized raise
THREE_BET = 12.7      # value 3-bet
FOUR_BET = 17.3       # value 4-bet
JAM = 19.5            # jam instead of a sized 4-bet

# ---------------------------------------------------------------------------
# Cards
# ---------------------------------------------------------------------------


def parse_card(s):
    """'As' -> (14, 's')."""
    return (RANK_VAL[s[0]], s[1])


def parse_cards(lst):
    return [parse_card(c) for c in lst]


def card_str(card):
    return RANKS[card[0] - 2] + card[1]


# ---------------------------------------------------------------------------
# Hand category evaluation (works for any number of cards, 1..7)
# ---------------------------------------------------------------------------


def straight_high(rank_iterable):
    """Highest card of the best straight in the ranks, or 0 (ace may be low)."""
    rs = set(rank_iterable)
    if 14 in rs:
        rs.add(1)
    for hi in range(14, 4, -1):
        ok = True
        for r in range(hi - 4, hi + 1):
            if r not in rs:
                ok = False
                break
        if ok:
            return hi
    return 0


def evaluate(cards):
    """Return (category, tiebreak tuple).  0 high card .. 8 straight flush.

    With fewer than 5 cards only the count based categories can occur.
    """
    cnt = {}
    by_suit = {}
    for r, s in cards:
        cnt[r] = cnt.get(r, 0) + 1
        by_suit.setdefault(s, []).append(r)
    flush = None
    for rs in by_suit.values():
        if len(rs) >= 5:
            flush = sorted(rs, reverse=True)
    if flush:
        sfh = straight_high(flush)
        if sfh:
            return (8, (sfh,))
    groups = sorted(((n, r) for r, n in cnt.items()), reverse=True)
    if groups[0][0] == 4:
        quad = groups[0][1]
        kick = max([r for r in cnt if r != quad], default=0)
        return (7, (quad, kick))
    trips = [r for n, r in groups if n == 3]
    pairs = [r for n, r in groups if n == 2]
    if trips and (len(trips) >= 2 or pairs):
        return (6, (trips[0], max(trips[1:] + pairs)))
    if flush:
        return (5, tuple(flush[:5]))
    sh = straight_high(cnt.keys())
    if sh:
        return (4, (sh,))
    if trips:
        t = trips[0]
        kick = sorted((r for r in cnt if r != t), reverse=True)[:2]
        return (3, (t,) + tuple(kick))
    if len(pairs) >= 2:
        hi, lo = pairs[0], pairs[1]
        kick = max([r for r in cnt if r != hi and r != lo], default=0)
        return (2, (hi, lo, kick))
    if pairs:
        p = pairs[0]
        kick = sorted((r for r in cnt if r != p), reverse=True)[:3]
        return (1, (p,) + tuple(kick))
    return (0, tuple(sorted(cnt, reverse=True)[:5]))


# ---------------------------------------------------------------------------
# Preflop hand score
# ---------------------------------------------------------------------------


def chen2(r1, r2, suited):
    """Chen-style points for a 2-card holding."""
    hi, lo = max(r1, r2), min(r1, r2)
    pts = {14: 10.0, 13: 8.0, 12: 7.0, 11: 6.0}.get(hi, hi / 2.0)
    if r1 == r2:
        return max(5.0, pts * 2.0)
    gap = hi - lo - 1
    if gap == 1:
        pts -= 1
    elif gap == 2:
        pts -= 2
    elif gap == 3:
        pts -= 4
    elif gap >= 4:
        pts -= 5
    if gap <= 1 and hi < 12:
        pts += 1
    if suited:
        pts += 2
    return pts


def preflop_score(cards):
    """Score of a 3-card hand: best 2-card subset + flexibility of the others."""
    vals = []
    for i in range(3):
        for j in range(i + 1, 3):
            a, b = cards[i], cards[j]
            vals.append(chen2(a[0], b[0], a[1] == b[1]))
    vals.sort(reverse=True)
    ranks = sorted(c[0] for c in cards)
    if ranks[0] == ranks[2]:
        return vals[0]  # three of a kind: just a pair, the third card is dead
    score = vals[0] + 0.35 * vals[1] + 0.1 * vals[2]
    if ranks[2] - ranks[0] <= 4:
        score += 1.0  # all three cards connected
    return score


# ---------------------------------------------------------------------------
# Board texture
# ---------------------------------------------------------------------------


def max_window(ranks):
    """Most distinct ranks of `ranks` inside any 5-rank straight window."""
    s = set(ranks)
    if 14 in s:
        s.add(1)
    best = 0
    for hi in range(5, 15):
        c = 0
        for r in range(hi - 4, hi + 1):
            if r in s:
                c += 1
        if c > best:
            best = c
    return best


def board_info(board):
    ranks = [c[0] for c in board]
    sc = {}
    for _, s in board:
        sc[s] = sc.get(s, 0) + 1
    max_suit = max(sc.values())
    win = max_window(ranks)
    paired = len(set(ranks)) < len(ranks)
    pts = 0.0
    if max_suit >= 4:
        pts += 1.6
    elif max_suit == 3:
        pts += 1.3
    elif max_suit == 2 and len(board) == 3:
        pts += 0.4
    if win >= 4:
        pts += 1.4
    elif win >= 3:
        pts += 0.8
    wet = 2 if pts >= 1.2 else (1 if pts >= 0.7 else 0)
    return {"max_suit": max_suit, "win": win, "paired": paired,
            "top": max(ranks), "wet": wet}


# ---------------------------------------------------------------------------
# Postflop hand classification
# ---------------------------------------------------------------------------


def made_strength(hole, board, binfo):
    """Strength class of the made hand on a 0..7 scale (see anchors below).

    0.0 nothing, 0.5 ace high, 1.0 bottom pair / underpair, 2.0 middle pair,
    2.8-3.9 top pair (kicker dependent), 3.3-4.6 overpair, 4.0-5.0 two pair,
    4.4-5.8 trips / set, 5.0-6.2 straight, 5.2-6.6 flush, 6.4-6.8 full house,
    7.0 quads / straight flush.
    """
    ev = evaluate(hole + board)
    bev = evaluate(board)
    cat, tb = ev
    hranks = [c[0] for c in hole]
    hset = set(hranks)
    bset = set(c[0] for c in board)
    brs = sorted(bset, reverse=True)
    top = brs[0]
    hi_hole = max(hranks)

    if len(board) == 5 and ev == bev and cat >= 3:
        # the board plays; our cards add nothing
        st = 1.5 if cat >= 4 else 0.8
        return st
    if cat == 0:
        st = 0.5 if hi_hole == 14 else (0.25 if hi_hole == 13 else 0.0)
    elif cat == 1:
        pr = tb[0]
        if hranks[0] == hranks[1] and hranks[0] == pr:
            if pr > top:
                st = 3.8 + 0.2 * (pr - 10) if pr >= 10 else 3.3
            else:
                k = sum(1 for r in brs if r > pr)
                st = 2.2 if k == 1 else (1.5 if k == 2 else 1.0)
        elif pr in hset:
            k = sum(1 for r in brs if r > pr)
            kick = max(r for r in hranks if r != pr)
            if k == 0:
                st = {14: 3.9, 13: 3.7, 12: 3.5, 11: 3.3, 10: 3.1}.get(kick, 2.8)
            elif k == 1:
                st = 2.2 + (0.3 if kick == 14 else 0.0)
            else:
                st = 1.2 + (0.2 if kick == 14 else 0.0)
        else:
            st = 0.9 if hi_hole == 14 else 0.5
    elif cat == 2:
        p1, p2 = tb[0], tb[1]
        in1, in2 = p1 in hset, p2 in hset
        if in1 and in2:
            st = 5.0 if p1 == top else 4.6
        elif in1:
            st = 4.2 if hranks[0] == hranks[1] else 4.0
        elif in2:
            st = 2.6
        else:
            st = 0.8
    elif cat == 3:
        t = tb[0]
        nh = sum(1 for r in hranks if r == t)
        if nh == 2:
            st = 5.6 + (0.2 if t == top else 0.0)
        elif nh == 1:
            kick = max(r for r in hranks if r != t)
            st = 4.9 if kick >= 13 else 4.4
        else:
            st = 0.9 if hi_hole == 14 else 0.7
    elif cat == 4:
        hi = tb[0]
        window = {14, 2, 3, 4, 5} if hi == 5 else set(range(hi - 4, hi + 1))
        used = len(set(r for r in hranks if r in window and r not in bset))
        if used >= 2:
            st = 6.0 + (0.2 if hi == 14 else 0.0)
        elif used == 1:
            st = 5.0
        else:
            st = 1.5
    elif cat == 5:
        fs = None
        cnt = {}
        for _, s in hole + board:
            cnt[s] = cnt.get(s, 0) + 1
        for s, n in cnt.items():
            if n >= 5:
                fs = s
        hs = sorted((c[0] for c in hole if c[1] == fs), reverse=True)
        if not hs:
            st = 1.5
        else:
            th = hs[0]
            st = 6.6 if th == 14 else (6.2 if th >= 12 else (5.6 if th >= 9 else 5.2))
    elif cat == 6:
        t, p = tb
        if t in hset or p in hset:
            st = 6.8 if hranks.count(t) == 2 else 6.4
        else:
            st = 1.5
    elif cat == 7:
        st = 7.0 if tb[0] in hset else (0.9 if hi_hole == 14 else 0.6)
    else:
        st = 7.0

    # board threats: we do not hold the hand that the board makes possible
    if cat < 5:
        if binfo["max_suit"] >= 4:
            st -= 1.0 if st < 5.9 else 0.5
        elif binfo["max_suit"] == 3:
            st -= 0.3
    if cat < 4:
        if binfo["win"] >= 4:
            st -= 0.8 if st < 5.0 else 0.4
        elif binfo["win"] == 3 and st < 4.5:
            st -= 0.2
    if cat in (4, 5) and binfo["paired"]:
        st -= 0.4
    return max(st, 0.0)


def draw_value(hole, board):
    """Draw class 0..3: >= 0.5 weak, >= 1.5 strong (flush draw / open ender),
    >= 2.8 combo draw.  Zero on the river."""
    if len(board) >= 5:
        return 0.0
    dv = 0.0
    # flush draw: exactly four cards of one suit, at least one of them ours
    fv = 0.0
    for s in "shdc":
        hs = [c[0] for c in hole if c[1] == s]
        bs = sum(1 for c in board if c[1] == s)
        if hs and len(hs) + bs == 4:
            if len(hs) == 2:
                v = 2.0
            else:
                v = 1.6 if max(hs) >= 13 else 1.2
            if 14 in hs:
                v += 0.3
            fv = max(fv, v)
    # straight draw: ranks that would complete a straight using one of our cards
    allr = set(c[0] for c in hole + board)
    bset = set(c[0] for c in board)
    hole_unique = set(c[0] for c in hole) - bset
    sv = 0.0
    if not straight_high(allr):
        outs = 0
        for r in range(2, 15):
            if r in allr:
                continue
            h = straight_high(allr | {r})
            if not h:
                continue
            window = {14, 2, 3, 4, 5} if h == 5 else set(range(h - 4, h + 1))
            if hole_unique & window:
                outs += 1
        sv = 1.7 if outs >= 2 else (0.7 if outs == 1 else 0.0)
    dv = min(3.0, fv + sv)
    if dv == 0.0:
        top = max(bset)
        if all(c[0] > top for c in hole):
            dv = 0.5  # two overcards
    return dv


def keep_value(keep, board, st, dv):
    """Value of keeping two cards (used for the discard and for the flop,
    where we know we will keep the best two of our three cards)."""
    v = 10.0 * st + 6.0 * dv
    r1, r2 = keep[0][0], keep[1][0]
    v += 0.1 * (r1 + r2)
    if r1 == r2:
        v += 2.0
    if keep[0][1] == keep[1][1]:
        bs = sum(1 for c in board if c[1] == keep[0][1])
        if bs == 1:
            v += 2.5  # backdoor flush
    if 1 <= abs(r1 - r2) <= 2:
        v += 1.0
    return v


def best_keep(hole3, board, binfo):
    """Try the three 2-card holdings; return (value, discard_index, st, dv)."""
    order = sorted(range(3), key=lambda i: (hole3[i][0], SUIT_ORDER.get(hole3[i][1], 9)))
    best = None
    for i in order:  # lowest card first so ties discard the lowest card
        keep = [hole3[j] for j in range(3) if j != i]
        st = made_strength(keep, board, binfo)
        dv = draw_value(keep, board)
        v = keep_value(keep, board, st, dv)
        if best is None or v > best[0] + 1e-9:
            best = (v, i, st, dv)
    return best


# ---------------------------------------------------------------------------
# Opponent profile (very light)
# ---------------------------------------------------------------------------


class Opp:
    def __init__(self):
        self.pf_opps = 0
        self.pf_raises = 0
        self.post_raise = 0
        self.post_call = 0
        self.my_bets = 0
        self.my_bets_fold = 0

    def update(self, history):
        saw_pf = False
        raised_pf = False
        for e in history:
            if not isinstance(e, dict) or e.get("actor") != "opp":
                continue
            a = e.get("action")
            if e.get("street") == "preflop":
                saw_pf = True
                if a == "raise":
                    raised_pf = True
            elif a == "raise":
                self.post_raise += 1
            elif a == "call":
                self.post_call += 1
        if saw_pf:
            self.pf_opps += 1
            if raised_pf:
                self.pf_raises += 1
        n = len(history)
        for i in range(n):
            e = history[i]
            if not isinstance(e, dict):
                continue
            if e.get("actor") == "me" and e.get("action") == "raise" and e.get("street") != "preflop":
                for j in range(i + 1, n):
                    f = history[j]
                    if not isinstance(f, dict) or f.get("street") != e.get("street"):
                        break
                    if f.get("actor") == "opp":
                        self.my_bets += 1
                        if f.get("action") == "fold":
                            self.my_bets_fold += 1
                        break

    def bluff_mult(self):
        """Scale for bluff frequencies: 1.0 by default, 0 vs a calling
        station, up to 1.5 vs a bot that folds a lot."""
        if self.my_bets < 15:
            return 1.0
        fr = self.my_bets_fold / float(self.my_bets)
        return max(0.0, min(1.5, (fr - 0.2) / 0.35))

    def call_shift(self):
        """Added to the strength needed to continue vs a bet."""
        n = self.post_raise + self.post_call
        if n < 20:
            return 0.0
        agg = self.post_raise / float(n)
        if agg >= 0.5:
            return -0.4
        if agg <= 0.25:
            return 0.4
        return 0.0

    def pf_shift(self):
        """Added to preflop call / 3-bet thresholds."""
        if self.pf_opps < 25:
            return 0.0
        r = self.pf_raises / float(self.pf_opps)
        if r >= 0.6:
            return -1.5
        if r <= 0.25:
            return 1.0
        return 0.0


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------


def act(name, amount=None):
    d = {"type": "action", "action": name}
    if amount is not None:
        d["amount"] = int(amount)
    return d


def need_strength(po):
    """Made-hand strength needed to call, from the pot odds po = call/(pot+call)."""
    if po <= 0.12:
        return 0.5
    if po <= 0.18:
        return 1.0
    if po <= 0.24:
        return 1.8
    if po <= 0.29:
        return 2.2
    if po <= 0.34:
        return 2.7
    if po <= 0.39:
        return 3.4
    if po <= 0.44:
        return 4.0
    return 4.6


def draw_call_limit(dv, street):
    """Largest pot odds at which a draw may call."""
    if dv < 0.5:
        return 0.0
    if street == "flop":
        return 0.15 if dv < 1.5 else (0.33 if dv < 2.8 else 0.43)
    if street == "turn":
        return 0.08 if dv < 1.5 else (0.2 if dv < 2.8 else 0.33)
    return 0.0


def fallback_action(req):
    """Safe legal action used on any error or when time is almost gone."""
    legal = req.get("legal_actions") or []
    if "check" in legal:
        return act("check")
    try:
        to_call = int(req.get("to_call", 0))
        pot = int(req.get("pot", 0))
    except Exception:
        to_call, pot = 0, 0
    if "call" in legal and to_call <= max(2, pot // 4):
        return act("call")
    if "fold" in legal:
        return act("fold")
    if "call" in legal:
        return act("call")
    return act("check")


def lowest_card(cards):
    """The engine's default discard: lowest rank, ties by s, h, d, c."""
    return min(cards, key=lambda c: (RANK_VAL.get(c[0], 0), SUIT_ORDER.get(c[1], 9)))


# ---------------------------------------------------------------------------
# The bot
# ---------------------------------------------------------------------------


class Bot:
    def __init__(self):
        self.rng = random.Random()
        self.opp = Opp()
        self.done = False
        self.seat = "button"
        self.hole = []        # list of (rank, suit); 3 cards before the discard, 2 after
        self.hole_str = []
        self.errors = 0
        self.total_hands = 400

    # -- logging (stderr only, capped well below 64 KB) -----------------------
    def log(self, text):
        if self.errors < 40:
            self.errors += 1
            try:
                sys.stderr.write(text[:300] + "\n")
                sys.stderr.flush()
            except Exception:
                pass

    # -- message dispatch ---------------------------------------------------------
    def handle(self, msg):
        t = msg.get("type")
        if t == "action_request":
            try:
                return self.on_action(msg)
            except Exception as e:  # never let anything escape
                self.log("action error: %r" % (e,))
                try:
                    return fallback_action(msg)
                except Exception:
                    return act("check")
        if t == "discard_request":
            try:
                return self.on_discard(msg)
            except Exception as e:
                self.log("discard error: %r" % (e,))
                return self.safe_discard(msg)
        try:
            if t == "init":
                self.total_hands = int(msg.get("total_hands", 400))
            elif t == "new_hand":
                self.seat = msg.get("seat", "button")
                self.hole_str = list(msg.get("hole_cards", []))
                self.hole = parse_cards(self.hole_str)
            elif t == "discard_result":
                hc = msg.get("hole_cards")
                if hc:
                    self.hole_str = list(hc)
                    self.hole = parse_cards(self.hole_str)
            elif t == "hand_result":
                hist = msg.get("history")
                if isinstance(hist, list):
                    self.opp.update(hist)
            elif t == "match_end":
                self.done = True
        except Exception as e:
            self.log("state error: %r" % (e,))
        return None

    # -- discard ------------------------------------------------------------------
    def safe_discard(self, msg):
        cards = msg.get("hole_cards") or self.hole_str
        try:
            parsed = parse_cards(cards)
            return {"type": "discard", "card": card_str(lowest_card(parsed))}
        except Exception:
            return {"type": "discard", "card": cards[0] if cards else "2c"}

    def on_discard(self, msg):
        cards = list(msg["hole_cards"])
        hole = parse_cards(cards)
        board = parse_cards(msg["board"])
        self.hole_str = cards
        self.hole = hole
        if len(hole) != 3 or not board:
            return self.safe_discard(msg)
        binfo = board_info(board)
        v, idx, st, dv = best_keep(hole, board, binfo)
        return {"type": "discard", "card": cards[idx]}

    # -- actions --------------------------------------------------------------------
    def on_action(self, req):
        try:
            if int(req.get("time_left_ms", 10 ** 9)) < 250:
                return fallback_action(req)  # almost out of time: no thinking
        except Exception:
            pass
        legal = req.get("legal_actions") or []
        if not legal:
            return act("check")
        if not self.hole:
            return fallback_action(req)
        if req.get("street") == "preflop":
            reply = self.preflop(req)
        else:
            reply = self.postflop(req)
        return self.validate(req, reply)

    def validate(self, req, reply):
        """Make sure the reply is legal; otherwise fall back."""
        legal = req.get("legal_actions") or []
        a = reply.get("action")
        if a not in legal:
            return fallback_action(req)
        if a == "raise":
            try:
                lo = int(req["min_raise"])
                hi = int(req["max_raise"])
                amt = int(reply.get("amount", lo))
            except Exception:
                return fallback_action(req)
            amt = max(lo, min(hi, amt))
            return act("raise", amt)
        return act(a)

    def raise_to(self, req, amount):
        """Raise action with the amount clamped; big raises become all-in."""
        lo = int(req["min_raise"])
        hi = int(req["max_raise"])
        amount = int(round(amount))
        if amount >= 0.6 * hi:
            amount = hi
        return act("raise", max(lo, min(hi, amount)))

    def can_raise(self, req):
        return ("raise" in (req.get("legal_actions") or [])
                and "min_raise" in req and "max_raise" in req)

    # -- preflop ---------------------------------------------------------------------
    def preflop(self, req):
        legal = req["legal_actions"]
        to_call = int(req.get("to_call", 0))
        opp_bet = int(req.get("opp_bet", 0))
        raises_left = int(req.get("raises_left", 0))
        can_raise = self.can_raise(req)
        score = preflop_score(self.hole)
        v = 3 - raises_left          # voluntary raises so far (big blind not counted)
        ip = self.seat == "button"
        shift = self.opp.pf_shift()
        r = self.rng.random()

        if to_call == 0:
            # big blind option after a limp
            if can_raise and score >= ISO_RAISE:
                size = 4 * BB if score >= ISO_BIG else 3 * BB
                return self.raise_to(req, size)
            return act("check") if "check" in legal else fallback_action(req)

        if v <= 0:
            # button / small blind, first to act
            if can_raise and score >= OPEN_RAISE:
                return self.raise_to(req, 3 * BB)
            if score >= LIMP_MIN:
                return act("call")
            return act("fold") if "fold" in legal else act("call")

        # facing a raise
        if opp_bet <= 4:
            thr = DEF_TINY
        elif opp_bet <= 8:
            thr = DEF_SMALL
        elif opp_bet <= 14:
            thr = DEF_MED
        elif opp_bet <= 30:
            thr = DEF_BIG
        elif opp_bet <= 80:
            thr = DEF_HUGE
        else:
            thr = DEF_SHOVE
        thr += shift

        if can_raise:
            if v == 1:
                if score >= THREE_BET + max(shift, 0.0):
                    return self.raise_to(req, opp_bet * (3.0 if ip else 3.5))
                if opp_bet <= 8 and 4.9 <= score < 7.5 and r < 0.06:
                    return self.raise_to(req, opp_bet * (3.0 if ip else 3.5))  # light 3-bet
            elif v == 2:
                if score >= JAM:
                    return act("raise", int(req["max_raise"]))
                if score >= FOUR_BET:
                    return self.raise_to(req, opp_bet * 2.3)
            elif score >= JAM:
                return act("raise", int(req["max_raise"]))
        if score >= thr:
            return act("call")
        return act("fold")

    # -- postflop --------------------------------------------------------------------
    def postflop(self, req):
        street = req["street"]
        board = parse_cards(req["board"])
        hole = self.hole
        binfo = board_info(board)
        if len(hole) >= 3:
            _, _, st, dv = best_keep(hole[:3], board, binfo)
            if street == "flop":
                st = max(0.0, st - 0.3)  # the opponent also picks the best of three
        else:
            st = made_strength(hole, board, binfo)
            dv = draw_value(hole, board)

        history = req.get("history") or []
        last_raiser = None
        n_street_raises = 0
        for e in history:
            if isinstance(e, dict) and e.get("action") == "raise":
                last_raiser = e.get("actor")
                if e.get("street") == street:
                    n_street_raises += 1
        initiative = last_raiser == "me"
        ip = self.seat == "button"
        to_call = int(req.get("to_call", 0))
        if to_call <= 0:
            return self.unopened(req, st, dv, binfo, ip, initiative)
        return self.facing_bet(req, st, dv, binfo, ip, n_street_raises)

    def bet(self, req, frac):
        """Bet / raise `frac` of the pot after a call."""
        if not self.can_raise(req):
            return act("check") if "check" in req["legal_actions"] else act("call")
        base = int(req["pot"]) + int(req.get("to_call", 0))
        amount = int(req.get("opp_bet", 0)) + frac * base
        return self.raise_to(req, amount)

    def check(self, req):
        return act("check") if "check" in req["legal_actions"] else fallback_action(req)

    def unopened(self, req, st, dv, binfo, ip, initiative):
        """We may check or bet (no bet to face)."""
        street = req["street"]
        wet = binfo["wet"]
        r = self.rng.random()
        river = street == "river"
        bm = self.opp.bluff_mult()
        val_frac = 0.5 + 0.12 * wet

        if st >= 5.5:
            if (not river) and wet == 0 and r < 0.15:
                return self.check(req)  # occasional slow play on a dry board
            return self.bet(req, 0.9 if river else val_frac + 0.15)
        if st >= 4.0:
            return self.bet(req, val_frac) if r < 0.92 else self.check(req)
        if st >= 3.0:
            if river:
                p, frac = (0.45 if st >= 3.5 else 0.2), 0.4
            elif street == "turn":
                p, frac = (0.6 if ip else 0.4) + 0.1 * wet, 0.5
            else:
                p, frac = (0.75 if ip else 0.55) + 0.08 * wet, 0.5
            return self.bet(req, frac) if r < p else self.check(req)
        if dv >= 1.5 and not river:
            if street == "flop":
                p = 0.6 if ip else 0.5
            else:
                p = 0.45 if ip else 0.35
            if dv >= 2.8:
                p += 0.25
            p *= min(1.0, max(0.5, bm))
            return self.bet(req, 0.6) if r < p else self.check(req)
        # weak made hands and air: occasional small bluffs
        if street == "flop":
            base = 0.40 if ip else 0.15
        elif street == "turn":
            base = 0.28 if ip else 0.10
        else:
            base = 0.22 if ip else 0.08
        if wet >= 2:
            base *= 0.7
        if st >= 2.0:
            base *= 0.5
        if dv >= 0.5:
            base *= 1.3
        if not initiative:
            base *= 0.8  # no story to tell if the opponent was the last aggressor
        p = min(0.8, base * bm)
        if r < p:
            return self.bet(req, 0.33 if street == "flop" else 0.5)
        return self.check(req)

    def facing_bet(self, req, st, dv, binfo, ip, n_street_raises):
        """We face a bet / raise: raise, call or fold."""
        street = req["street"]
        pot = int(req["pot"])
        to_call = int(req["to_call"])
        r = self.rng.random()
        can_raise = self.can_raise(req) and int(req.get("raises_left", 0)) > 0
        po = to_call / float(max(1, pot + to_call))
        ratio = to_call / float(max(1, pot - to_call))
        bm = self.opp.bluff_mult()

        need = need_strength(po) + self.opp.call_shift()
        if street == "turn":
            need += 0.2
        elif street == "river":
            need += 0.5
        if n_street_raises >= 2:
            need += 0.6

        river = street == "river"
        # value raises
        if can_raise:
            if st >= 6.0:
                if r < 0.8:
                    return self.bet(req, 1.0)
            elif st >= 5.0:
                if (not river) and ratio <= 0.8 and r < 0.3 and n_street_raises < 2:
                    return self.bet(req, 0.75)
                if river and ratio <= 0.5 and r < 0.3:
                    return self.bet(req, 0.75)
            # semi-bluff raise with a strong draw
            if (not river) and dv >= 1.5 and int(req.get("raises_left", 0)) >= 2 \
                    and ratio <= 0.75 and n_street_raises < 2:
                p = (0.35 if dv >= 2.8 else 0.2) * min(1.0, max(0.5, bm))
                if r < p:
                    return self.bet(req, 0.75)
        if st >= need:
            return act("call")
        if po <= draw_call_limit(dv, street):
            return act("call")
        return act("fold")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def main():
    bot = Bot()
    while True:
        try:
            line = sys.stdin.readline()
        except Exception:
            break
        if not line:
            break  # EOF: the engine is gone
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        try:
            reply = bot.handle(msg)
        except Exception as e:  # last line of defence
            bot.log("fatal handler error: %r" % (e,))
            reply = None
            t = msg.get("type")
            if t == "action_request":
                reply = act("check") if "check" in (msg.get("legal_actions") or []) else act("fold")
            elif t == "discard_request":
                try:
                    reply = {"type": "discard", "card": msg["hole_cards"][0]}
                except Exception:
                    reply = None
        if reply is not None:
            try:
                send(reply)
            except Exception:
                break  # stdout closed
        if bot.done:
            break


if __name__ == "__main__":
    main()

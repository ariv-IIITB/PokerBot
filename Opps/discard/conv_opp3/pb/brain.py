"""Brain: the engine-independent bot, driven by bot.py (the protocol layer).

Public API
    b = Brain(); b.new_match(total_hands, bank_per_400=60.0)
    b.new_hand(hand_no, hole, button)           (hole = 3 cards; optional, act() starts a hand if needed)
    action = b.act(obs)                          never raises, always returns a legal action
    card = b.discard(hole, board, time_left, hands_left)   which of the 3 hole cards to throw away
    b.discard_result(my_discard, opp_discard, hole, board) both discards are public now
    b.hand_over(HandResult)
"""
import math
import random

import numpy as np

from . import strategy
from .equity import COMBO_ID, N_COMBOS, equity, keep_equities, keeps
from .opponent import OppModel
from .ranges import BoardInfo, PF_COMBO_EQ, RangeTracker, pf_percentile
from .strategy import Ctx, legalize, panic_action
from .timing import Clock, now
from .types import CALL, CHECK, FOLD, RAISE


class _Hand:
    __slots__ = ("hand_no", "hole", "button", "prev_obs", "last_act", "raise_level",
                 "aggr_street", "opp_aggr_river", "opp_acted_events", "s_hand", "opened",
                 "dead")

    def __init__(self, hand_no, hole, button):
        self.hand_no = hand_no
        self.hole = tuple(hole)
        self.button = bool(button)
        self.prev_obs = None
        self.last_act = None
        self.raise_level = 0           # preflop raises so far (both players)
        self.aggr_street = {}          # street -> we bet/raised there
        self.opp_aggr_river = False
        self.opp_acted_events = 0
        self.s_hand = 0.5
        self.opened = False
        self.dead = ()                 # the two discards, once they are public


class Brain:
    name = "brain"

    def __init__(self, max_samples=900, seed=20240607, fold_out=False):
        self.max_samples = max_samples
        self.seed = seed
        self.fold_out = fold_out
        self.new_match(400)

    # ------------------------------------------------------------ lifecycle
    def new_match(self, total_hands=400, bank_per_400=60.0):
        self.total_hands = total_hands
        self.opp = OppModel()
        self.clock = Clock(total_hands, bank_per_400)
        self.rng = random.Random(self.seed)
        self.nprng = np.random.default_rng(self.seed)
        self.rt = RangeTracker()
        self.h = None
        self.crashes = 0
        self.panic_decisions = 0

    def new_hand(self, hand_no, hole, button):
        self.h = _Hand(hand_no, hole, button)
        try:
            self.rt.reset(self.h.hole)
            self.h.s_hand = pf_percentile(self.h.hole)
        except Exception:
            self.crashes += 1

    # ------------------------------------------------------------ main entry
    def act(self, obs):
        t0 = now()
        try:
            act = self._act(obs, t0)
        except Exception:
            self.crashes += 1
            act = self._safe_fallback(obs)
        try:
            act = legalize(obs, act)
        except Exception:
            act = (CHECK,) if getattr(obs, "can_check", False) else (FOLD,)
        try:
            h = self.h
            if h is not None:
                h.prev_obs = obs
                h.last_act = act
                if act[0] == RAISE:
                    h.aggr_street[obs.street] = True
                    if obs.street == 0:
                        h.raise_level += 1
        except Exception:
            pass
        self.clock.charge(now() - t0)
        return act

    def _safe_fallback(self, obs):
        try:
            s = self.h.s_hand if self.h else 0.5
            return panic_action(obs, s)
        except Exception:
            return (CHECK,) if obs.can_check else (FOLD,)

    # ------------------------------------------------------------ core
    def _act(self, obs, t0):
        if self.h is None or self.h.hand_no != obs.hand_no:
            self.new_hand(obs.hand_no, obs.hole, obs.button)
        h = self.h

        mode = self.clock.mode(obs.time_left, obs.hands_left)
        if mode == "panic":
            self.panic_decisions += 1
            return panic_action(obs, h.s_hand)

        # provably-won match: stop risking chips (blind losses cannot overturn the lead)
        if self.fold_out and obs.hands_left > 0:
            cost = (3 * obs.hands_left + 1) // 2 + 3
            if obs.bankroll > cost + 2:
                return (CHECK,) if obs.can_check else (FOLD,)

        lean = (mode == "lean")
        self._observe(obs, lean)

        bb = obs.big_blind
        unopened = obs.street == 0 and obs.button and obs.hero_pip < bb and obs.opp_pip <= bb
        bb_vs_limp = obs.street == 0 and (not obs.button) and obs.to_call == 0 and obs.opp_pip <= bb
        eq = 0.5
        if not (unopened or bb_vs_limp):
            budget = self.clock.budget(obs.time_left, obs.hands_left, obs.street)
            mult = len(keeps(obs.hole))          # a 3-card hand is scored once per possible keep
            n = self.clock.samples(budget / mult, lo=80, hi=(150 if lean else self.max_samples // mult))
            te = now()
            eq, _ = equity(obs.hole, obs.board, self.rt.w, n, self.nprng, dead=obs.dead)
            self.clock.observe(now() - te, n * mult)

        ctx = Ctx(self.opp, self.rng, s_hand=h.s_hand, risk=self._risk(obs),
                  aggr_prev=h.aggr_street.get(obs.street - 1, False),
                  suited_or_ace=self._suited_or_ace(obs.hole), eq=eq)
        return strategy.decide(obs, eq, ctx)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _suited_or_ace(hole):
        suits = [c // 13 for c in hole]
        return any(c % 13 == 12 for c in hole) or len(set(suits)) < len(suits)

    def _risk(self, obs):
        hl = max(obs.hands_left, 1)
        z = obs.bankroll / (25.0 * math.sqrt(hl))
        if z > 2.0:
            return 1
        if z < -2.0 and hl < 150:
            return -1
        return 0

    # ------------------------------------------------------------ opponent inference
    def _observe(self, obs, lean):
        h, opp, rt = self.h, self.opp, self.rt
        prev, la = h.prev_obs, h.last_act
        bb = obs.big_blind
        old_events = []      # (kind, board, f, level) belonging to the previous street
        new_events = []      # belonging to the current street

        def facing_f():
            return obs.to_call / float(max(1, obs.pot - obs.to_call))

        if prev is None:
            if obs.street == 0 and not obs.button:
                if obs.to_call > 0 and obs.opp_pip > bb:
                    opp.pf_open.add(True)
                    h.raise_level = 1
                    new_events.append(("open", obs.board, 0.0, 1))
                elif obs.to_call == 0:
                    opp.pf_open.add(False)
                    new_events.append(("limp", obs.board, 0.0, 0))
        elif la is not None:
            lk = la[0]
            if obs.street == prev.street:
                if lk == RAISE and obs.to_call > 0:
                    if obs.street == 0:
                        lvl = h.raise_level + 1
                        h.raise_level = lvl
                        if lvl == 2:
                            opp.pf_3bet.add(True)
                            opp.pf_defend.add(True)
                            opp.pf_fold_to_open.add(False)
                        else:
                            opp.pf_fold_to_3bet.add(False)
                        new_events.append(("pf_reraise", obs.board, 0.0, lvl))
                    else:
                        opp.fold_to_bet.add(False)
                        opp.fold_to_raise.add(False)
                        opp.bet.add(True)
                        new_events.append(("raise", obs.board, facing_f(), 0))
                        if obs.street == 3:
                            h.opp_aggr_river = True
                elif lk == CHECK and obs.to_call > 0 and obs.street > 0:
                    opp.bet.add(True)
                    new_events.append(("bet", obs.board, facing_f(), 0))
                    if obs.street == 3:
                        h.opp_aggr_river = True
                elif lk == CALL and obs.street == 0 and obs.to_call > 0:
                    # we limped, BB isolated us
                    h.raise_level += 1
                    new_events.append(("iso", obs.board, 0.0, 1))
            else:
                # the street advanced: close out the previous street
                pb = prev.board
                if lk == RAISE:
                    if prev.street == 0:
                        if h.raise_level <= 1:
                            opp.pf_defend.add(True)
                            opp.pf_fold_to_open.add(False)
                            old_events.append(("pf_call", pb, 0.0, 1))
                        else:
                            opp.pf_fold_to_3bet.add(False)
                            old_events.append(("pf_call3", pb, 0.0, h.raise_level))
                    else:
                        opp.fold_to_bet.add(False)
                        old_events.append(("call", pb, self._our_f(prev, la), 0))
                elif lk == CHECK:
                    if prev.street > 0:
                        opp.bet.add(False)
                        old_events.append(("check", pb, 0.0, 0))
                elif lk == CALL:
                    if prev.street == 0 and h.raise_level == 0:
                        old_events.append(("pf_check", pb, 0.0, 0))
                # first action on the new street
                if obs.to_call > 0:
                    opp.bet.add(True)
                    new_events.append(("bet", obs.board, facing_f(), 0))
                    if obs.street == 3:
                        h.opp_aggr_river = True
                elif obs.button:
                    opp.bet.add(False)
                    new_events.append(("check", obs.board, 0.0, 0))

        if lean:
            if len(obs.board):
                rt.block(obs.board)
            return
        for kind, board, f, lvl in old_events:
            rt.update(kind, board, opp, f=f, level=lvl)
        if len(obs.board):
            rt.block(obs.board)
        for kind, board, f, lvl in new_events:
            rt.update(kind, board, opp, f=f, level=lvl)

    @staticmethod
    def _our_f(prev, la):
        """Our bet size as a fraction of the pot it was made into (for 'opp called' likelihood)."""
        amt = max(0, la[1] - prev.hero_pip) if len(la) > 1 else 0
        base = max(1, prev.pot)
        return amt / float(base)

    # ------------------------------------------------------------ discard
    def discard(self, hole, board, time_left, hands_left):
        """Index into `hole` of the card to throw away: keep the 2-card hand with the best
        equity against the opponent's range on this flop (sampled, same runouts for all three)."""
        t0 = now()
        try:
            idx = self._discard(hole, board, time_left, hands_left)
        except Exception:
            self.crashes += 1
            idx = self._discard_heuristic(hole, board)
        self.clock.charge(now() - t0)
        return idx

    def _discard(self, hole, board, time_left, hands_left):
        if self.clock.mode(time_left, hands_left) == "panic":
            return self._discard_heuristic(hole, board)
        budget = self.clock.budget(time_left, hands_left, 1) * 0.9
        lean = self.clock.mode(time_left, hands_left) == "lean"
        n = self.clock.samples(budget / 3.0, lo=80, hi=(150 if lean else self.max_samples // 3))
        te = now()
        options, eqs = keep_equities(hole, board, self.rt.w, n, self.nprng)
        self.clock.observe(now() - te, n * 3)
        best = max(range(len(options)), key=lambda i: eqs[i])
        kept = options[best]
        return [i for i, c in enumerate(hole) if c not in kept][0]

    @staticmethod
    def _discard_heuristic(hole, board):
        """No simulation: keep the pair with the best preflop equity, plus a bonus for
        cards that pair the board."""
        best_i, best_v = 0, -1.0
        ranks = {c % 13 for c in board}
        for i in range(len(hole)):
            keep = [c for j, c in enumerate(hole) if j != i]
            v = PF_COMBO_EQ[COMBO_ID[keep[0], keep[1]]] + 0.15 * sum(1 for c in keep if c % 13 in ranks)
            if v > best_v:
                best_i, best_v = i, v
        return best_i

    def discard_result(self, my_discard, opp_discard, hole, board):
        """Both discards are public: they are out of play, and the opponent's tells us what
        it chose not to keep."""
        try:
            h = self.h
            if h is None:
                return
            h.hole = tuple(hole)
            h.dead = (my_discard, opp_discard)
            self.rt.block([my_discard])
            if len(board):
                self.rt.apply_discard(board, opp_discard)
            else:
                self.rt.block([opp_discard])
        except Exception:
            self.crashes += 1

    # ------------------------------------------------------------ end of hand
    def hand_over(self, result):
        try:
            self._hand_over(result)
        except Exception:
            self.crashes += 1

    def _hand_over(self, result):
        h, opp = self.h, self.opp
        if h is None:
            return
        opp.hands += 1
        prev, la = h.prev_obs, h.last_act
        showdown = result.opp_hole is not None and len(result.opp_hole) == 2
        opp_folded = (not showdown) and (not result.hero_folded)

        if prev is None:
            # we never had to act: only possible as BB when the SB folded
            if opp_folded and not h.button:
                opp.pf_open.add(False)
            return

        lk = la[0] if la else None
        if opp_folded and lk == RAISE:
            if prev.street == 0:
                if h.raise_level <= 1:
                    opp.pf_fold_to_open.add(True)
                    opp.pf_defend.add(False)
                else:
                    opp.pf_fold_to_3bet.add(True)
            else:
                opp.fold_to_bet.add(True)
        elif showdown:
            if lk == RAISE:
                if prev.street == 0:
                    if h.raise_level <= 1:
                        opp.pf_fold_to_open.add(False)
                        opp.pf_defend.add(True)
                else:
                    opp.fold_to_bet.add(False)
            elif lk == CHECK and prev.street > 0:
                opp.bet.add(False)
            if h.opp_aggr_river and len(result.board) == 5:
                try:
                    opp.river_bluff.add(self._opp_pct(result.opp_hole, result.board) < 0.35)
                except Exception:
                    pass

    @staticmethod
    def _opp_pct(opp_hole, board):
        bi = BoardInfo(board)
        a, b = sorted(opp_hole)
        cid = int(COMBO_ID[a, b])
        pos = int(np.nonzero(bi.live == cid)[0][0])
        mine = bi.inv[pos]
        below = (bi.inv < mine).sum() + 0.5 * (bi.inv == mine).sum()
        return float(below) / len(bi.inv)

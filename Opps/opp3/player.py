"""
Tournament entry point (adapter between the engine skeleton and the engine-independent Brain).

ASSUMPTION: the starter code follows the MIT Pokerbots skeleton API
(skeleton.actions / states / bot / runner, Bot.handle_new_round / handle_round_over /
get_action). If your starter code differs, ONLY this file needs changing: convert the
engine state into `pb.types.Obs`, call brain.act(obs), convert the returned tuple back.
"""
from skeleton.actions import CallAction, CheckAction, FoldAction, RaiseAction
from skeleton.main_bot import Bot
from skeleton.runner import parse_args, run_bot
from skeleton.states import BIG_BLIND, NUM_ROUNDS, SMALL_BLIND, STARTING_STACK

from pb.brain import Brain
from pb.cards import parse
from pb.types import CALL, CHECK, FOLD, RAISE, HandResult, Obs

_STREET_INDEX = {0: 0, 3: 1, 4: 2, 5: 3}


def _cards(strs):
    out = []
    for s in strs:
        try:
            out.append(parse(s))
        except Exception:
            pass
    return tuple(out)


class Player(Bot):
    def __init__(self):
        self.brain = Brain()
        self.brain.new_match(NUM_ROUNDS)
        self._clock_synced = False

    # ------------------------------------------------------------------ rounds
    def handle_new_round(self, game_state, round_state, active):
        try:
            if not self._clock_synced:
                bank = float(game_state.game_clock)
                self.brain.clock.initial_bank = bank
                self.brain.clock.reserve = max(1.5, 0.10 * bank)
                self._clock_synced = True
            self.brain.new_hand(game_state.round_num, _cards(round_state.hands[active]), active == 0)
        except Exception:
            pass

    def handle_round_over(self, game_state, terminal_state, active):
        try:
            prev = terminal_state.previous_state
            opp = _cards(prev.hands[1 - active]) if prev.hands[1 - active] else ()
            h = self.brain.h
            folded = bool(h and h.last_act and h.last_act[0] == FOLD)
            board = _cards(prev.deck[:prev.street])
            self.brain.hand_over(HandResult(delta=terminal_state.deltas[active],
                                            opp_hole=opp if len(opp) == 2 else None,
                                            board=board, hero_folded=folded))
        except Exception:
            pass

    # ------------------------------------------------------------------ decisions
    def get_action(self, game_state, round_state, active):
        try:
            legal = round_state.legal_actions()
        except Exception:
            legal = {FoldAction, CallAction, CheckAction}
        try:
            obs = self._build_obs(game_state, round_state, active, legal)
            act = self.brain.act(obs)
            kind = act[0]
            if kind == RAISE and RaiseAction in legal:
                lo, hi = round_state.raise_bounds()
                return RaiseAction(int(max(lo, min(hi, act[1]))))
            if kind == CHECK and CheckAction in legal:
                return CheckAction()
            if kind == CALL and CallAction in legal:
                return CallAction()
            if kind == FOLD and FoldAction in legal:
                return FoldAction()
        except Exception:
            pass
        # last-resort safe action (must never raise)
        try:
            if CheckAction in legal:
                return CheckAction()
            if CallAction in legal and round_state.pips[1 - active] - round_state.pips[active] <= 2:
                return CallAction()
        except Exception:
            pass
        return FoldAction()

    @staticmethod
    def _build_obs(gs, rs, active, legal):
        street_cards = rs.street
        hole = _cards(rs.hands[active])
        board = _cards(rs.deck[:street_cards])
        my_pip, opp_pip = rs.pips[active], rs.pips[1 - active]
        my_stack, opp_stack = rs.stacks[active], rs.stacks[1 - active]
        can_raise = RaiseAction in legal
        lo = hi = 0
        if can_raise:
            lo, hi = rs.raise_bounds()
        return Obs(
            hand_no=gs.round_num, hole=hole, board=board,
            street=_STREET_INDEX.get(street_cards, 0), button=(active == 0),
            pot=2 * STARTING_STACK - my_stack - opp_stack,
            hero_pip=my_pip, opp_pip=opp_pip, hero_stack=my_stack, opp_stack=opp_stack,
            to_call=opp_pip - my_pip, min_raise=lo, max_raise=hi,
            can_check=CheckAction in legal, can_raise=can_raise,
            can_call=CallAction in legal, can_fold=FoldAction in legal,
            time_left=float(gs.game_clock), hands_left=max(1, NUM_ROUNDS - gs.round_num + 1),
            bankroll=gs.bankroll, big_blind=BIG_BLIND, small_blind=SMALL_BLIND,
            start_stack=STARTING_STACK)


if __name__ == "__main__":
    run_bot(Player(), parse_args())

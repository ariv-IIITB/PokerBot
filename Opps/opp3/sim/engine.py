"""Local heads-up no-limit hold'em engine (MIT-pokerbots-style rules).

Rules mirrored: stacks reset to START_STACK every hand, SB = button acts first
preflop and last postflop, minimum raise = max(last raise size, big blind),
raise_to semantics = total chips on the street, all-in runouts, split pots.
This is NOT the official tournament engine; use it for relative testing only.
"""
import time

from pb.types import CALL, CHECK, FOLD, RAISE, HandResult, Obs
from pb.evaluator import evaluate

import numpy as np


class BotFault(Exception):
    pass


class Seat:
    """Wraps a bot with time-bank and fault accounting."""

    def __init__(self, bot, bank):
        self.bot = bot
        self.bank = bank
        self.used = 0.0
        self.max_decision = 0.0
        self.decisions = 0
        self.crashes = 0
        self.illegal = 0
        self.timed_out = False

    @property
    def time_left(self):
        return self.bank - self.used

    def call(self, fn, *a):
        t = time.perf_counter()
        try:
            return fn(*a)
        except Exception:
            self.crashes += 1
            raise BotFault()
        finally:
            dt = time.perf_counter() - t
            self.used += dt
            self.max_decision = max(self.max_decision, dt)
            if self.used > self.bank:
                self.timed_out = True


class Engine:
    def __init__(self, stack=400, sb=1, bb=2):
        self.stack, self.sb, self.bb = stack, sb, bb

    # ------------------------------------------------------------------
    def play_hand(self, seats, button_seat, holes, board5, hand_no, hands_left, bankrolls):
        """Play one hand. `seats` = [Seat, Seat]; `holes[i]` = 2 cards for seat i.

        Returns (delta_seat0, delta_seat1). Bots that crash/time out fold.
        """
        S, SB, BB = self.stack, self.sb, self.bb
        stacks = [S, S]
        pips = [0, 0]
        sb_seat, bb_seat = button_seat, 1 - button_seat
        pips[sb_seat], pips[bb_seat] = SB, BB
        stacks[sb_seat] -= SB
        stacks[bb_seat] -= BB

        for i in (0, 1):
            try:
                seats[i].call(seats[i].bot.new_hand, hand_no, tuple(holes[i]), i == button_seat)
            except BotFault:
                pass

        folded = None
        street = 0
        last_actions = [None, None]
        while True:
            board = tuple(board5[:(0, 3, 4, 5)[street]])
            to_act = button_seat if street == 0 else 1 - button_seat
            acted = [False, False]
            betting = stacks[0] > 0 and stacks[1] > 0
            while betting:
                i = to_act
                to_call = pips[1 - i] - pips[i]
                if to_call == 0:
                    can_check = True
                    can_raise = stacks[0] > 0 and stacks[1] > 0
                else:
                    can_check = False
                    can_raise = not (to_call >= stacks[i] or stacks[1 - i] == 0)
                max_contrib = min(stacks[i], stacks[1 - i] + to_call)
                min_contrib = min(max_contrib, to_call + max(to_call, BB))
                min_raise = pips[i] + min_contrib if can_raise else 0
                max_raise = pips[i] + max_contrib if can_raise else 0
                pot = 2 * S - stacks[0] - stacks[1]
                obs = Obs(hand_no=hand_no, hole=tuple(holes[i]), board=board, street=street,
                          button=(i == button_seat), pot=pot, hero_pip=pips[i], opp_pip=pips[1 - i],
                          hero_stack=stacks[i], opp_stack=stacks[1 - i], to_call=to_call,
                          min_raise=min_raise, max_raise=max_raise, can_check=can_check,
                          can_raise=can_raise, can_call=(to_call > 0), can_fold=(to_call > 0),
                          time_left=seats[i].time_left, hands_left=hands_left,
                          bankroll=bankrolls[i], big_blind=BB, small_blind=SB, start_stack=S)
                seats[i].decisions += 1
                try:
                    if seats[i].timed_out:
                        raise BotFault()
                    act = seats[i].call(seats[i].bot.act, obs)
                except BotFault:
                    act = (FOLD,)
                kind = act[0] if act else FOLD
                # --- validate (illegal -> check if free else fold, like the real engine)
                if kind == RAISE and (not can_raise or len(act) < 2 or
                                      not (min_raise <= act[1] <= max_raise)):
                    seats[i].illegal += 1
                    kind = CHECK if can_check else FOLD
                elif kind == CHECK and not can_check:
                    seats[i].illegal += 1
                    kind = FOLD
                elif kind == CALL and to_call == 0:
                    seats[i].illegal += 1
                    kind = CHECK
                elif kind not in (FOLD, CHECK, CALL, RAISE):
                    seats[i].illegal += 1
                    kind = CHECK if can_check else FOLD
                last_actions[i] = kind

                if kind == FOLD:
                    folded = i
                    break
                if kind == CHECK:
                    acted[i] = True
                    if acted[1 - i]:
                        break
                    to_act = 1 - i
                elif kind == CALL:
                    pay = min(to_call, stacks[i])
                    stacks[i] -= pay
                    pips[i] += pay
                    acted[i] = True
                    if acted[1 - i]:
                        break
                    if street == 0 and i == sb_seat and not acted[1 - i]:
                        to_act = 1 - i              # SB limped: BB still has the option
                    else:
                        break
                else:  # RAISE
                    amt = act[1]
                    pay = amt - pips[i]
                    stacks[i] -= pay
                    pips[i] = amt
                    acted[i] = True
                    acted[1 - i] = False
                    to_act = 1 - i
            if folded is not None:
                break
            if street == 3:
                break
            street += 1
            pips = [0, 0]

        pot = 2 * S - stacks[0] - stacks[1]
        contrib = [S - stacks[0], S - stacks[1]]
        opp_hole_for = [None, None]
        if folded is not None:
            win = 1 - folded
            d = [0, 0]
            d[win] = contrib[folded]
            d[folded] = -contrib[folded]
            result_board = tuple(board5[:(0, 3, 4, 5)[min(street, 3)]])
        else:
            full = np.array([list(holes[0]) + list(board5), list(holes[1]) + list(board5)])
            sc = evaluate(full)
            matched = min(contrib)
            if sc[0] > sc[1]:
                d = [matched, -matched]
            elif sc[1] > sc[0]:
                d = [-matched, matched]
            else:
                d = [0, 0]
            opp_hole_for = [tuple(holes[1]), tuple(holes[0])]
            result_board = tuple(board5)
        for i in (0, 1):
            try:
                seats[i].call(seats[i].bot.hand_over,
                              HandResult(delta=d[i], opp_hole=opp_hole_for[i], board=result_board,
                                         hero_folded=(folded == i)))
            except BotFault:
                pass
        return d[0], d[1]

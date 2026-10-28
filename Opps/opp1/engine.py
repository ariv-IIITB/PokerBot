"""
Complete Heads-Up No-Limit Texas Hold'em Engine.
Features:
- Full standard NLHE rule enforcement
- Duplicate deal generation and replay
- Strict time bank accounting (default 60s per match)
- In-memory execution (read-only filesystem compliant)
- Detailed match analytics (chips, bb/100, win rate, time consumed)
"""

import time
import random
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction
from skeleton.states import (
    GameState,
    TerminalState,
    RoundState,
    STARTING_STACK,
    BIG_BLIND,
    SMALL_BLIND,
)
from skeleton.evaluate import ALL_CARDS, INT_TO_CARD, evaluate_hand


class DuplicateDeal:
    """Holds a predetermined deal for duplicate poker matches."""
    def __init__(self, hand_a, hand_b, board):
        self.hand_a = hand_a  # 2 card strings
        self.hand_b = hand_b  # 2 card strings
        self.board = board    # 5 card strings

    @classmethod
    def generate_random(cls):
        deck = list(ALL_CARDS)
        random.shuffle(deck)
        hand_a = [INT_TO_CARD[c] for c in deck[0:2]]
        hand_b = [INT_TO_CARD[c] for c in deck[2:4]]
        board = [INT_TO_CARD[c] for c in deck[4:9]]
        return cls(hand_a, hand_b, board)


class MatchEngine:
    """
    Runs heads-up poker matches with duplicate deals between two bots.
    """

    def __init__(self, bot1, bot2, total_rounds=400, time_bank=60.0):
        self.bots = [bot1, bot2]
        self.bot_names = [bot1.__class__.__name__, bot2.__class__.__name__]
        self.total_rounds = total_rounds
        self.clocks = [float(time_bank), float(time_bank)]
        self.bankrolls = [0, 0]
        self.hands_played = 0
        self.stats = [
            {"vpip_count": 0, "pfr_count": 0, "cbet_count": 0, "hands": 0, "timeouts": 0},
            {"vpip_count": 0, "pfr_count": 0, "cbet_count": 0, "hands": 0, "timeouts": 0},
        ]

    def _call_bot_safe(self, bot_idx, fn_name, *args):
        """Calls a bot method with strict time bank tracking and exception safety."""
        bot = self.bots[bot_idx]
        t0 = time.perf_counter()
        result = None
        try:
            method = getattr(bot, fn_name)
            result = method(*args)
        except Exception as e:
            result = None
        elapsed = time.perf_counter() - t0
        self.clocks[bot_idx] = max(0.0, self.clocks[bot_idx] - elapsed)
        if self.clocks[bot_idx] <= 0:
            self.stats[bot_idx]["timeouts"] += 1
        return result

    def play_hand(self, deal, button_idx, round_num):
        """
        Plays a single hand of heads-up NLHE.
        button_idx: index (0 or 1) of the player who has the Button (posts SB).
        bb_idx: 1 - button_idx (posts BB).
        deal: DuplicateDeal instance.
        """
        bb_idx = 1 - button_idx

        # Assign cards based on button role
        # button gets hand_a, bb gets hand_b
        p0_cards = deal.hand_a if button_idx == 0 else deal.hand_b
        p1_cards = deal.hand_b if button_idx == 0 else deal.hand_a

        hands = [p0_cards, p1_cards]

        pips = [0, 0]
        stacks = [STARTING_STACK, STARTING_STACK]

        # Post blinds
        pips[button_idx] = SMALL_BLIND
        stacks[button_idx] -= SMALL_BLIND

        pips[bb_idx] = BIG_BLIND
        stacks[bb_idx] -= BIG_BLIND

        round_state = RoundState(
            button=button_idx,
            street=0,
            pips=list(pips),
            stacks=list(stacks),
            hands=[p0_cards, p1_cards],
            deck=[],
            previous_state=None,
        )

        # Notify bots of new round
        for i in range(2):
            g_state = GameState(self.bankrolls[i], self.clocks[i], round_num)
            view_state = RoundState(
                button=button_idx,
                street=0,
                pips=list(pips),
                stacks=list(stacks),
                hands=[p0_cards if i == 0 else None, p1_cards if i == 1 else None],
                deck=[],
                previous_state=None,
            )
            self._call_bot_safe(i, "handle_new_round", g_state, view_state, i)

        # Betting rounds: 0=preflop, 3=flop, 4=turn, 5=river
        street_board_lens = {0: 0, 3: 3, 4: 4, 5: 5}
        streets = [0, 3, 4, 5]

        folded = False
        folder = None

        for street_idx, street in enumerate(streets):
            board = deal.board[:street_board_lens[street]]
            if street > 0:
                # Reset pips for new street
                pips = [0, 0]

            round_state = RoundState(
                button=button_idx,
                street=street,
                pips=list(pips),
                stacks=list(stacks),
                hands=hands,
                deck=board,
                previous_state=round_state,
            )

            # Check if all-in reached
            if stacks[0] == 0 or stacks[1] == 0:
                # Board runs out automatically
                continue

            # In heads up:
            # Preflop (street 0): Button acts first
            # Postflop (streets 3,4,5): Non-button (BB) acts first
            current_actor = button_idx if street == 0 else bb_idx

            street_actions = 0
            while True:
                # Both players matched pips and both have had chance to act
                if street_actions >= 2 and pips[0] == pips[1]:
                    break

                # If one player called all-in
                if street_actions >= 1 and (stacks[current_actor] == 0 or stacks[1 - current_actor] == 0) and pips[0] == pips[1]:
                    break

                continue_cost = pips[1 - current_actor] - pips[current_actor]
                legal = round_state.legal_actions()

                g_state = GameState(self.bankrolls[current_actor], self.clocks[current_actor], round_num)
                view_state = RoundState(
                    button=button_idx,
                    street=street,
                    pips=list(pips),
                    stacks=list(stacks),
                    hands=[p0_cards if current_actor == 0 else None, p1_cards if current_actor == 1 else None],
                    deck=board,
                    previous_state=round_state,
                )

                # If time ran out, bot can only check or fold
                if self.clocks[current_actor] <= 0:
                    action = CheckAction() if continue_cost == 0 else FoldAction()
                else:
                    action = self._call_bot_safe(current_actor, "get_action", g_state, view_state, current_actor)

                # Validate action
                if action is None:
                    action = CheckAction() if continue_cost == 0 else FoldAction()

                # Enforce legal action
                if isinstance(action, FoldAction):
                    if continue_cost == 0:
                        # Free to check, never fold
                        action = CheckAction()
                    else:
                        folded = True
                        folder = current_actor
                        break

                if isinstance(action, CheckAction):
                    if continue_cost > 0:
                        # Cannot check facing a bet -> fold
                        folded = True
                        folder = current_actor
                        break

                if isinstance(action, CallAction):
                    call_amount = min(continue_cost, stacks[current_actor])
                    pips[current_actor] += call_amount
                    stacks[current_actor] -= call_amount
                    street_actions += 1
                    current_actor = 1 - current_actor

                elif isinstance(action, RaiseAction):
                    min_raise, max_raise = round_state.raise_bounds()
                    if max_raise <= pips[current_actor]:
                        # Cannot raise, call instead
                        call_amount = min(continue_cost, stacks[current_actor])
                        pips[current_actor] += call_amount
                        stacks[current_actor] -= call_amount
                    else:
                        raise_to = max(min_raise, min(int(action.amount), max_raise))
                        additional = raise_to - pips[current_actor]
                        additional = min(additional, stacks[current_actor])
                        pips[current_actor] += additional
                        stacks[current_actor] -= additional

                    street_actions += 1
                    current_actor = 1 - current_actor

                elif isinstance(action, CheckAction):
                    street_actions += 1
                    current_actor = 1 - current_actor

                round_state = RoundState(
                    button=button_idx,
                    street=street,
                    pips=list(pips),
                    stacks=list(stacks),
                    hands=hands,
                    deck=board,
                    previous_state=round_state,
                )

            if folded:
                break

        # Calculate chip outcome
        # Total committed by each player
        committed_0 = STARTING_STACK - stacks[0]
        committed_1 = STARTING_STACK - stacks[1]
        pot = committed_0 + committed_1

        if folded:
            winner = 1 - folder
            deltas = [0, 0]
            deltas[winner] = pot - (committed_0 if winner == 0 else committed_1)
            deltas[folder] = -(committed_0 if folder == 0 else committed_1)
        else:
            # Showdown
            full_board = deal.board
            s0 = evaluate_hand(hands[0] + full_board)
            s1 = evaluate_hand(hands[1] + full_board)

            if s0 < s1:
                # Player 0 wins (lower score is better in Cactus Kev)
                deltas = [committed_1, -committed_1]
            elif s1 < s0:
                # Player 1 wins
                deltas = [-committed_0, committed_0]
            else:
                # Tie: pot split
                deltas = [0, 0]

        # Update bankrolls
        self.bankrolls[0] += deltas[0]
        self.bankrolls[1] += deltas[1]

        # Round over notification
        term = TerminalState(deltas, round_state)
        for i in range(2):
            g_state = GameState(self.bankrolls[i], self.clocks[i], round_num)
            self._call_bot_safe(i, "handle_round_over", g_state, term, i)

        self.hands_played += 1
        return deltas

    def play_duplicate_match(self, verbose=False):
        """
        Runs full duplicate match over total_rounds (2 deals per duplicate round).
        """
        num_pairs = self.total_rounds // 2
        round_counter = 1

        for pair_idx in range(num_pairs):
            deal = DuplicateDeal.generate_random()

            # Deal 1: Bot 0 is Button
            d1 = self.play_hand(deal, button_idx=0, round_num=round_counter)
            round_counter += 1

            # Deal 2: Bot 1 is Button with exact same cards (swapped seats)
            d2 = self.play_hand(deal, button_idx=1, round_num=round_counter)
            round_counter += 1

            if verbose and pair_idx % 50 == 0:
                print(f"Hand {round_counter}/{self.total_rounds}: "
                      f"{self.bot_names[0]} bankroll={self.bankrolls[0]}, "
                      f"{self.bot_names[1]} bankroll={self.bankrolls[1]}")

        # Summary
        b0_win = self.bankrolls[0] > self.bankrolls[1]
        b1_win = self.bankrolls[1] > self.bankrolls[0]
        winner = self.bot_names[0] if b0_win else (self.bot_names[1] if b1_win else "Tie")

        # bb/100: (chips / BIG_BLIND) / (hands_played / 100)
        bb_100_0 = (self.bankrolls[0] / BIG_BLIND) / (self.hands_played / 100.0) if self.hands_played > 0 else 0
        bb_100_1 = (self.bankrolls[1] / BIG_BLIND) / (self.hands_played / 100.0) if self.hands_played > 0 else 0

        result = {
            "winner": winner,
            "hands": self.hands_played,
            "bankrolls": {
                self.bot_names[0]: self.bankrolls[0],
                self.bot_names[1]: self.bankrolls[1],
            },
            "bb_per_100": {
                self.bot_names[0]: round(bb_100_0, 2),
                self.bot_names[1]: round(bb_100_1, 2),
            },
            "clocks_remaining": {
                self.bot_names[0]: round(self.clocks[0], 2),
                self.bot_names[1]: round(self.clocks[1], 2),
            },
            "timeouts": {
                self.bot_names[0]: self.stats[0]["timeouts"],
                self.bot_names[1]: self.stats[1]["timeouts"],
            }
        }
        return result

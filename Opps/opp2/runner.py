"""
runner.py - Head-to-Head duplicate match runner for heads-up pokerbots.
"""

import time
from typing import Any, Dict, List, Tuple
import numpy as np
from scipy import stats

from evaluator import card_to_str, evaluate_7cards
from bot import PokerBot
from baselines import CallingStationBot, CheckFoldBot, AllInManiacBot, NitTagBot


class HeadsUpEngine:
    def __init__(self, bot_a: Any, bot_b: Any, initial_stack: int = 200, sb: int = 1, bb: int = 2):
        self.bot_a = bot_a
        self.bot_b = bot_b
        self.initial_stack = initial_stack
        self.sb = sb
        self.bb = bb

    def play_hand(
        self,
        hand_id: int,
        deck: np.ndarray,
        time_banks: List[float],
        button_idx: int,
    ) -> Tuple[int, int]:
        bots = [self.bot_a, self.bot_b]
        hole_a = [deck[0], deck[1]]
        hole_b = [deck[2], deck[3]]
        board = [deck[4], deck[5], deck[6], deck[7], deck[8]]

        cards_str = [
            [card_to_str(c) for c in hole_a],
            [card_to_str(c) for c in hole_b],
        ]

        stacks = [self.initial_stack, self.initial_stack]
        bets = [0, 0]

        sb_player = button_idx
        bb_player = 1 - button_idx

        bets[sb_player] = self.sb
        stacks[sb_player] -= self.sb
        bets[bb_player] = self.bb
        stacks[bb_player] -= self.bb
        pot = self.sb + self.bb

        for idx in range(2):
            bots[idx].on_hand_start(
                hand_id,
                cards_str[idx],
                is_button=(idx == button_idx),
                hero_stack=stacks[idx],
                opp_stack=stacks[1 - idx],
            )

        streets = [("preflop", 0), ("flop", 3), ("turn", 4), ("river", 5)]
        current_actor = sb_player

        for street_name, board_count in streets:
            curr_board_str = [card_to_str(c) for c in board[:board_count]]

            if street_name != "preflop":
                bets = [0, 0]
                current_actor = bb_player

            street_active = True
            acted_count = 0

            while street_active:
                call_cost = bets[1 - current_actor] - bets[current_actor]
                legal_actions = []
                if call_cost == 0:
                    legal_actions.append("check")
                else:
                    legal_actions.append("call")
                    legal_actions.append("fold")

                min_raise = 0
                max_raise = 0
                if stacks[current_actor] > call_cost:
                    legal_actions.append("raise")
                    min_raise = bets[1 - current_actor] + max(self.bb, call_cost)
                    max_raise = bets[current_actor] + stacks[current_actor]

                state = {
                    "legal_actions": legal_actions,
                    "call_cost": call_cost,
                    "min_raise": min_raise,
                    "max_raise": max_raise,
                    "pot": pot,
                    "hero_stack": stacks[current_actor],
                    "opp_stack": stacks[1 - current_actor],
                    "time_bank": time_banks[current_actor],
                    "street": street_name,
                    "board": curr_board_str,
                }

                t0 = time.perf_counter()
                action, amount = bots[current_actor].get_action(state)
                elapsed = time.perf_counter() - t0
                time_banks[current_actor] = max(0.0, time_banks[current_actor] - elapsed)

                acted_count += 1

                if action == "fold":
                    winner = 1 - current_actor
                    stacks[winner] += pot
                    return (
                        stacks[0] - self.initial_stack,
                        stacks[1] - self.initial_stack,
                    )

                elif action == "call":
                    actual_call = min(call_cost, stacks[current_actor])
                    stacks[current_actor] -= actual_call
                    bets[current_actor] += actual_call
                    pot += actual_call
                    if acted_count >= 2:
                        street_active = False

                elif action == "check":
                    if acted_count >= 2:
                        street_active = False

                elif action == "raise":
                    raise_amt = min(amount - bets[current_actor], stacks[current_actor])
                    stacks[current_actor] -= raise_amt
                    bets[current_actor] += raise_amt
                    pot += raise_amt
                    acted_count = 1

                current_actor = 1 - current_actor

                if stacks[0] == 0 or stacks[1] == 0:
                    street_active = False
                    break

            if stacks[0] == 0 or stacks[1] == 0:
                break

        score_a = evaluate_7cards(hole_a + board)
        score_b = evaluate_7cards(hole_b + board)

        if score_a > score_b:
            stacks[0] += pot
        elif score_b > score_a:
            stacks[1] += pot
        else:
            stacks[0] += pot // 2
            stacks[1] += pot // 2

        summary = {"showdown": True, "board": [card_to_str(c) for c in board]}
        self.bot_a.on_hand_end({**summary, "opp_hole_cards": cards_str[1]})
        self.bot_b.on_hand_end({**summary, "opp_hole_cards": cards_str[0]})

        return (stacks[0] - self.initial_stack, stacks[1] - self.initial_stack)


def run_duplicate_match(
    bot_class_hero: Any,
    bot_class_opp: Any,
    num_hands: int = 400,
    seed: int = 42,
) -> Tuple[int, int, float, float]:
    rng = np.random.default_rng(seed)
    decks = [rng.permutation(52) for _ in range(num_hands)]

    hero1 = bot_class_hero()
    opp1 = bot_class_opp()
    tb1 = [60.0, 60.0]
    engine1 = HeadsUpEngine(hero1, opp1)
    delta_a1 = 0

    for h in range(num_hands):
        da, _ = engine1.play_hand(h + 1, decks[h], tb1, button_idx=(h % 2))
        delta_a1 += da

    opp2 = bot_class_opp()
    hero2 = bot_class_hero()
    tb2 = [60.0, 60.0]
    engine2 = HeadsUpEngine(opp2, hero2)
    delta_b2 = 0

    for h in range(num_hands):
        _, db = engine2.play_hand(h + 1, decks[h], tb2, button_idx=(h % 2))
        delta_b2 += db

    total_hero_delta = delta_a1 + delta_b2
    match_win = 1 if total_hero_delta > 0 else (0.5 if total_hero_delta == 0 else 0)
    hero_time = (60.0 - tb1[0]) + (60.0 - tb2[1])
    opp_time = (60.0 - tb1[1]) + (60.0 - tb2[0])

    return total_hero_delta, match_win, hero_time, opp_time


def evaluate_against_all_baselines() -> None:
    baselines = [
        ("CheckFoldBot", CheckFoldBot),
        ("CallingStationBot", CallingStationBot),
        ("AllInManiacBot", AllInManiacBot),
        ("NitTagBot", NitTagBot),
    ]

    print("=" * 80)
    print("STARTING TOURNAMENT GAUNTLET (DUPLICATE DEALS, 400 HANDS/MATCH)")
    print("=" * 80)

    for name, b_cls in baselines:
        deltas = []
        wins = 0
        n_matches = 10
        total_time = 0.0

        for m in range(n_matches):
            d, w, t_hero, _ = run_duplicate_match(
                PokerBot, b_cls, num_hands=400, seed=1000 + m * 37
            )
            deltas.append(d)
            wins += w
            total_time += t_hero

        deltas_arr = np.array(deltas, dtype=np.float64)
        mean_bb100 = (deltas_arr.mean() / (400 * 2)) * 100.0
        ci_low, ci_high = stats.t.interval(
            0.95,
            len(deltas) - 1,
            loc=mean_bb100,
            scale=stats.sem(deltas_arr / 8.0),
        )

        print(f"Vs {name:<18} | Win Rate: {wins/n_matches*100:>5.1f}% | "
              f"BB/100: {mean_bb100:>+7.2f} (95% CI: [{ci_low:>+6.2f}, {ci_high:>+6.2f}]) | "
              f"Avg Time: {total_time/n_matches:>4.2f}s")

    print("=" * 80)


if __name__ == "__main__":
    evaluate_against_all_baselines()

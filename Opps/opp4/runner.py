"""
runner.py - Complete duplicate-deal tournament match runner with:
- Paired duplicate deals (seats swapped, identical deck runouts)
- 95% confidence intervals for win rate and chip differential
- Illegal action and crash tracking (release gate = 0)
- Peak memory measurement via resource.getrusage
- Elapsed CPU and wall-clock execution time
"""

import math
import resource
import time
from typing import Any, Dict, List, Sequence, Tuple
import numpy as np

from evaluator import card_to_str, evaluate_7cards
from main_bot import PokerBot
from baselines import CallingStationBot, CheckFoldBot, AllInManiacBot, NitTagBot, RandomBot


class HeadsUpEngine:
    """Simulates heads-up NLHE hands between two bots."""

    def __init__(
        self,
        bot_a: Any,
        bot_b: Any,
        initial_stack: int = 200,
        sb: int = 1,
        bb: int = 2,
    ):
        self.bot_a = bot_a
        self.bot_b = bot_b
        self.initial_stack = initial_stack
        self.sb = sb
        self.bb = bb
        self.illegal_actions = [0, 0]
        self.crashes = [0, 0]

    def _safe_get_action(
        self,
        bot: Any,
        bot_idx: int,
        state: Dict[str, Any],
    ) -> Tuple[str, int]:
        try:
            act, amt = bot.get_action(state)
        except Exception:
            self.crashes[bot_idx] += 1
            legal = state.get("legal_actions", ["check", "fold"])
            return ("check", 0) if "check" in legal else ("fold", 0)

        legal = state.get("legal_actions", ["check", "fold"])
        min_raise = state.get("min_raise", 0)
        max_raise = state.get("max_raise", 0)

        if act not in legal:
            self.illegal_actions[bot_idx] += 1
            act = "check" if "check" in legal else "fold"
            amt = 0
        elif act == "raise":
            if max_raise < min_raise or amt < min_raise or amt > max_raise:
                self.illegal_actions[bot_idx] += 1
                amt = max(min_raise, min(amt, max_raise)) if max_raise >= min_raise else 0
                if max_raise < min_raise:
                    act = "call" if "call" in legal else "check"

        return act, amt

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
            try:
                bots[idx].on_hand_start(
                    hand_id,
                    cards_str[idx],
                    is_button=(idx == button_idx),
                    hero_stack=stacks[idx],
                    opp_stack=stacks[1 - idx],
                )
            except Exception:
                self.crashes[idx] += 1

        streets = [("preflop", 0), ("flop", 3), ("turn", 4), ("river", 5)]
        current_actor = sb_player
        folded = False
        folder = -1

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
                if stacks[current_actor] > call_cost and stacks[1 - current_actor] > 0:
                    legal_actions.append("raise")
                    min_raise = bets[1 - current_actor] + max(self.bb, call_cost)
                    max_raise = bets[current_actor] + stacks[current_actor]
                    max_raise = min(max_raise, bets[1 - current_actor] + stacks[1 - current_actor])

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
                act, amt = self._safe_get_action(bots[current_actor], current_actor, state)
                elapsed = time.perf_counter() - t0
                time_banks[current_actor] = max(0.0, time_banks[current_actor] - elapsed)

                acted_count += 1

                if act == "fold":
                    folded = True
                    folder = current_actor
                    street_active = False
                    break
                elif act == "check":
                    if acted_count >= 2:
                        street_active = False
                    else:
                        current_actor = 1 - current_actor
                elif act == "call":
                    diff = call_cost
                    actual_call = min(diff, stacks[current_actor])
                    bets[current_actor] += actual_call
                    stacks[current_actor] -= actual_call
                    pot += actual_call
                    street_active = False
                elif act == "raise":
                    needed = amt - bets[current_actor]
                    actual_add = min(needed, stacks[current_actor])
                    bets[current_actor] += actual_add
                    stacks[current_actor] -= actual_add
                    pot += actual_add
                    current_actor = 1 - current_actor
                    acted_count = 1

                if stacks[0] == 0 or stacks[1] == 0:
                    street_active = False

            if folded or stacks[0] == 0 or stacks[1] == 0:
                break

        committed_a = self.initial_stack - stacks[0]
        committed_b = self.initial_stack - stacks[1]

        if folded:
            if folder == 0:
                p0_delta = -committed_a
                p1_delta = committed_a
            else:
                p0_delta = committed_b
                p1_delta = -committed_b
        else:
            full_board = list(board)
            score_a = evaluate_7cards(hole_a + full_board)
            score_b = evaluate_7cards(hole_b + full_board)

            if score_a > score_b:
                p0_delta = committed_b
                p1_delta = -committed_b
            elif score_b > score_a:
                p0_delta = -committed_a
                p1_delta = committed_a
            else:
                p0_delta = 0
                p1_delta = 0

        try:
            bots[0].on_hand_end(p0_delta, p1_delta)
        except Exception:
            self.crashes[0] += 1
        try:
            bots[1].on_hand_end(p1_delta, p0_delta)
        except Exception:
            self.crashes[1] += 1

        return p0_delta, p1_delta


def run_paired_duplicate_match(
    hero_cls: Any,
    opp_cls: Any,
    num_deals: int = 200,
    seed: int = 42,
    initial_time_bank: float = 60.0,
) -> Dict[str, Any]:
    """
    Executes paired duplicate match:
    In pass 1: Hero is bot 0, Opponent is bot 1.
    In pass 2: Opponent is bot 0, Hero is bot 1.
    Exact same deck runouts are replayed with swapped seats.
    """
    rng = np.random.default_rng(seed)
    decks = [rng.permutation(52) for _ in range(num_deals)]

    hero1 = hero_cls(total_hands=num_deals * 2, time_budget=initial_time_bank)
    opp1 = opp_cls()
    tb1 = [float(initial_time_bank), float(initial_time_bank)]
    engine1 = HeadsUpEngine(hero1, opp1)

    opp2 = opp_cls()
    hero2 = hero_cls(total_hands=num_deals * 2, time_budget=initial_time_bank)
    tb2 = [float(initial_time_bank), float(initial_time_bank)]
    engine2 = HeadsUpEngine(opp2, hero2)

    deltas_hero: List[int] = []
    pair_wins = 0
    pair_ties = 0

    t_start_wall = time.perf_counter()
    t_start_cpu = time.process_time()

    for h in range(num_deals):
        button_idx = h % 2

        # Pass 1: Hero in Seat 0
        d1_hero, _ = engine1.play_hand(2 * h + 1, decks[h], tb1, button_idx=button_idx)

        # Pass 2: Hero in Seat 1 (Opponent in Seat 0 with identical deck)
        _, d2_hero = engine2.play_hand(2 * h + 2, decks[h], tb2, button_idx=button_idx)

        pair_net = d1_hero + d2_hero
        if pair_net > 0:
            pair_wins += 1
        elif pair_net == 0:
            pair_ties += 1

        deltas_hero.extend([d1_hero, d2_hero])

    t_elapsed_wall = time.perf_counter() - t_start_wall
    t_elapsed_cpu = time.process_time() - t_start_cpu

    total_hands = num_deals * 2
    net_chips = sum(deltas_hero)
    bb100 = (net_chips / 2.0) / (total_hands / 100.0)

    # 95% Confidence Interval for Pair Win Rate
    p_win = (pair_wins + 0.5 * pair_ties) / float(num_deals)
    se_p = math.sqrt(max(0.0, p_win * (1.0 - p_win)) / float(num_deals))
    ci_win_low = max(0.0, p_win - 1.96 * se_p)
    ci_win_high = min(1.0, p_win + 1.96 * se_p)

    # 95% Confidence Interval for Chip Win Rate (bb/100)
    deltas_arr = np.array(deltas_hero, dtype=np.float64) / 2.0
    mean_bb_hand = float(np.mean(deltas_arr))
    se_bb_hand = float(np.std(deltas_arr, ddof=1) / math.sqrt(total_hands))
    ci_bb100_low = (mean_bb_hand - 1.96 * se_bb_hand) * 100.0
    ci_bb100_high = (mean_bb_hand + 1.96 * se_bb_hand) * 100.0

    # Total Hero Time Used
    hero_time_used = (initial_time_bank - tb1[0]) + (initial_time_bank - tb2[1])

    # Peak memory
    peak_rss_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    total_illegal = engine1.illegal_actions[0] + engine2.illegal_actions[1]
    total_crashes = engine1.crashes[0] + engine2.crashes[1]

    return {
        "total_hands": total_hands,
        "net_chips": net_chips,
        "bb100": round(bb100, 2),
        "ci_bb100": (round(ci_bb100_low, 2), round(ci_bb100_high, 2)),
        "pair_win_rate": round(p_win, 4),
        "ci_win_rate": (round(ci_win_low, 4), round(ci_win_high, 4)),
        "pair_record": (pair_wins, pair_ties, num_deals - pair_wins - pair_ties),
        "illegal_actions": total_illegal,
        "crashes": total_crashes,
        "hero_time_used": round(hero_time_used, 3),
        "avg_ms_per_hand": round(hero_time_used * 1000.0 / total_hands, 2),
        "elapsed_wall_sec": round(t_elapsed_wall, 3),
        "elapsed_cpu_sec": round(t_elapsed_cpu, 3),
        "peak_memory_mb": round(peak_rss_mb, 2),
    }


def run_benchmark_suite(num_deals: int = 200, seed: int = 42) -> None:
    """Runs PokerBot against all baselines with paired duplicate deals."""
    baselines = [
        ("CheckFoldBot", CheckFoldBot),
        ("CallingStationBot", CallingStationBot),
        ("AllInManiacBot", AllInManiacBot),
        ("NitTagBot", NitTagBot),
        ("RandomBot", RandomBot),
    ]

    print("=" * 80)
    print("OPPONENT 4 (TITAN) - DUPLICATE MATCH BENCHMARK SUITE")
    print(f"Format: {num_deals} Paired Duplicate Deals ({2 * num_deals} Hands) | Seed: {seed}")
    print("=" * 80)

    all_passed_gate = True

    for name, bot_cls in baselines:
        print(f"\n[*] Evaluating vs {name}...")
        res = run_paired_duplicate_match(PokerBot, bot_cls, num_deals=num_deals, seed=seed)

        gate_ok = (res["illegal_actions"] == 0 and res["crashes"] == 0)
        if not gate_ok:
            all_passed_gate = False

        print(f"    Net Chips: {res['net_chips']:+d} | Win Rate: {res['bb100']:+.2f} bb/100 (95% CI: [{res['ci_bb100'][0]:+.2f}, {res['ci_bb100'][1]:+.2f}])")
        print(f"    Pair Win Rate: {res['pair_win_rate'] * 100:.1f}% (95% CI: [{res['ci_win_rate'][0] * 100:.1f}%, {res['ci_win_rate'][1] * 100:.1f}%])")
        print(f"    Pair Record: {res['pair_record'][0]}W - {res['pair_record'][1]}D - {res['pair_record'][2]}L")
        print(f"    Time Used: {res['hero_time_used']:.2f}s | Avg/Hand: {res['avg_ms_per_hand']:.2f} ms (<75ms target)")
        print(f"    Safety: Illegal={res['illegal_actions']}, Crashes={res['crashes']} (Gate: {'PASS' if gate_ok else 'FAIL'})")

    print("\n" + "=" * 80)
    print(f"OVERALL RELEASE GATE: {'PASS (100% Zero Crashes & Zero Illegal Responses)' if all_passed_gate else 'FAIL'}")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark_suite(num_deals=200, seed=42)

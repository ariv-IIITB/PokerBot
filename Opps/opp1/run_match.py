#!/usr/bin/env python3
"""
CLI Match Runner for Heads-Up Pokerbot evaluation.
Runs duplicate deals matches, prints detailed statistics, win rate in bb/100, and timing.
"""

import sys
import argparse
from engine import MatchEngine
from player import TitanBot
from baselines import AlwaysCallBot, AlwaysFoldBot, RandomBot, TightBot

BOT_REGISTRY = {
    "titanbot": TitanBot,
    "titan": TitanBot,
    "alwayscall": AlwaysCallBot,
    "call": AlwaysCallBot,
    "alwaysfold": AlwaysFoldBot,
    "fold": AlwaysFoldBot,
    "random": RandomBot,
    "tight": TightBot,
}


def run_single_match(bot1_cls, bot2_cls, total_hands=400, time_bank=60.0, verbose=False):
    """Executes a duplicate match between two bot classes."""
    b1 = bot1_cls()
    b2 = bot2_cls()
    engine = MatchEngine(b1, b2, total_rounds=total_hands, time_bank=time_bank)
    return engine.play_duplicate_match(verbose=verbose)


def run_benchmark_suite(total_hands=400, time_bank=60.0):
    """Runs TitanBot against all 4 baselines in duplicate format and prints summary."""
    baselines = [
        ("AlwaysFoldBot", AlwaysFoldBot),
        ("AlwaysCallBot", AlwaysCallBot),
        ("RandomBot", RandomBot),
        ("TightBot", TightBot),
    ]

    print("=" * 70)
    print("TITANBOT TOURNAMENT BENCHMARK SUITE")
    print(f"Format: Heads-Up NLHE Duplicate Deals | {total_hands} Hands | {time_bank}s Time Bank")
    print("=" * 70)

    results = []
    total_chips_won = 0
    all_wins = True

    for name, b_cls in baselines:
        print(f"\n[*] Running TitanBot vs {name} ({total_hands} hands)...")
        res = run_single_match(TitanBot, b_cls, total_hands=total_hands, time_bank=time_bank)
        
        t_chips = res["bankrolls"]["TitanBot"]
        t_bb100 = res["bb_per_100"]["TitanBot"]
        t_clock = res["clocks_remaining"]["TitanBot"]
        t_timeouts = res["timeouts"]["TitanBot"]
        winner = res["winner"]
        
        is_win = (winner == "TitanBot")
        if not is_win:
            all_wins = False
        total_chips_won += t_chips

        print(f"    Result: {winner} | Chips: {t_chips:+d} | Win Rate: {t_bb100:+.2f} bb/100")
        print(f"    Time Left: {t_clock:.2f}s / {time_bank:.1f}s (Used {time_bank - t_clock:.2f}s) | Timeouts: {t_timeouts}")

        results.append({
            "opponent": name,
            "winner": winner,
            "chips": t_chips,
            "bb100": t_bb100,
            "clock_used": round(time_bank - t_clock, 2),
            "timeouts": t_timeouts,
        })

    print("\n" + "=" * 70)
    print("FINAL BENCHMARK SCOREBOARD")
    print(f"{'Opponent':<18} | {'Winner':<12} | {'Chips':<10} | {'bb/100':<12} | {'Time Used':<10}")
    print("-" * 70)
    for r in results:
        print(f"{r['opponent']:<18} | {r['winner']:<12} | {r['chips']:>+8d}   | {r['bb100']:>+9.2f}    | {r['clock_used']:>6.2f}s")
    print("=" * 70)
    print(f"Total Net Chips: {total_chips_won:+d} | Match Record: {sum(1 for r in results if r['winner'] == 'TitanBot')}/{len(results)}")
    print("=" * 70)
    return results


def main():
    parser = argparse.ArgumentParser(description="Heads-Up Pokerbot Duplicate Match Runner")
    parser.add_argument("--bot1", type=str, default="titan", help="First bot name (default: titan)")
    parser.add_argument("--bot2", type=str, default="call", help="Second bot name (default: call)")
    parser.add_argument("--hands", type=int, default=400, help="Number of hands (default: 400)")
    parser.add_argument("--time", type=float, default=60.0, help="Time bank in seconds (default: 60.0)")
    parser.add_argument("--verbose", action="store_true", help="Print progress updates")
    parser.add_argument("--benchmark-all", action="store_true", help="Run TitanBot against all baselines")

    args = parser.parse_args()

    if args.benchmark_all:
        run_benchmark_suite(total_hands=args.hands, time_bank=args.time)
        return

    b1_key = args.bot1.lower()
    b2_key = args.bot2.lower()

    if b1_key not in BOT_REGISTRY:
        print(f"Error: Unknown bot1 '{args.bot1}'. Available: {list(BOT_REGISTRY.keys())}")
        sys.exit(1)
    if b2_key not in BOT_REGISTRY:
        print(f"Error: Unknown bot2 '{args.bot2}'. Available: {list(BOT_REGISTRY.keys())}")
        sys.exit(1)

    b1_cls = BOT_REGISTRY[b1_key]
    b2_cls = BOT_REGISTRY[b2_key]

    print(f"Starting Match: {b1_cls.__name__} vs {b2_cls.__name__} ({args.hands} hands, {args.time}s clock)...")
    res = run_single_match(b1_cls, b2_cls, total_hands=args.hands, time_bank=args.time, verbose=args.verbose)

    print("\n" + "=" * 50)
    print("MATCH RESULT")
    print("=" * 50)
    print(f"Winner: {res['winner']}")
    print(f"Hands Played: {res['hands']}")
    print(f"Bankrolls: {res['bankrolls']}")
    print(f"Win Rate (bb/100): {res['bb_per_100']}")
    print(f"Remaining Clocks: {res['clocks_remaining']}")
    print(f"Timeouts: {res['timeouts']}")
    print("=" * 50)


if __name__ == "__main__":
    main()

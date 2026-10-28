#!/usr/bin/env python3
"""
Main Entry Point for the Pokerbot Tournament and Local Evaluation.
Supports:
1. Competition socket mode: python run.py [--host HOST] [--port PORT]
2. Local benchmark mode: python run.py --benchmark [--hands N]
3. Quick match mode: python run.py --match [--bot OPPONENT]
"""

import sys
import argparse
from player import TitanBot
from skeleton.runner import run_socket
from run_match import run_benchmark_suite, run_single_match, BOT_REGISTRY


def main():
    parser = argparse.ArgumentParser(description="TitanBot NLHE Pokerbot")
    parser.add_argument("--host", type=str, default="localhost", help="Competition server host")
    parser.add_argument("--port", type=int, default=None, help="Competition server port")
    parser.add_argument("--benchmark", action="store_true", help="Run full benchmark suite against baselines")
    parser.add_argument("--match", action="store_true", help="Run local match against a baseline")
    parser.add_argument("--bot", type=str, default="call", help="Opponent bot for local match")
    parser.add_argument("--hands", type=int, default=400, help="Number of hands to play")
    parser.add_argument("--time", type=float, default=60.0, help="Time bank in seconds")

    # If called with positional host:port or port (common in competition runners)
    args, unknown = parser.parse_known_args()

    # Check unknown args for port or host:port
    host = args.host
    port = args.port

    for u in unknown:
        if ":" in u:
            h, p = u.split(":", 1)
            host = h
            port = int(p)
        elif u.isdigit():
            port = int(u)

    if args.benchmark:
        run_benchmark_suite(total_hands=args.hands, time_bank=args.time)
        return

    if args.match:
        opp_key = args.bot.lower()
        opp_cls = BOT_REGISTRY.get(opp_key, BOT_REGISTRY["call"])
        print(f"Running match: TitanBot vs {opp_cls.__name__} ({args.hands} hands)...")
        res = run_single_match(TitanBot, opp_cls, total_hands=args.hands, time_bank=args.time)
        print("Winner:", res["winner"])
        print("Bankrolls:", res["bankrolls"])
        print("Win Rate (bb/100):", res["bb_per_100"])
        print("Clocks remaining:", res["clocks_remaining"])
        return

    # If port specified, connect over TCP socket to tournament server
    if port is not None:
        print(f"Connecting TitanBot to competition engine at {host}:{port}...")
        bot = TitanBot()
        run_socket(bot, host, port)
        return

    # Default if no arguments given: run benchmark
    print("No competition socket port specified. Running benchmark suite by default...")
    run_benchmark_suite(total_hands=400, time_bank=60.0)


if __name__ == "__main__":
    main()

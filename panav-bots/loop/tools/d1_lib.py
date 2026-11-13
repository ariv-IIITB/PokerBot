"""Shared helpers for the D1 node-level audit: log parsing, card codes, a vectorised 7-card evaluator.

Logs are the files written by file_duel.py --logdir (what the logged bot received). Our own replies are not
logged, but `hand_result.history` is complete, and request k's reply is final_history[len(request_k.history)].
Amounts in history/requests are per-street cumulative ("raise to"/"call to"); `pot` in a request already
includes the opponent's bet. Chips committed before a decision = start_stack - my_stack.
The evaluator is the bot's own numpy evaluator (best 5 of 7), loaded from the bundle source.
"""
from __future__ import annotations
import ast, json, types
from pathlib import Path

import numpy as np

RANKS = "23456789TJQKA"
SUITS = "cdhs"
ST = ["preflop", "flop", "turn", "river"]
BOT = Path(__file__).resolve().parents[1] / "evalbuilds" / "final_seeded.py"


def card(s: str) -> int:
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])


def cards(xs):
    return [card(x) for x in xs]


def _load_evaluator():
    tree = ast.parse(BOT.read_text())
    src = None
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_SOURCES":
            src = ast.literal_eval(n.value)
    m = types.ModuleType("d1_eval")
    exec(src["shared.evaluator"][1], m.__dict__)
    return m


EV = _load_evaluator()
evaluate = EV.evaluate            # (N,k) int cards -> int64 values, higher wins


def parse_dir(d):
    """Yield one dict per hand: file, seed, leg, seat, hole3, reqs (action_requests with our reply), disc, res."""
    for f in sorted(Path(d).glob("*.jsonl")):
        seed = int(f.stem.split("_")[0][4:]); leg = f.stem.split("_")[1]
        cur = None
        for line in f.read_text().splitlines():
            m = json.loads(line); t = m["type"]
            if t == "init":
                start = m["starting_stack"]
            elif t == "new_hand":
                cur = dict(file=f.name, seed=seed, leg=leg, hand_id=m["hand_id"], seat=m["seat"], hole3=m["hole_cards"],
                           start=start, reqs=[], disc=None, dres=None)
            elif t == "action_request" and cur is not None:
                cur["reqs"].append(m)
            elif t == "discard_request" and cur is not None:
                cur["disc"] = m
            elif t == "discard_result" and cur is not None:
                cur["dres"] = m
            elif t == "hand_result" and cur is not None:
                cur["res"] = m
                hist = m["history"]
                for r in cur["reqs"]:
                    i = len(r["history"])
                    r["reply"] = hist[i] if i < len(hist) else None
                yield cur
                cur = None


def actor_first(seat):      # not needed by callers beyond clarity: button = SB acts first preflop, BB first postflop
    return seat == "button"

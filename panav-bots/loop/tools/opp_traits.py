"""Opponent trait stats from file_duel leg logs (what a trait gate could observe), from OUR point of view.

  PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/opp_traits.py LOGDIR [LOGDIR ...]

Per logdir (one opponent):
  flop_bet_rate  opp's first flop action with no bet before it: raises / (checks + raises)
  big_per_100    big bets/raises (>= 0.7 pot) we faced on flop/turn, per 100 hands that reached the flop
  big_share      share of the flop/turn bets we faced that were big
  value_share    among hands where WE CALLED a big bet (any postflop street) and reached showdown, the share where the
                 opponent's hand beat ours (ties count half); n_sd = number of such showdowns
Uses the engine's evaluator on the revealed cards (final 2 cards + 5-card board).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_replay import parse_leg, rules  # noqa: E402
from bot.cards import parse_card  # noqa: E402


def traits(logdir: str) -> dict:
    ev = rules().evaluator
    flop_hands = flop_first = flop_raise = 0
    faced = big = 0
    sd = beat = 0.0
    for f in sorted(Path(logdir).glob("seed*_m*.jsonl")):
        li = parse_leg(f)
        for h, hd in li["hands"].items():
            if "history" not in hd:
                continue
            hist = hd["history"]
            if any(e["street"] == "flop" for e in hist) or hd["board"]:
                flop_hands += 1
            # opponent's first flop action with no raise before it on that street
            raised = False
            for e in hist:
                if e["street"] != "flop":
                    continue
                if e["actor"] == "opp" and not raised:
                    flop_first += 1
                    flop_raise += int(e["action"] == "raise")
                    break
                if e["action"] == "raise":
                    raised = True
        called_big = {}
        for d in li["decisions"]:
            if d["street"] in ("flop", "turn", "river") and d["to_call"] > 0:
                frac = d["to_call"] / max(1, d["pot"] - d["to_call"])
                if d["street"] in ("flop", "turn"):
                    faced += 1
                    big += int(frac >= 0.7)
                if frac >= 0.7 and d["logged"]["action"] == "call":
                    called_big.setdefault(d["h"], d)
        for h in called_big:
            hd = li["hands"][h]
            if hd["result"] != "showdown" or not hd["opp_hole"] or len(hd["board"]) != 5:
                continue
            mine = [parse_card(c) for c in hd["hole2"]]
            theirs = [parse_card(c) for c in hd["opp_hole"]]
            board = [parse_card(c) for c in hd["board"]]
            a, b = ev.evaluate(theirs, board), ev.evaluate(mine, board)
            sd += 1
            beat += 1.0 if a > b else 0.5 if a == b else 0.0
    return dict(flop_bet_rate=flop_raise / max(1, flop_first), big_per_100=100 * big / max(1, flop_hands),
                big_share=big / max(1, faced), value_share=beat / max(1, sd), n_sd=int(sd), flop_hands=flop_hands)


def main() -> None:
    for d in sys.argv[1:]:
        t = traits(d)
        print(f"{Path(d).name:14s} flop_bet_rate {t['flop_bet_rate']:.2f}  big_per_100 {t['big_per_100']:.1f}  "
              f"big_share {t['big_share']:.2f}  value_share {t['value_share']:.2f} (n_sd {t['n_sd']})  flop_hands {t['flop_hands']}")


if __name__ == "__main__":
    main()

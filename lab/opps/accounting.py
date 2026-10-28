"""Chip accounting: where bot A wins/loses chips vs bot B, by our seat, the street the
hand ended on and how it ended (who folded, or showdown won/lost). Locks off.
Usage: python3 -m lab.opps.accounting tier2 opp3 50"""
import sys
from collections import defaultdict
from lab import engine
from lab.engine import play_match
from lab.harness import load_variant
from lab.players import PlayerSpec

STREETS = ("pre", "flop", "turn", "river")
SEAT = ("SB/BTN", "BB")
_LOG: list = []          # (seats, street, HandResult) for every hand played


def _logging_play(self):
    res = _orig_play(self)
    _LOG.append((self.seats, self.st.street, res))
    return res


_orig_play = engine.Hand.play
engine.Hand.play = _logging_play   # lab-only patch so the engine stays untouched


def outcome(role: int, res) -> str:
    """How the hand ended, from `role`'s point of view."""
    if res.folded is not None:
        return "we fold" if res.folded == role else "they fold"
    d = res.deltas[role]
    return "showdown won" if d > 0 else ("showdown lost" if d < 0 else "showdown split")


def account(a_name: str, b_name: str, pairs: int) -> tuple[dict, int, int]:
    """Returns {(seat, street, outcome): [hands, chips]}, total chips, total hands for A."""
    v = load_variant("lab/opps/holdem_100bb.json")
    cfg_b = {"fold_out": False} if b_name == "opp3" else None
    table = defaultdict(lambda: [0, 0])
    total = hands = 0
    for seed in range(pairs):
        for swap in (False, True):
            pa = PlayerSpec.brain(a_name, {"lock_enabled": False}).build()
            pb = PlayerSpec.brain(b_name, cfg_b).build()
            _LOG.clear()
            r = play_match([pb, pa] if swap else [pa, pb], v, seed, 400)
            match_chips = r.chips[1] if swap else r.chips[0]
            logged = 0
            for seats, street, res in _LOG:
                role = 0 if seats[0].player is pa else 1
                key = (SEAT[role], STREETS[min(street, 3)], outcome(role, res))
                table[key][0] += 1
                table[key][1] += res.deltas[role]
                logged += res.deltas[role]
            assert logged == match_chips, f"accounting mismatch {logged} != {match_chips}"
            total += match_chips
            hands += r.hands_played
    return table, total, hands


def report(table: dict, total: int, hands: int) -> str:
    bb = 2  # chips per big blind in holdem_100bb
    lines = [f"total {total:+d} chips over {hands} hands = {total / hands / bb:+.3f} bb/hand",
             f"{'seat':7} {'street':6} {'outcome':15} {'hands':>6} {'%hands':>7} "
             f"{'chips':>8} {'bb/100 of all':>13}"]
    for k in sorted(table, key=lambda k: table[k][1]):
        n, c = table[k]
        lines.append(f"{k[0]:7} {k[1]:6} {k[2]:15} {n:6d} {n / hands:7.1%} "
                     f"{c:+8d} {c / hands / bb * 100:+13.1f}")
    for name, idx in (("by street", 1), ("by outcome", 2), ("by seat", 0)):
        agg = defaultdict(lambda: [0, 0])
        for k, (n, c) in table.items():
            agg[k[idx]][0] += n
            agg[k[idx]][1] += c
        lines.append(f"--- {name}: " + " | ".join(
            f"{g} {c / hands / bb * 100:+.1f} bb/100 ({n / hands:.0%})"
            for g, (n, c) in sorted(agg.items(), key=lambda x: x[1][1])))
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(*account(sys.argv[1], sys.argv[2], int(sys.argv[3]))), flush=True)

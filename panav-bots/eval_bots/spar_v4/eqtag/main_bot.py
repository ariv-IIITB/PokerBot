"""eqtag: the solid baseline. Equity against the opponent's range, pot odds with realisation, value bets by street, c-bets, semi-bluffs, percentile preflop."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401


class Bot(BaseBot):
    pass


if __name__ == "__main__":
    run(Bot)

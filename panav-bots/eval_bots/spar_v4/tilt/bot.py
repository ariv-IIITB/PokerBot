"""tilt: plays tight; after losing a pot over 80 chips it plays loose-aggressive for 30 hands, then tight again."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401

TIGHT = dict(BASE, open=0.38, limp=0.15, defend=0.42, three=0.91, three_bluff=0.05, call3=0.58, four=0.95, call4=0.92,
             semi=0.25, river_bluff=0.08, cbet=0.7, margin=0.03, raise_val=0.82, value=(0.63, 0.65, 0.70))
LOOSE = dict(BASE, open=0.14, limp=0.0, defend=0.20, three=0.62, three_bluff=0.20, call3=0.50, semi=0.65,
             river_bluff=0.15, cbet=0.9, margin=0.0, value=(0.45, 0.48, 0.54), size_dry=0.6, size_wet=0.8, raise_val=0.80)


class Bot(BaseBot):
    def __init__(self):
        super().__init__()
        self.tilt_left = 0

    def on_hand_result(self, msg):
        super().on_hand_result(msg)
        if self.tilt_left > 0:
            self.tilt_left -= 1
        if msg.get("net", 0) <= -80:
            self.tilt_left = 30

    def params(self):
        return LOOSE if self.tilt_left > 0 else TIGHT


if __name__ == "__main__":
    run(Bot)

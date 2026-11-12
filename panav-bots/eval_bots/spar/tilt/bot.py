"""tilt: plays tight; after losing a pot over 80 chips it plays loose-aggressive for 30 hands, then tight again."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import BASE, BaseBot, run, board_wet, board_paired, has_draw, pre_pct, score, category  # noqa: E402,F401

TIGHT = dict(BASE, open=0.36, defend=0.46, three=0.93, three_bluff=0.0, semi=0.15, river_bluff=0.06, margin=0.05,
             value=(0.66, 0.68, 0.72))
LOOSE = dict(BASE, open=0.08, limp=0.0, defend=0.14, three=0.55, three_bluff=0.40, semi=0.8, river_bluff=0.4, cbet=1.0,
             margin=-0.02, value=(0.42, 0.45, 0.50), size_dry=0.7, size_wet=0.9)


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

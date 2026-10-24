"""Run any lab brain (sparring bots included) as a protocol-speaking subprocess bot.

    .venv/bin/python -m lab.run_brain maniac
Same main loop and safety layers as bot.main; only the brain registry is bigger.
"""
from __future__ import annotations

import sys

import bot.main as botmain
from lab.players import BRAINS


def main() -> int:
    botmain.BRAINS = BRAINS
    name = sys.argv[1] if len(sys.argv) > 1 else "tier0"
    return botmain.main(["--brain", name, *sys.argv[2:]])


if __name__ == "__main__":
    sys.exit(main())

"""Peak memory (RSS) of the bot process over a match through the subprocess path.

Uses getrusage(RUSAGE_CHILDREN) after the bot exits, so it must run in a fresh process
with no other children (the CLI does). Fails (exit 1) above the limit (default 1024 MB).

CLI:  .venv/bin/python -m lab.memory_check --hands 400 --brain tier2
"""
from __future__ import annotations

import argparse
import resource
import sys
from typing import Optional

from lab.engine import play_match
from lab.players import PlayerSpec, SubprocessPlayer


def _maxrss_mb(usage) -> float:
    # ru_maxrss is bytes on macOS, kilobytes on Linux.
    return usage.ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024)


def peak_rss_mb(brain: str = "tier2", hands: int = 400, opponent: str = "maniac",
                seed: int = 0) -> float:
    """Peak RSS (MB) of any child process run so far, after playing one match."""
    bot = SubprocessPlayer([sys.executable, "-m", "bot.main", "--brain", brain], name=brain)
    play_match([bot, PlayerSpec.brain(opponent).build()], seed=seed, hands=hands)
    return _maxrss_mb(resource.getrusage(resource.RUSAGE_CHILDREN))


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Peak RSS of the bot process.")
    ap.add_argument("--brain", default="tier2")
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--opponent", default="maniac")
    ap.add_argument("--limit-mb", type=float, default=1024.0)
    args = ap.parse_args(argv)
    mb = peak_rss_mb(args.brain, args.hands, args.opponent)
    print(f"bot peak RSS: {mb:.1f} MB (limit {args.limit_mb:g} MB)")
    return 0 if mb < args.limit_mb else 1


if __name__ == "__main__":
    sys.exit(main())

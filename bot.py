"""Submission entry point: `python3.11 bot.py`. Speaks the official protocol on stdin/stdout.
Everything lives in the `bot/` package next to this file (a package wins over this module for
`import bot`, so the name clash is harmless)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(["--protocol", "pokerbots"]))

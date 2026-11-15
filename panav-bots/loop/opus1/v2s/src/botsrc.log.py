"""stderr logging with a per-match cap (BUILDMAP §9.11). The engine keeps only 64 KB of stderr."""
import sys

LIMIT_BYTES = 20_000


class Log:
    def __init__(self, limit=LIMIT_BYTES):
        self.limit = limit
        self.used = 0
        self.dropped = 0

    def __call__(self, text):
        line = text if text.endswith("\n") else text + "\n"
        n = len(line.encode("utf-8", "replace"))
        if self.used + n > self.limit:
            self.dropped += 1
            return
        self.used += n
        try:
            sys.__stderr__.write(line)
            sys.__stderr__.flush()
        except Exception:
            pass


log = Log()

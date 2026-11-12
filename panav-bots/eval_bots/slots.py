"""Run a command while holding one of 4 shared match slots, so that at most 4 matches run at once on this laptop
(more makes bots slow and the results unreliable). Used by every agent that plays test matches.

    python eval/bots/slots.py -- .venv311/bin/python eval/bots/spar/play.py A B --matches 10 --workers 1

Waits (polling) until a slot is free. A slot is an advisory file lock, released when the command ends or crashes.
"""
import fcntl
import os
import pathlib
import subprocess
import sys
import time

SLOTS = 4
DIR = pathlib.Path(__file__).resolve().parents[2] / "logs" / "slots.noindex"


def main():
    if "--" not in sys.argv:
        raise SystemExit(__doc__)
    cmd = sys.argv[sys.argv.index("--") + 1:]
    DIR.mkdir(parents=True, exist_ok=True)
    fds = [os.open(DIR / f"slot{i}", os.O_CREAT | os.O_RDWR) for i in range(SLOTS)]
    waited = 0.0
    while True:
        for fd in fds:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                continue
        else:
            time.sleep(2.0)
            waited += 2.0
            continue
        break
    if waited:
        print(f"[slots] waited {waited:.0f} s for a free slot", file=sys.stderr, flush=True)
    sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()

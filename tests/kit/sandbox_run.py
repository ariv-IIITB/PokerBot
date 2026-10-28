"""Run the bot under an audit hook that reports everything a sandbox would forbid.

    python tests/kit/sandbox_run.py [bot.main args...] < engine_lines

Allowed: opening .py/.pyc/.so/.pth files (the import machinery). Reported on stderr as
`SANDBOX-VIOLATION <event> <args>`: any other open(), socket.*, subprocess.Popen, os.system,
os.fork, os.exec*, os.posix_spawn. The bot keeps running so every violation is listed; the
exit code is the bot's. Used by tests/test_sandbox.py.
"""
import os
import sys

ALLOWED_SUFFIXES = (".py", ".pyc", ".so", ".pth")
BAD_EVENTS = {"subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.posix_spawn",
              "os.spawn", "os.startfile"}


def _violation(event: str, args: tuple) -> bool:
    if event == "open":
        path = args[0]
        if isinstance(path, bytes):
            path = os.fsdecode(path)
        if not isinstance(path, str):                 # an int file descriptor: not a new file
            return False
        return not path.endswith(ALLOWED_SUFFIXES)
    return event in BAD_EVENTS or event.startswith(("socket.", "os.exec"))


def _hook(event: str, args: tuple) -> None:
    if _violation(event, args):
        sys.stderr.write(f"SANDBOX-VIOLATION {event} {args[:2]!r}\n")
        sys.stderr.flush()


if __name__ == "__main__":
    sys.addaudithook(_hook)
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from bot.main import main
    sys.exit(main(sys.argv[1:]))

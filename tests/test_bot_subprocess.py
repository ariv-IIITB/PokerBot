"""Run the bot as a real subprocess: stdout must contain only valid actions."""
import subprocess
import sys
import time
from pathlib import Path

from helpers import decode_replies, encode, scripted_messages

from bot.actions import Action, is_legal
from bot.protocol import ActRequest, MatchEnd, MatchInfo

ROOT = Path(__file__).resolve().parent.parent


def run(args: list[str], stdin: bytes) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], input=stdin, capture_output=True,
                          cwd=ROOT, timeout=30)


def test_stdout_only_valid_actions() -> None:
    msgs = scripted_messages(hands=20)
    lines = encode(msgs)
    # Sprinkle garbage, including invalid UTF-8, into the input stream.
    data = b"".join(line.encode() + b"\n" + (b"\xff\xfe junk\n" if i % 7 == 0 else b"")
                    for i, line in enumerate(lines))
    proc = run(["-m", "bot.main"], data)
    assert proc.returncode == 0, proc.stderr.decode()

    requests = [m for m in msgs if isinstance(m, ActRequest)]
    replies = proc.stdout.decode().splitlines()
    assert len(replies) == len(requests)
    for req, action in zip(requests, decode_replies(msgs, replies)):
        assert is_legal(action, req.legal), action


def test_script_path_entry_point() -> None:
    msgs = scripted_messages(hands=1)
    proc = run(["bot/main.py", "--brain", "tier0"], ("\n".join(encode(msgs)) + "\n").encode())
    assert proc.returncode == 0
    assert decode_replies(msgs, proc.stdout.decode().splitlines()) == [
        Action.fold(), Action.check(), Action.special("1"), Action.fold()]   # lowest of Ah,Kd


def test_empty_input_exits_cleanly() -> None:
    proc = run(["-m", "bot.main"], b"")
    assert proc.returncode == 0 and proc.stdout == b""


def test_startup_time() -> None:
    """Start-up must be well inside the 5 s allowed. Wall time is meaningless under a loaded
    machine (pytest -n auto), so judge the child's own CPU time; the wall bound is loose. The
    packaged bot's strict wall-clock start-up check runs serially in tools/package_submission."""
    import resource
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.perf_counter()
    proc = run(["-m", "bot.main"], ("\n".join(encode([MatchInfo(), MatchEnd()])) + "\n").encode())
    elapsed = time.perf_counter() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
    print(f"\nbot startup + exit: {elapsed * 1000:.0f} ms wall, {cpu * 1000:.0f} ms cpu")
    assert proc.returncode == 0
    assert cpu < 1.0 and elapsed < 5.0

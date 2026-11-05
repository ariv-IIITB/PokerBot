"""Remote play (lab/remote_seat.py + lab/remote_relay.py): a bot on another machine seats like a local one."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ECHO = [sys.executable, "-u", "-c", "import sys\nfor l in sys.stdin: print(l.strip().upper(), flush=True)"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _env(token: str = "secret") -> dict:
    return dict(os.environ, REMOTE_TOKEN=token, PYTHONPATH=str(ROOT))


def _relay(port: int, cmd: list[str], token: str = "secret", once: bool = False) -> subprocess.Popen:
    args = [sys.executable, str(ROOT / "lab" / "remote_relay.py"), "127.0.0.1", str(port)] + (["--once"] if once else []) + ["--"] + cmd
    return subprocess.Popen(args, env=_env(token), stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_lines_cross_the_bridge_both_ways() -> None:
    port = _free_port()
    seat = subprocess.Popen([sys.executable, "-m", "lab.remote_seat", "--port", str(port), "--host", "127.0.0.1"],
                            cwd=ROOT, env=_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    relay = _relay(port, ECHO, once=True)
    try:
        seat.stdin.write(b"hello\n")
        seat.stdin.flush()
        assert seat.stdout.readline().strip() == b"HELLO"
        seat.stdin.close()                               # the engine ends the match
        assert relay.wait(timeout=10) == 0
    finally:
        for p in (seat, relay):
            p.kill()
            p.wait()


def test_wrong_token_is_dropped() -> None:
    port = _free_port()
    seat = subprocess.Popen([sys.executable, "-m", "lab.remote_seat", "--port", str(port), "--host", "127.0.0.1", "--wait", "3"],
                            cwd=ROOT, env=_env(), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    relay = _relay(port, ECHO, token="wrong")
    try:
        seat.stdin.write(b"hello\n")
        seat.stdin.flush()
        assert seat.wait(timeout=10) == 1               # nobody with the right token showed up
        assert seat.stdout.read() == b""
    finally:
        for p in (seat, relay):
            p.kill()
            p.wait()


def test_a_full_match_against_a_remote_bot() -> None:
    """lab.eval seats `remote:PORT`; the 'friend' is the organisers' starter bot behind a relay."""
    port = _free_port()
    starter = [sys.executable, str(ROOT / "lab" / "sparring" / "starter_bot.py")]
    relay = _relay(port, starter)
    try:
        t0 = time.time()
        out = subprocess.run([sys.executable, "-m", "lab.eval", "calling_station", "--pool", f"remote:{port}", "--pairs", "1",
                              "--hands", "20", "--locks", "off", "--variant", "discard_holdem"],
                             cwd=ROOT, env=_env(), capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr[-500:]
        assert f"remote{port}" in out.stdout and "forfeits A/B 0/0" in out.stdout, out.stdout[-500:]
        assert time.time() - t0 < 100
    finally:
        relay.kill()
        relay.wait()

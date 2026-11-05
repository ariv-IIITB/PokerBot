"""Run YOUR bot on YOUR machine and let someone else's engine play it (docs/REMOTE_PLAY.md).

    REMOTE_TOKEN=<shared secret> python3 remote_relay.py HOST PORT -- python3.11 bot.py

One file, standard library only (Python 3.8+). For every match it starts a fresh copy of your
command, connects to the host's engine, and copies protocol lines both ways. Your code stays
on your machine; the host only ever sees the messages your bot prints. Stop it with Ctrl-C.
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time


def _copy_out(proc: subprocess.Popen, sock: socket.socket) -> None:
    try:
        while True:
            data = os.read(proc.stdout.fileno(), 65536)
            if not data:
                break
            sock.sendall(data)
    except OSError:
        pass
    try:
        sock.shutdown(socket.SHUT_RDWR)                 # your bot exited: tell the host
    except OSError:
        pass


def serve_once(host: str, port: int, token: str, cmd: list[str]) -> bool:
    """One match: start the bot, connect, bridge. False if the host was not reachable yet."""
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
    sock = None
    try:
        while sock is None:                             # the bot is already up while we wait for the host
            if proc.poll() is not None:
                print(f"your bot exited with code {proc.returncode} before the host connected", file=sys.stderr)
                return False
            try:
                sock = socket.create_connection((host, port), timeout=2)
            except OSError:
                time.sleep(0.1)
        sock.sendall(f"TOKEN {token}\n".encode())
        sock.settimeout(5)
        if sock.recv(3) != b"OK\n":
            print("the host refused the token", file=sys.stderr)
            return False
        sock.settimeout(None)
        print("match started", flush=True)
        t = threading.Thread(target=_copy_out, args=(proc, sock), daemon=True)
        t.start()
        try:
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                proc.stdin.write(data)
        except OSError:
            pass
        print("match finished", flush=True)
        return True
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.kill()
        proc.wait()
        if sock is not None:
            sock.close()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    cmd: list[str] = []
    if "--" in argv:                                    # argparse mangles `--` before a REMAINDER: split by hand
        i = argv.index("--")
        argv, cmd = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("host")
    ap.add_argument("port", type=int)
    ap.add_argument("--once", action="store_true", help="stop after one match")
    args = ap.parse_args(argv)
    token = os.environ.get("REMOTE_TOKEN", "")
    if not cmd or not token:
        print("usage: REMOTE_TOKEN=... python3 remote_relay.py HOST PORT -- <your bot command>", file=sys.stderr)
        return 2
    try:
        while True:
            ok = serve_once(args.host, args.port, token, cmd)
            if ok and args.once:
                return 0
            if not ok:
                time.sleep(1)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())

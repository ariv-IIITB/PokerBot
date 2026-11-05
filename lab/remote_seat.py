"""Engine-side seat for a bot that runs on ANOTHER machine (docs/REMOTE_PLAY.md).

The lab engine starts this as if it were a bot: protocol lines arrive on stdin, replies go to
stdout. It waits for the friend's `lab/remote_relay.py` to connect, checks the shared token,
then copies bytes both ways. Only protocol messages cross the network: no code, no files.
Lab only, never part of the submitted bot.
"""
from __future__ import annotations

import argparse
import os
import select
import socket
import sys
import time


def _read_line(conn: socket.socket, limit: int = 200) -> str:
    buf = b""
    while b"\n" not in buf and len(buf) < limit:
        chunk = conn.recv(1)
        if not chunk:
            break
        buf += chunk
    return buf.decode(errors="replace").strip()


def accept_peer(host: str, port: int, token: str, wait: float) -> socket.socket:
    """Block until a peer sends `TOKEN <token>`; others are dropped. Raises socket.timeout after `wait` s."""
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(4)
    end = time.monotonic() + wait
    try:
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise socket.timeout("no peer with the right token")
            srv.settimeout(left)                        # one deadline for the whole wait, wrong tokens included
            conn, _ = srv.accept()
            conn.settimeout(5)
            try:
                if _read_line(conn) == f"TOKEN {token}":
                    conn.sendall(b"OK\n")
                    conn.settimeout(None)
                    return conn
            except OSError:
                pass
            conn.close()
    finally:
        srv.close()


def pipe(conn: socket.socket) -> None:
    """stdin -> socket, socket -> stdout, until either side closes."""
    fd_in, fd_out = sys.stdin.fileno(), sys.stdout.fileno()
    while True:
        ready, _, _ = select.select([fd_in, conn], [], [])
        if fd_in in ready:
            data = os.read(fd_in, 65536)
            if not data:
                return                                  # engine closed: the match is over
            conn.sendall(data)
        if conn in ready:
            data = conn.recv(65536)
            if not data:
                return                                  # the friend's side closed
            os.write(fd_out, data)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=7777)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--wait", type=float, default=600.0, help="seconds to wait for the friend to connect")
    args = ap.parse_args(argv)
    token = os.environ.get("REMOTE_TOKEN", "")
    if not token:
        print("REMOTE_TOKEN is not set", file=sys.stderr)
        return 2
    try:
        conn = accept_peer(args.host, args.port, token, args.wait)
    except (socket.timeout, OSError) as e:
        print(f"no peer connected: {e!r}", file=sys.stderr)
        return 1
    try:
        pipe(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

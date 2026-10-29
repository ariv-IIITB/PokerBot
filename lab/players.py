"""Players the lab engine can seat.

Every player implements:
    notify(msg)  - an engine message that needs no reply
    act(req)     - an ActRequest; returns an Action, or a raw reply string
    close()

InProcessPlayer   runs a brain directly through bot.main.Bot (fast, no text).
SubprocessPlayer  runs a bot as a separate process over stdin/stdout using the placeholder
                  protocol, and enforces the time bank (timeout / crash -> exceptions the
                  engine turns into a forfeit, as in the competition).
"""
from __future__ import annotations

import importlib
import json
import os
import select
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from bot.actions import Action
from bot.brains.base import Brain
from bot.main import BRAINS as BOT_BRAINS
from bot.main import Bot
from bot.protocol import ActRequest, Message
from bot.protocols import get_adapter
from bot.protocols.base import as_lines

ROOT = Path(__file__).resolve().parent.parent

# Brains usable in-process: the bot's own plus the lab sparring bots.
BRAINS: dict[str, str] = dict(BOT_BRAINS)
BRAINS.update({
    "random_legal": "lab.sparring.bots:RandomLegal",
    "all_in": "lab.sparring.bots:AllIn",
    "calling_station": "lab.sparring.bots:CallingStation",
    "tight": "lab.sparring.bots:Tight",
    "maniac": "lab.sparring.bots:Maniac",
    "cfr": "lab.cfr.brain:CFRBrain",          # lab only: CFR is a no-go for the real bot
    # LLM-built opponents from Opps/ (play them on lab/opps/holdem_100bb.json)
    "opp1": "lab.opps:Opp1Brain",
    "opp2": "lab.opps:Opp2Brain",
    "opp3": "lab.opps:Opp3Brain",
    "opp4": "lab.opps:Opp4Brain",
})


class PlayerTimeout(Exception):
    """The player's time bank ran out."""


class PlayerCrashed(Exception):
    """The player process died or closed its stdout."""


def load_brain(name: str, config: Optional[dict] = None) -> Brain:
    module, _, cls_name = BRAINS[name].partition(":")
    cls = getattr(importlib.import_module(module), cls_name)
    return cls(config=config) if config is not None else cls()


class InProcessPlayer:
    def __init__(self, brain: Brain, name: str = "") -> None:
        self.name = name or getattr(brain, "name", "brain")
        self.bot = Bot(brain, out=None)

    def set_rules(self, rules) -> None:
        """Tell the brain which variant this match uses (the real bot reads variant/active.json)."""
        self.bot.brain.set_rules(rules)

    def notify(self, msg: Message) -> None:
        self.bot.on_message(msg)

    def act(self, req: ActRequest) -> Union[Action, str]:
        action = self.bot.on_message(req)
        return action if action is not None else "F"

    def close(self) -> None:
        pass


class SubprocessPlayer:
    """Runs `cmd` (default: this repo's bot) with cwd `cwd`. `act` waits for one reply line
    at most `timeleft` seconds (the engine passes the player's remaining bank)."""

    def __init__(self, cmd: Optional[list[str]] = None, cwd: Optional[str] = None,
                 name: str = "subprocess", stderr_to: Optional[str] = None,
                 variant_path: Optional[str] = None, protocol: Optional[str] = None,
                 brain_config: Optional[dict] = None) -> None:
        """variant_path: a spec JSON the bot should play (its JSON text goes to $POKERBOT_VARIANT_JSON).
        protocol: wire format (an adapter name; default $POKERBOT_PROTOCOL or placeholder).
        The bot process is started with the same $POKERBOT_PROTOCOL."""
        self.name = name
        self.cmd = cmd or [sys.executable, "-m", "bot.main"]
        self.adapter = get_adapter(protocol)
        self._err = open(stderr_to, "ab") if stderr_to else subprocess.DEVNULL
        env = dict(os.environ)
        env["POKERBOT_PROTOCOL"] = self.adapter.name
        if brain_config:
            env["POKERBOT_BRAIN_CONFIG"] = json.dumps(brain_config)
        if variant_path:
            env["POKERBOT_VARIANT_JSON"] = Path(variant_path).read_text()
        self.proc = subprocess.Popen(self.cmd, cwd=cwd or str(ROOT), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self._err, bufsize=0,
                                     env=env)
        self._buf = b""
        self.dead = False

    def _send(self, line: str) -> None:
        if self.dead:
            raise PlayerCrashed(f"{self.name} is dead")
        try:
            self.proc.stdin.write(line.encode() + b"\n")  # type: ignore[union-attr]
        except (BrokenPipeError, OSError):
            self.dead = True
            raise PlayerCrashed(f"{self.name} closed stdin") from None

    def notify(self, msg: Message) -> None:
        for line in as_lines(self.adapter.encode_message(msg)):    # may be none, or several
            self._send(line)

    def act(self, req: ActRequest, timeout: Optional[float] = None) -> Union[Action, str]:
        """The bot's reply decoded through the adapter (an Action), or the raw line if it
        can't be decoded (the engine then counts it as illegal)."""
        for line in as_lines(self.adapter.encode_message(req)):
            self._send(line)
        limit = req.timeleft if timeout is None else timeout
        line = self._read_line(max(0.0, limit if limit is not None else 60.0))
        try:
            return self.adapter.parse_action(line)
        except Exception:
            return f"<unparseable: {line[:60]}>"

    def _read_line(self, timeout: float) -> str:
        fd = self.proc.stdout.fileno()  # type: ignore[union-attr]
        deadline = time.perf_counter() + timeout
        while b"\n" not in self._buf:
            left = deadline - time.perf_counter()
            if left <= 0:
                raise PlayerTimeout(f"{self.name} timed out")
            ready, _, _ = select.select([fd], [], [], left)
            if not ready:
                raise PlayerTimeout(f"{self.name} timed out")
            chunk = os.read(fd, 4096)
            if not chunk:
                self.dead = True
                raise PlayerCrashed(f"{self.name} exited")
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line.decode(errors="replace").strip()

    def close(self) -> None:
        try:
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()
            self.proc.wait()
        if self._err is not subprocess.DEVNULL:
            self._err.close()


# --------------------------------------------------------------------------- specs

@dataclass(frozen=True)
class PlayerSpec:
    """Picklable description of a player, so harness workers can build their own.

    kind="brain":      name = a key of BRAINS, config = optional hyperparameter dict
    kind="subprocess": cmd/cwd = how to launch it (default: this repo's bot)
    kind="factory":    name = "module:function" returning a player (for fuzz bots etc.)
    """
    kind: str = "brain"
    name: str = "tier0"
    config: Optional[tuple] = None         # dict as sorted items (keeps the spec hashable)
    cmd: Optional[tuple[str, ...]] = None
    cwd: Optional[str] = None
    label: str = ""
    protocol: Optional[str] = None         # wire format for subprocess players (adapter name)

    @staticmethod
    def brain(name: str, config: Optional[dict] = None, label: str = "") -> "PlayerSpec":
        cfg = tuple(sorted(config.items())) if config else None
        return PlayerSpec("brain", name, cfg, label=label or name)

    @staticmethod
    def subprocess(cmd: Optional[list[str]] = None, cwd: Optional[str] = None,
                   label: str = "subprocess", protocol: Optional[str] = None) -> "PlayerSpec":
        return PlayerSpec("subprocess", label, None, tuple(cmd) if cmd else None, cwd, label,
                          protocol)

    @property
    def display(self) -> str:
        return self.label or self.name

    def build(self):
        if self.kind == "brain":
            cfg = dict(self.config) if self.config else None
            return InProcessPlayer(load_brain(self.name, cfg), self.display)
        if self.kind == "subprocess":
            return SubprocessPlayer(list(self.cmd) if self.cmd else None, self.cwd, self.display,
                                    protocol=self.protocol)
        if self.kind == "factory":
            module, _, fn = self.name.partition(":")
            return getattr(importlib.import_module(module), fn)()
        raise ValueError(f"unknown player kind {self.kind!r}")

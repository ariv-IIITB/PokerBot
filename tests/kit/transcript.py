"""Transcript kit: replay a wire-level conversation against the bot.

A fixture is a text file, one message per line:

    # comment                      (blank lines and # lines are ignored)
    E> <wire line>                 engine -> bot
    B> <wire line>                 the bot's expected reply to the request just above
    B> ANY                         any reply the adapter can decode

When the expected reply parses as a JSON object it is a partial match: only the given
keys are compared (`B> {"type":"action"}` checks the type alone). Otherwise the reply must
equal the text. An E> line with no B> after it must produce NO output (the bot never speaks
unprompted); one B> after it means exactly one reply line.

replay_transcript() feeds the E> lines to bot.main.Bot in-process and returns the Bot, so the
test can inspect `bot.state`. It also runs the engine side: every B> line must decode through
the adapter's parse_action (the adapter sees the neutral messages first, as in the lab).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Optional, Sequence, Union

from bot.actions import Action
from bot.main import Bot
from bot.protocols import get_adapter
from kit.scripted_brain import make_brain


class TranscriptError(AssertionError):
    """The bot's output differs from the fixture; the message names the fixture line."""


def read_transcript(path: Union[str, Path]) -> list[tuple[int, str, str]]:
    """(line number, 'E' or 'B', text) for each message line."""
    out = []
    for n, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tag, sep, text = line.partition("> ")
        if not sep or tag not in ("E", "B"):
            tag, sep, text = line.partition(">")
        if tag not in ("E", "B") or not sep:
            raise TranscriptError(f"{path}:{n}: expected 'E> ' or 'B> ', got {line[:40]!r}")
        out.append((n, tag, text.strip()))
    return out


def _matches(expected: str, got: str) -> bool:
    try:
        want = json.loads(expected)
    except ValueError:
        return expected == got
    if not isinstance(want, dict):
        return expected == got
    try:
        have = json.loads(got)
    except ValueError:
        return False
    return isinstance(have, dict) and all(k in have and have[k] == v for k, v in want.items())


def _as_list(parsed) -> list:
    return [] if parsed is None else (list(parsed) if isinstance(parsed, (list, tuple)) else [parsed])


def replay_transcript(path: Union[str, Path], brain: str = "tier0", adapter: str = "placeholder",
                      script: Optional[Sequence[Action]] = None) -> Bot:
    """Replay `path` against a fresh Bot. brain="scripted" replies from `script`."""
    out = io.StringIO()
    bot = Bot(make_brain(brain, script), out, adapter=get_adapter(adapter))
    parser = get_adapter(adapter)          # bot-side twin: the neutral messages of each E> line
    engine = get_adapter(adapter)          # engine-side twin: decodes the expected replies
    lines = read_transcript(path)
    i = 0
    while i < len(lines):
        n, tag, text = lines[i]
        if tag == "B":
            raise TranscriptError(f"{path}:{n}: a reply with no request before it")
        before = len(out.getvalue())
        bot.handle_line(text)
        replies = out.getvalue()[before:].splitlines()
        for m in _as_list(_parse(parser, text)):
            engine.encode_message(m)       # give the engine adapter its per-request context
        expect = []
        while i + 1 < len(lines) and lines[i + 1][1] == "B":
            i += 1
            expect.append(lines[i])
        if len(replies) != len(expect):
            raise TranscriptError(f"{path}:{n}: expected {len(expect)} reply line(s) to "
                                  f"{text[:60]!r}, got {len(replies)}: {replies}")
        for (bn, _, want), got in zip(expect, replies):
            if want != "ANY" and not _matches(want, got):
                raise TranscriptError(f"{path}:{bn}: expected reply {want!r}, got {got!r}")
            try:
                engine.parse_action(got if want == "ANY" else want)
            except Exception as e:
                raise TranscriptError(f"{path}:{bn}: engine side cannot decode "
                                      f"{(got if want == 'ANY' else want)!r}: {e!r}") from e
        i += 1
    return bot


def _parse(parser, text: str):
    try:
        return parser.parse_line(text)
    except Exception:                      # malformed lines: the bot's own handling is tested
        return None

"""Record matches hand by hand, from our side, for opponent profiling (lab only).

Our in-process brain plays each opponent in duplicate pairs (as lab.eval does). At the end of
every hand the recorder saves what our bot saw: our seat, our cards, the board, every action
with its street, the revealed discards, the opponent's cards if shown, and our chip result.
That is enough to rebuild any trait we measure (lab.opps.traits) and to replay the hands into
a detector (to_hand_state).

    .venv/bin/python -m lab.opps.record --pool train,starter,calling_station --pairs 12 \
        --out logs/records [--brain tier3] [--locks off] [--variant discard_holdem]

One file per opponent, <out>/<opponent>.json.gz:

    {"opponent", "brain", "variant", "hands_per_match", "commit",
     "pairs": [{"seed", "matches": [{"chips", "score", "forfeit", "hands": [HAND, ...]}, x2]}]}

    HAND = {"id", "seat", "hole3", "hole", "board", "opp", "delta",
            "h": [[street, "m"|"o", kind, amount|None, choice|None], ...],
            "rv": [["m"|"o", [card, ...]], ...]}

`seat` 0 = button (small blind, acts first preflop); `hole3` = the hole cards dealt, `hole` =
the hole cards at the end (after the discard); `opp` = the opponent's cards at showdown, else [];
`rv` = revealed cards (in Discard Hold'em, each player's discard). Card ints are bot.cards ids.
"""
from __future__ import annotations

import argparse
import gzip
import json
import multiprocessing as mp
import os
import subprocess
import time
from pathlib import Path
from typing import Iterable, Optional, Sequence

from bot.actions import Action
from bot.protocol import HandEnd, Info
from bot.state import ME, OPP, ActionRecord, HandState

ROOT = Path(__file__).resolve().parents[2]
ACTOR = {ME: "m", OPP: "o"}
ACTOR_BACK = {"m": ME, "o": OPP}


# --------------------------------------------------------------------------- one hand

def hand_record(h: HandState) -> dict:
    """A finished HandState as a compact JSON-able dict (see the module docstring)."""
    hole3 = next((list(cards) for kind, cards in h.card_log if kind == "hole"), list(h.hole))
    return {
        "id": h.hand_id, "seat": h.seat, "hole3": hole3, "hole": list(h.hole),
        "board": list(h.board), "opp": list(h.opp_cards), "delta": h.delta,
        "h": [[r.street, ACTOR[r.actor], r.action.kind, r.action.amount, r.action.choice]
              for r in h.history],
        "rv": [[ACTOR.get(i.who, i.who), list(i.cards)] for i in h.info if i.kind == "reveal"],
    }


def to_hand_state(rec: dict) -> HandState:
    """Rebuild a finished HandState from a record (for replaying hands into a detector)."""
    h = HandState(hand_id=rec["id"], seat=rec["seat"], start_stack=0, opp_start_stack=0,
                  hole=tuple(rec["hole"]), board=tuple(rec["board"]),
                  opp_cards=tuple(rec["opp"]), delta=rec["delta"], finished=True)
    h.history = [ActionRecord(street, ACTOR_BACK[who], Action(kind, amount, choice))
                 for street, who, kind, amount, choice in rec["h"]]
    h.info = [Info("reveal", ACTOR_BACK.get(who, who), tuple(cards)) for who, cards in rec["rv"]]
    h.card_log = [("hole", tuple(rec["hole3"]))]
    return h


# --------------------------------------------------------------------------- one pair

def _hook(player, hands: list) -> None:
    """Append a hand_record to `hands` after every hand our in-process brain sees."""
    brain = player.bot.brain
    observe = brain.observe

    def recording_observe(state, msg):
        observe(state, msg)
        if isinstance(msg, HandEnd) and state.hand is not None:
            hands.append(hand_record(state.hand))

    brain.observe = recording_observe


def record_pair(brain, opponent, cfg, seed: int, hands: Optional[int],
                time_bank_s: Optional[float] = None) -> dict:
    """One duplicate pair: `brain` (an in-process PlayerSpec) plays seat 0 then seat 1.
    Top-level so a spawn Pool can pickle it."""
    from lab.engine import play_match

    matches = []
    for ours in (0, 1):
        players = [None, None]
        players[ours] = brain.build(cfg)
        players[1 - ours] = opponent.build(cfg)
        recorded: list = []
        _hook(players[ours], recorded)
        res = play_match(players, cfg, seed, hands, time_bank_s=time_bank_s)
        matches.append({"chips": res.chips[ours], "score": res.score(ours),
                        "forfeit": None if res.forfeit is None else
                        ("us" if res.forfeit == ours else "opp"),
                        "hands": recorded})
    return {"seed": seed, "matches": matches}


def _pair_task(args) -> dict:
    return record_pair(*args)


def record(brain, opponent, cfg, seeds: Sequence[int], hands: Optional[int] = None,
           processes: Optional[int] = None, time_bank_s: Optional[float] = None) -> list[dict]:
    """Every seed as a recorded duplicate pair (in parallel, like lab.harness.run_duplicate)."""
    tasks = [(brain, opponent, cfg, s, hands, time_bank_s) for s in seeds]
    n_proc = processes or os.cpu_count() or 1
    if n_proc <= 1 or len(tasks) <= 1:
        return [_pair_task(t) for t in tasks]
    with mp.get_context("spawn").Pool(min(n_proc, len(tasks))) as pool:
        return pool.map(_pair_task, tasks, chunksize=1)


# --------------------------------------------------------------------------- files

def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, separators=(",", ":")).encode()
    with gzip.GzipFile(path, "wb", compresslevel=9, mtime=0) as f:
        f.write(raw)


def load(path: Path) -> dict:
    with gzip.open(path, "rb") as f:
        return json.loads(f.read())


def iter_hands(data: dict) -> Iterable[dict]:
    for pair in data["pairs"]:
        for m in pair["matches"]:
            yield from m["hands"]


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


def main(argv: Optional[list[str]] = None) -> int:
    from lab.eval import opponent_spec, parse_brain, resolve_pool
    from lab.harness import load_variant

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brain", default="tier3")
    ap.add_argument("--pool", required=True, help="names or train (comma separated)")
    ap.add_argument("--pairs", type=int, default=12)
    ap.add_argument("--first-seed", type=int, default=0)
    ap.add_argument("--hands", type=int, default=400)
    ap.add_argument("--locks", choices=("on", "off"), default="off")
    ap.add_argument("--variant", default="discard_holdem")
    ap.add_argument("--processes", type=int, default=None)
    ap.add_argument("--out", default="logs/records")
    args = ap.parse_args(argv)

    brain = parse_brain(args.brain, args.locks)
    cfg = load_variant(args.variant)
    seeds = range(args.first_seed, args.first_seed + args.pairs)
    for name in resolve_pool([args.pool], final=False):
        t0 = time.perf_counter()
        pairs = record(brain, opponent_spec(name, args.locks), cfg, seeds, args.hands,
                       args.processes)
        data = {"opponent": name, "brain": brain.display, "variant": args.variant,
                "hands_per_match": args.hands, "commit": _commit(), "pairs": pairs}
        path = Path(args.out) / f"{name}.json.gz"
        save(path, data)
        n = sum(1 for _ in iter_hands(data))
        print(f"{name}: {n} hands in {time.perf_counter() - t0:.0f}s -> {path} "
              f"({path.stat().st_size // 1024} KB)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

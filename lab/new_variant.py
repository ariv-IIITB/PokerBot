"""Day-1 variant scaffolding: write variant/active.json, validate it, explain it, smoke-test it.

    .venv/bin/python -m lab.new_variant --from mit2026_discard     # start from a preset
    .venv/bin/python -m lab.new_variant --interactive              # answer a few questions
    .venv/bin/python -m lab.new_variant                            # check variant/active.json

Then it: validates the spec (every problem listed), compiles it (naming any missing plugin),
prints the whole game in plain English (read it next to the official rules), and runs a
smoke fuzz (default 2,000 hands: Tier 2 and sparring bots, audit on: no illegal actions,
chips conserved, no information leaks, determinism). Exit code 1 if anything fails.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from bot.game.compile import NotSupported, compile_spec
from lab.engine import play_match
from lab.fuzz import WeirdPlayer
from lab.players import ROOT, PlayerSpec
from variant.spec import SpecError, VariantSpec

ACTIVE = ROOT / "variant" / "active.json"
FAST = {"max_samples": 256, "rollout_worlds": 24, "pimc_worlds": 4}


def summarize(spec: VariantSpec, rules) -> str:
    """The variant in plain English."""
    d, ev, b, m = spec.deck, spec.evaluation, spec.betting, spec.match
    lines = [f"Variant '{spec.name}': {spec.description}".rstrip(": "), ""]
    deck = f"Deck: {len(rules.deck)} cards (ranks {d.ranks}, suits {d.suits}"
    deck += f", {d.jokers} joker(s)" if d.jokers else ""
    deck += f", {d.copies} decks" if d.copies > 1 else ""
    deck += f", removed {', '.join(d.removed)}" if d.removed else ""
    lines.append(deck + ").")
    kind = {"high": "best high hand", "low_27": "2-7 lowball (worst high hand wins)",
            "low_a5": "A-5 lowball", "hilo": "hi-lo split", "score": f"custom score '{ev.score}'"}
    show = f"Showdown: {kind[ev.kind]} of {ev.hand_size} cards"
    if ev.hole_exact is not None:
        show += f", using exactly {ev.hole_exact} hole card(s)"
    if ev.hole_min is not None or ev.hole_max is not None:
        show += f", using {ev.hole_min or 0}-{ev.hole_max if ev.hole_max is not None else ev.hand_size} hole cards"
    if ev.category_order:
        show += "; ranking low->high: " + " < ".join(ev.category_order)
    if ev.wild:
        show += f"; wild: {ev.wild}"
    if ev.low_qualifier:
        show += f"; low must be {ev.low_qualifier} or better"
    lines.append(show + ".")
    bet = {"NL": "No-limit", "PL": "Pot-limit", "FL": f"Fixed-limit {b.fixed_bets}"}[b.structure]
    bet += f" betting; blinds {b.small_blind}/{b.big_blind}"
    bet += f", ante {b.ante}" if b.ante else ""
    bet += f", SB straddle {b.straddle}" if b.straddle else ""
    bet += f", max {b.max_raises} raises/round" if b.max_raises is not None else ""
    bet += f", sizes {b.bet_sizes} x pot" if b.bet_sizes else ""
    bet += f", multiples of {b.bet_multiple}" if b.bet_multiple else ""
    bet += ", no check-raise" if not b.check_raise else ""
    lines.append(bet + ".")
    match = (f"Match: {m.hands} hands, {m.time_bank_s:g}s time bank, stacks {m.starting_stack} "
             f"({'reset every hand' if m.reset_stacks else 'carried over'}"
             f"{'' if m.reset_stacks else (', bust ends the match' if m.bust_ends_match else ', rebuy on bust')})")
    if m.blind_schedule:
        match += f", blinds {m.blind_schedule}"
    lines.append(match + ".")
    if spec.payoffs:
        lines.append(f"Payoff modifiers: {spec.payoffs}.")
    lines += ["", "Each hand:", rules.describe()]
    return "\n".join(lines)


def smoke(spec: VariantSpec, hands: int, seed: int = 0) -> list[str]:
    """Short audited matches; returns problems (empty = fine)."""
    problems = []
    rules = compile_spec(spec)
    per = max(10, hands // 8)
    pairings = [("tier2", "random_legal"), ("tier2", "maniac"), ("tier2", "calling_station"),
                ("tight", "maniac"), ("tier2", "tier2")]
    for i, (a, b) in enumerate(pairings):
        pa = PlayerSpec.brain(a, FAST if a.startswith("tier") else None).build()
        pb = PlayerSpec.brain(b, FAST if b.startswith("tier") else None).build()
        try:
            m = play_match([pa, pb], rules, seed=seed + i, hands=per, audit=True)
        except Exception as e:
            problems.append(f"{a} vs {b}: {type(e).__name__}: {e}")
            continue
        if m.errors != [0, 0]:
            problems.append(f"{a} vs {b}: illegal actions {m.errors}")
        if m.forfeit is not None:
            problems.append(f"{a} vs {b}: forfeit ({m.forfeit_reason})")
    for style in WeirdPlayer.STYLES:
        try:
            m = play_match([PlayerSpec.brain("tier2", FAST).build(), WeirdPlayer(style, seed)],
                           rules, seed=seed + 100, hands=per // 2, audit=True)
            if m.errors[0]:
                problems.append(f"tier2 vs weird:{style}: our bot sent illegal actions")
        except Exception as e:
            problems.append(f"tier2 vs weird:{style}: {type(e).__name__}: {e}")
    runs = [play_match([PlayerSpec.brain("random_legal").build(), PlayerSpec.brain("maniac").build()],
                       rules, seed=seed, hands=30).hand_deltas for _ in range(2)]
    if runs[0] != runs[1]:
        problems.append("not deterministic for a fixed seed")
    return problems


def interactive() -> dict:
    """A few questions for the common fields; edit the JSON for the rest."""
    def ask(q: str, default):
        raw = input(f"{q} [{default}]: ").strip()
        if not raw:
            return default
        return type(default)(raw) if not isinstance(default, list) else json.loads(raw)
    d: dict = {"name": ask("variant name", "active"), "description": ask("one-line description", "")}
    ranks = ask("deck ranks low->high", "23456789TJQKA")
    if ranks != "23456789TJQKA":
        d["deck"] = {"ranks": ranks}
    d["hole_cards"] = ask("hole cards each", 2)
    d["streets"] = ask("board cards per betting round, as a JSON list", [0, 3, 1, 1])
    b = {"structure": ask("betting structure NL/PL/FL", "NL"),
         "small_blind": ask("small blind", 1), "big_blind": ask("big blind", 2)}
    if b["structure"] == "FL":
        b["fixed_bets"] = ask("fixed bet per round (JSON list)", [2, 2, 4, 4])
    d["betting"] = b
    d["match"] = {"hands": ask("hands per match", 400), "time_bank_s": ask("time bank (s)", 60.0),
                  "starting_stack": ask("starting stack", 400)}
    print("Card steps, side mechanics etc.: edit variant/active.json (see docs/VARIANT_INTERVIEW.md).")
    return d


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Create / check the active variant.")
    ap.add_argument("--from", dest="preset", default=None, help="catalog preset to copy")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--spec", default=str(ACTIVE), help="spec file to check (and write)")
    ap.add_argument("--hands", type=int, default=2000, help="smoke-fuzz hands (0 = skip)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing spec file")
    args = ap.parse_args(argv)
    path = Path(args.spec)

    if args.preset or args.interactive:
        if path.exists() and not args.force:
            print(f"{path} exists: use --force to overwrite (or edit it and rerun without --from)")
            return 1
        if args.preset:
            shutil.copyfile(ROOT / "variant" / "catalog" / f"{args.preset}.json", path)
        else:
            path.write_text(json.dumps(interactive(), indent=2) + "\n")
        print(f"wrote {path}")

    try:
        spec = VariantSpec.load(path)
        rules = compile_spec(spec)
    except SpecError as e:
        print(f"INVALID SPEC\n{e}")
        return 1
    except NotSupported as e:
        print(f"NEEDS A NEW PLUGIN: {e}\n(see docs/WRITING_A_PLUGIN.md)")
        return 1
    except (OSError, ValueError) as e:
        print(f"cannot read {path}: {e}")
        return 1
    print(summarize(spec, rules))
    if args.hands:
        t = time.perf_counter()
        problems = smoke(spec, args.hands)
        dt = time.perf_counter() - t
        if problems:
            print(f"\nSMOKE FUZZ FAILED ({dt:.0f}s):")
            for p in problems:
                print("  -", p)
            return 1
        print(f"\nsmoke fuzz: OK ({args.hands} hands, {dt:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

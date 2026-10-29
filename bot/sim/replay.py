"""Rebuild the current hand as a bot.game.GameState from what the bot has seen.

Method ("replay with placeholders"):
  1. Start a GameState whose deck is made of placeholder tokens (negative ints), so the
     rules can deal without knowing real cards.
  2. Replay every action of the hand so far through the runner: ours from our history,
     the opponent's from theirs. Opponent choices we never saw (private steps, or a
     simultaneous choice still pending) are sampled from their legal options.
  3. Line up the replayed events that we were allowed to see (hole / board / card-info
     events) with the messages we actually received, card by card. That maps every
     placeholder we've seen to its real card.
Placeholders left unmapped are the hidden cards (opponent hole cards, the undealt deck,
hidden discards). `determinize` fills them with real unseen cards, giving one
consistent world.

If random engine outcomes (random swaps, ties) differ between the replay and reality,
the alignment fails; we retry with another random seed, and give up after a few tries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from bot.actions import SPECIAL, Action, clamp
from bot.game.runner import act, advance, legal_actions
from bot.game.state import ALL, INFO_KINDS, GameState
from bot.state import ME, OPP, HandState


class ReplayError(Exception):
    """The replay could not be matched to what we observed."""


@dataclass
class Reconstruction:
    state: GameState                 # at our current decision; hidden cards are placeholders
    me: int                          # our role
    mapping: dict                    # placeholder -> real card (cards we've seen)
    unknown: list                    # placeholders still hidden
    pool: list                       # real cards not seen: candidates for the unknowns
    sampled_opp_choices: int = 0     # opponent choices we had to guess
    smart_discard: bool = True       # rollouts keep the best two cards (False: a random discard)
    tries: int = 1
    opp_decisions: list = field(default_factory=list)   # visible opponent choices (inference)
    bet_log: list = field(default_factory=list)         # (player, action, pot, to_call, bet,
                                                        #  all_in, street, legal) per betting action

    def assignments(self, rng: np.random.Generator, n: int) -> dict:
        """n random fillings of the hidden tokens: token -> (n,) array of real cards."""
        k = len(self.unknown)
        pool = np.asarray(self.pool)
        idx = np.argsort(rng.random((n, len(pool))), axis=1)[:, :k]
        cards = pool[idx]
        return {tok: cards[:, i] for i, tok in enumerate(self.unknown)}

    def world_from(self, columns: dict, row: int) -> GameState:
        full = dict(self.mapping)
        for tok, col in columns.items():
            full[tok] = int(col[row])
        return substitute(self.state, full)

    def world(self, rng: np.random.Generator) -> GameState:
        """One determinized copy: unknown placeholders replaced by random unseen cards."""
        return self.world_from(self.assignments(rng, 1), 0)


def _visible_card_events(st: GameState, me: int) -> list[tuple[str, tuple]]:
    """Replayed events that the engine would have turned into card messages for `me`."""
    out = []
    for e in st.events:
        if e.visible != ALL and e.visible != me:
            continue
        cards = e.data.get("cards", ())
        if e.kind == "hole" and e.player == me:
            out.append(("hole", tuple(cards)))
        elif e.kind == "board":
            out.append(("board", tuple(cards)))
        elif e.kind in INFO_KINDS and cards:
            out.append(("info:" + e.kind, tuple(cards)))
    return out


def _sample_hidden_choice(legal, shown: Optional[str], rng) -> Action:
    """A legal opponent choice consistent with what we were shown of it."""
    sp = legal.special
    if sp is None:
        return clamp(Action.check(), legal)
    if sp.is_range:
        if shown is not None and shown.lstrip("-").isdigit():
            return clamp(Action.special(shown), legal)
        return Action.special(str(int(rng.integers(sp.lo, sp.hi + 1))))
    opts = list(sp.choices)
    if shown is not None and shown in opts:
        return Action.special(shown)
    if shown is not None and shown.isdigit():           # a draw: we were told the count
        k = int(shown)
        same = [o for o in opts if (0 if o == "none" else len(o.split("+"))) == k]
        if same:
            opts = same
    return Action.special(opts[int(rng.integers(len(opts)))])


def _patch_values(st: GameState, hand: HandState) -> None:
    """Non-card random outcomes we observed (e.g. a random bounty rank)."""
    for info in hand.info:
        if info.kind == "bounty" and info.who == "none" and info.value is not None:
            b = st.extra.get("bounty")
            if b is not None:
                b = dict(b)
                b["ranks"] = {p: info.value for p in range(st.n_players)}
                st.extra["bounty"] = b


def replay_once(rules, hand: HandState, rng, level=None) -> Reconstruction:
    me = hand.seat
    n_cards = len(rules.deck)
    tokens = [-(i + 1) for i in range(n_cards)]
    stacks = [0, 0]
    stacks[me], stacks[1 - me] = hand.start_stack, hand.opp_start_stack
    st = GameState(rules, tokens, stacks, hand.hand_id, record=True, level=level)
    mine = [r.action for r in hand.history if r.actor == ME]
    theirs = [r.action for r in hand.history if r.actor == OPP]
    guessed = 0
    decisions: list = []
    bet_log: list = []

    def log_bet(p, a, legal):
        if st.rules.program[st.pc].type_name == "betting" and a.kind != SPECIAL:
            all_in = a.kind == "R" and a.amount == st.bet[p] + st.stack[p]
            bet_log.append((p, a, st.pot, st.to_call(p), st.bet[p], all_in, st.street, legal))
    while True:
        p = advance(st, rng)
        if p is None:
            raise ReplayError("hand ended during replay")
        legal = legal_actions(st, p)
        if p == me:
            if not mine:
                break                                    # our current decision
            a = clamp(mine.pop(0), legal)
            log_bet(p, a, legal)
            act(st, p, a)
            continue
        if theirs:
            a = theirs.pop(0)
            if a.kind == SPECIAL and not legal.can_special:
                raise ReplayError("opponent special action out of place")
            genuine = True
            if a.kind == SPECIAL and not legal.special.allows(a.choice):
                a = _sample_hidden_choice(legal, a.choice, rng)
                guessed += 1
                genuine = False
            if genuine:
                _record(decisions, st, p, a, legal)
            a = clamp(a, legal)
            log_bet(p, a, legal)
            act(st, p, a)
        else:                                            # opponent choice not shown yet
            act(st, p, _sample_hidden_choice(legal, None, rng) if legal.can_special
                else clamp(Action.check(), legal))
            guessed += 1
    _patch_values(st, hand)

    # Align our visible card events with the card messages we received.
    replayed = _visible_card_events(st, me)
    observed = list(hand.card_log)
    if len(replayed) != len(observed):
        raise ReplayError(f"{len(replayed)} card events replayed, {len(observed)} observed")
    mapping: dict = {}
    for (k1, toks), (k2, real) in zip(replayed, observed):
        if k1 != k2 or len(toks) != len(real):
            raise ReplayError(f"event mismatch {k1} vs {k2}")
        for t, c in zip(toks, real):
            if mapping.setdefault(t, c) != c:
                raise ReplayError("inconsistent card mapping")
    if len(set(mapping.values())) != len(mapping):
        raise ReplayError("two placeholders mapped to one card")
    seen = set(mapping.values())
    pool = [c for c in rules.deck if c not in seen]
    in_play = set(st.deck) | set(st.muck) | {t for h in st.hole for t in h} | set(st.board)
    in_play |= {t for b in st.boards for t in b}
    for v in st.extra.get("offers", {}).values():
        in_play |= set(v)
    unknown = sorted(t for t in in_play if t < 0 and t not in mapping)
    return Reconstruction(st, me, mapping, unknown, pool, guessed, opp_decisions=decisions,
                          bet_log=bet_log)


def _record(decisions: list, st: GameState, p: int, a: Action, legal) -> None:
    """Keep the opponent's visible choices that say something about their cards."""
    from bot.sim.inference import OppDecision
    step = st.rules.program[st.pc]
    if step.type_name == "betting" and a.kind != SPECIAL:
        kinds = tuple(k for k, ok in (("F", legal.fold), ("K", legal.check), ("C", legal.call),
                                      ("R", legal.can_raise)) if ok)
        decisions.append(OppDecision("bet", a, tuple(st.hole[p]), tuple(st.board),
                                     legal_kinds=kinds))
    elif step.type_name == "discard" and getattr(step, "visibility", "") == "public":
        decisions.append(OppDecision("discard", a, tuple(st.hole[p]), tuple(st.board),
                                     options=tuple(legal.special.choices)))


def reconstruct(rules, hand: HandState, rng: np.random.Generator, level=None,
                tries: int = 6) -> Reconstruction:
    """Replay the hand (retrying with fresh randomness if random outcomes don't match)."""
    last: Optional[Exception] = None
    for i in range(tries):
        try:
            rec = replay_once(rules, hand, np.random.default_rng(int(rng.integers(2**62))), level)
            rec.tries = i + 1
            return rec
        except ReplayError as e:
            last = e
    raise ReplayError(f"could not reconstruct after {tries} tries: {last}")


def _sub(x, m: dict):
    if isinstance(x, int):
        return m.get(x, x) if x < 0 else x
    if isinstance(x, list):
        return [_sub(v, m) for v in x]
    if isinstance(x, tuple):
        return tuple(_sub(v, m) for v in x)
    if isinstance(x, dict):
        return {k: _sub(v, m) for k, v in x.items()}
    return x


def substitute(st: GameState, m: dict) -> GameState:
    """Copy of `st` with placeholder tokens replaced through mapping `m` (no event log)."""
    g = st.copy(record=False)
    g.deck = [m.get(c, c) for c in g.deck]
    g.hole = [[m.get(c, c) for c in h] for h in g.hole]
    g.board = [m.get(c, c) for c in g.board]
    g.boards = [[m.get(c, c) for c in b] for b in g.boards]
    g.muck = [m.get(c, c) for c in g.muck]
    g.extra = _sub(g.extra, m)
    return g

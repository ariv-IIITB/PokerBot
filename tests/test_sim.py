"""Phase 16: reconstruction, determinization, expected share, PIMC and step policies."""
import time

import numpy as np
import pytest

from bot.actions import Action, LegalActions, SpecialOption
from bot.brains.base import Brain
from bot.cards import parse_cards as P
from bot.equity import equity_exact
from bot.game.compile import compile_spec
from bot.sim.policies import decide_special
from bot.sim.replay import reconstruct
from bot.sim.rollout import pimc, rollout_share
from bot.sim.share import expected_share, fast_path_ok, fast_share
from lab.engine import Hand, play_match
from lab.players import InProcessPlayer, PlayerSpec
from variant.spec import VariantSpec, load_catalog

CATALOG = load_catalog()


class Probe(Brain):
    """Reconstructs at every decision and checks the result against the true engine state
    (which the test hands it through `truth`)."""

    def __init__(self) -> None:
        self.truth = None
        self.ok = self.fail = 0
        self.errors: list[str] = []

    def decide(self, state, legal, budget_s):
        rng = np.random.default_rng(len(state.hand.history))
        try:
            rec = reconstruct(self.rules, state.hand, rng, tries=8)
        except Exception as e:
            self.fail += 1
            self.errors.append(repr(e))
            return Action.special(legal.special.default()) if legal.can_special else \
                (Action.call() if legal.call else Action.check())
        true = self.truth()
        me = rec.me
        real = lambda toks: [rec.mapping.get(t, t) for t in toks]  # noqa: E731
        assert real(rec.state.hole[me]) == list(true.hole[me])
        assert real(rec.state.board) == list(true.board)
        assert [real(b) for b in rec.state.boards] == [list(b) for b in true.boards]
        assert rec.state.total == true.total and rec.state.stack == true.stack
        assert rec.state.pc == true.pc
        from bot.game.runner import legal_actions
        assert legal_actions(rec.state, me) == legal
        # A determinized world never invents a seen card or duplicates a card.
        w = rec.world(rng)
        cards = w.deck + w.board + w.muck + [c for h in w.hole for c in h] + \
            [c for b in w.boards for c in b] + [c for v in w.extra.get("offers", {}).values() for c in v]
        assert sorted(cards) == sorted(self.rules.deck)
        assert w.hole[me] == list(true.hole[me])
        self.ok += 1
        if legal.can_special:
            sp = legal.special
            return Action.special(sp.choices[int(rng.integers(len(sp.choices)))] if sp.choices
                                  else str(int(rng.integers(sp.lo, sp.hi + 1))))
        opts = [a for a, ok in [(Action.check(), legal.check), (Action.call(), legal.call),
                                (Action.fold(), legal.fold and rng.random() < 0.1)] if ok]
        if legal.can_raise and rng.random() < 0.25:
            opts.append(Action.raise_to(legal.raise_min))
        return opts[int(rng.integers(len(opts)))]


class TruthPlayer(InProcessPlayer):
    """In-process player whose brain can peek at the engine's real hand (test only)."""


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_reconstruction_matches_engine(name, monkeypatch) -> None:
    probe = Probe()
    player = TruthPlayer(probe)
    current = {}
    orig_init = Hand.__init__

    def init(self, *a, **kw):
        orig_init(self, *a, **kw)
        current["hand"] = self
    monkeypatch.setattr(Hand, "__init__", init)
    probe.truth = lambda: current["hand"].st
    m = play_match([player, PlayerSpec.brain("random_legal").build()], CATALOG[name], seed=5,
                   hands=25)
    assert m.errors == [0, 0]
    total = probe.ok + probe.fail
    assert total > 0 and probe.fail <= 0.05 * total, (probe.fail, total, probe.errors[:3])


# --------------------------------------------------------------------------- shares

def rec_for(spec, hole, board, me=0, script=None):
    """Reconstruction of a hand checked down to `board` (deck rigged so we hold `hole`)."""
    from bot.state import GameState as BotState
    from bot.protocol import BoardUpdate, HandStart, HoleCards, OppAction
    rules = compile_spec(spec)
    st = BotState()
    st.apply(HandStart(0, me, rules.starting_stack, rules.starting_stack))
    st.apply(HoleCards(P(hole)))
    if not board:
        return reconstruct(rules, st.hand, np.random.default_rng(0))   # our first decision
    # Pre-flop: SB calls, BB checks; then flop/turn/river checked through to `board`.
    if me == 0:
        st.record_my_action(Action.call()); st.apply(OppAction(Action.check()))
    else:
        st.apply(OppAction(Action.call())); st.record_my_action(Action.check())
    cards = P(board)
    sizes = [3, 4, 5][: [0, 0, 0, 1, 2, 3][len(cards)]]
    for street, k in enumerate(sizes, start=1):
        st.apply(BoardUpdate(street, cards[:k]))
        if k < len(cards):
            if me == 1:
                st.record_my_action(Action.check()); st.apply(OppAction(Action.check()))
            else:
                st.apply(OppAction(Action.check())); st.record_my_action(Action.check())
    if me == 1 and sizes:
        pass
    elif sizes:
        st.apply(OppAction(Action.check()))
    return reconstruct(rules, st.hand, np.random.default_rng(0))


def test_fast_share_matches_exact_equity() -> None:
    rec = rec_for(VariantSpec(), "8s,8d", "Ts,9s,2c,Kh")
    assert fast_path_ok(rec)
    exact = equity_exact(P("8s,8d"), P("Ts,9s,2c,Kh")).equity
    r = fast_share(rec, np.random.default_rng(1), 0.05, max_samples=40000)
    assert abs(r.share - exact) < 4 * r.stderr + 0.005


def test_rollout_share_agrees_with_fast_share() -> None:
    rec = rec_for(VariantSpec(), "Ah,Kh", "Qh,7c,2d")
    fast = fast_share(rec, np.random.default_rng(2), 0.05, max_samples=20000)
    slow = rollout_share(rec, np.random.default_rng(3), 0.15)
    assert abs(fast.share - slow.share) < 4 * (fast.stderr + slow.stderr) + 0.01


def test_share_generalizes_to_hilo_and_boards() -> None:
    for name in ["omaha_hilo", "three_boards", "deuces_wild", "short_deck"]:
        spec = CATALOG[name]
        rules = compile_spec(spec)
        hole = ",".join(__import__("bot.cards", fromlist=["x"]).format_card(c)
                        for c in rules.deck[-rules.hole_cards:])
        rec = rec_for(spec, hole, "")
        r = expected_share(rec, np.random.default_rng(4), 0.02)
        assert 0.0 <= r.share <= 1.0 and r.samples > 50, name


# --------------------------------------------------------------------------- PIMC / policies

def mit_rec(hole: str, flop: str):
    spec = CATALOG["mit2026_discard"]
    from bot.state import GameState as BotState
    from bot.protocol import BoardUpdate, HandStart, HoleCards, OppAction
    rules = compile_spec(spec)
    st = BotState()
    st.apply(HandStart(0, 1, 400, 400))            # we are BB: we discard first
    st.apply(HoleCards(P(hole)))
    st.apply(OppAction(Action.raise_to(40)))       # a real pot, so the choice matters
    st.record_my_action(Action.call())
    st.apply(BoardUpdate(1, P(flop)))
    return reconstruct(rules, st.hand, np.random.default_rng(0))


def test_pimc_throws_away_the_junk_card() -> None:
    # Discards go face up onto the board: throwing a spade away helps the opponent too.
    rec = mit_rec("As,Ks,2d", "Qs,Js")
    legal = LegalActions(special=SpecialOption("discard", ("0", "1", "2")))
    picks = [pimc(rec, [Action.special(c) for c in ("0", "1", "2")],
                  np.random.default_rng(seed), 0.15).best for seed in range(3)]
    assert picks.count(Action.special("2")) >= 2, picks
    t0 = time.perf_counter()
    decide_special(rec, legal, np.random.default_rng(6), 0.03)
    assert time.perf_counter() - t0 < 0.1          # respects its budget


def test_auction_bids_track_prize_value() -> None:
    for prize, positive in [("card", True), ("position", False)]:
        spec = VariantSpec.from_dict({"program": [
            {"type": "post_blinds"}, {"type": "deal_hole", "n": 2}, {"type": "betting"},
            {"type": "deal_board", "n": 3},
            {"type": "auction", "kind": "second_price", "prize": prize},
            {"type": "betting"}, {"type": "deal_board", "n": 2}, {"type": "betting"},
            {"type": "showdown"}]})
        rec = rec_for(spec, "Ah,Kd", "Qh,7c,2d")
        legal = LegalActions(special=SpecialOption("bid", (), 0, 398))
        bid = int(decide_special(rec, legal, np.random.default_rng(7), 0.08).choice)
        if positive:
            assert bid > 0
        else:
            assert bid <= 1                                   # check-down: position worth ~0


def test_market_quote_is_fair_value() -> None:
    spec = VariantSpec.from_dict({"program": [
        {"type": "post_blinds"}, {"type": "deal_hole", "n": 2}, {"type": "betting"},
        {"type": "deal_board", "n": 3}, {"type": "market", "quantity": "board_hearts"},
        {"type": "betting"}, {"type": "deal_board", "n": 2}, {"type": "betting"},
        {"type": "showdown"}]})
    rec = rec_for(spec, "Ah,Kd", "Qh,7h,2d")
    legal = LegalActions(special=SpecialOption("quote", (), 0, 5))
    q = int(decide_special(rec, legal, np.random.default_rng(8), 0.05).choice)
    # 2 hearts showing; 11 of 45 unseen are hearts; 2 more cards -> 2 + 2*11/45 ~ 2.5
    assert q in (2, 3)


def test_upgraded_tier2_plays_every_catalog_variant() -> None:
    for name, spec in CATALOG.items():
        m = play_match([PlayerSpec.brain("tier2", {"rollout_worlds": 12, "pimc_worlds": 2}).build(),
                        PlayerSpec.brain("random_legal").build()], spec, seed=9, hands=20,
                       audit=True)
        assert m.errors == [0, 0] and m.forfeit is None, name

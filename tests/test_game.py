"""bot/game: hand programs, hidden-information correctness, simulation support."""
import random

import pytest

from bot.actions import Action
from bot.game.observation import hidden_from, observe
from bot.game.rules_spec import Rules, to_rules
from bot.game.runner import act, advance, legal_actions, play_out
from bot.game.state import GameState, VisibilityError
from bot.game.steps import STEP_TYPES, Step
from lab.engine import deck_for
from lab.example_variants import EXAMPLES
from variant.spec import VariantSpec


def random_policy(seed: int):
    rng = random.Random(seed)

    def policy(st, p, legal):
        opts = []
        if legal.fold:
            opts.append(Action.fold())
        if legal.check:
            opts.append(Action.check())
        if legal.call:
            opts += [Action.call()] * 3
        if legal.can_raise:
            opts.append(Action.raise_to(rng.randint(legal.raise_min, legal.raise_max)))
        if legal.can_special:
            opts.append(Action.special(rng.choice(legal.special.choices)))
        return rng.choice(opts)
    return policy


def new_state(spec: VariantSpec, seed: int, audit: bool = True) -> GameState:
    rules = to_rules(spec)
    return GameState(rules, deck_for(seed, 0), [rules.starting_stack] * 2, audit=audit)


def test_holdem_is_a_hand_program() -> None:
    rules = to_rules(VariantSpec())
    names = [s.type_name for s in rules.program]
    assert names == ["post_blinds", "deal_hole", "betting", "deal_board", "betting",
                     "deal_board", "betting", "deal_board", "betting", "showdown"]
    text = rules.describe()
    assert "preflop no-limit betting, SB acts first" in text and "deal 3 board cards" in text
    assert set(STEP_TYPES) >= {"post_blinds", "deal_hole", "deal_board", "betting", "showdown"}


def test_discard_placed_before_flop_betting() -> None:
    names = [s.type_name for s in to_rules(EXAMPLES["discard3"]).program]
    assert names[3:6] == ["deal_board", "discard", "betting"]


@pytest.mark.parametrize("variant", sorted(EXAMPLES))
def test_observations_never_leak(variant: str) -> None:
    """Random hands: at every decision, no player has seen an undealt card or an
    opponent's unrevealed hole card; showdown reveals only after the betting ends."""
    cfg = EXAMPLES[variant]
    for seed in range(60):
        st = new_state(cfg, seed)                 # audit=True also checks every emit
        policy = random_policy(seed)
        while True:
            p = advance(st)
            for q in range(2):
                v = observe(st, q)
                if not st.done:
                    assert not (v.seen_cards & hidden_from(st, q)), (variant, seed, q)
                    assert not v.revealed
                assert set(v.hole) == set(st.hole[q]) or st.done
            if p is None:
                break
            act(st, p, policy(st, p, legal_actions(st, p)))
        assert sum(st.deltas) == 0
        for q in range(2):
            v = observe(st, q)
            assert v.delta == st.deltas[q]
            if st.showdown:
                assert v.revealed[1 - q] == tuple(st.hole[1 - q])


class LeakyStep(Step):
    """Broken on purpose: shows the big blind's hole cards to everyone."""
    type_name = "leaky"

    def apply(self, st, rng) -> None:
        st.emit("oops", 1, cards=tuple(st.hole[1]))


def test_leak_is_detected() -> None:
    base = to_rules(VariantSpec())
    leaky = Rules(base.program[:2] + (LeakyStep(),) + base.program[2:], base.evaluator)
    st = GameState(leaky, deck_for(0, 0), [400, 400], audit=True)
    with pytest.raises(VisibilityError):
        advance(st)
    # Without the audit, the observation check catches it too.
    st = GameState(leaky, deck_for(0, 0), [400, 400])
    advance(st)
    assert observe(st, 0).seen_cards & hidden_from(st, 0)


def test_copy_is_independent_and_replays() -> None:
    st = new_state(VariantSpec(), 3, audit=False)
    p = advance(st)
    act(st, p, Action.call())
    p = advance(st)
    snapshot = (list(st.stack), list(st.deck), st.pc, list(st.board))
    sims = []
    for i in range(20):
        c = st.copy()
        sims.append(play_out(c, random_policy(i)))
        assert sum(sims[-1]) == 0
    assert (list(st.stack), list(st.deck), st.pc, list(st.board)) == snapshot
    assert len(set(map(tuple, sims))) > 1          # different policies, different outcomes
    # The original continues normally after the simulations.
    assert sum(play_out(st, random_policy(0))) == 0


def test_same_deck_same_result() -> None:
    a = play_out(new_state(VariantSpec(), 5), random_policy(1))
    b = play_out(new_state(VariantSpec(), 5), random_policy(1))
    assert a == b


def test_no_record_mode_has_no_events() -> None:
    st = GameState(to_rules(VariantSpec()), deck_for(1, 0), [400, 400], record=False)
    play_out(st, random_policy(2))
    assert st.events == [] and st.done

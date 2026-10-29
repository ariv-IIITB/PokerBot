"""Phase B: Discard Hold'em (docs/rules: Rulebook 4, Protocol 4/7/9/10), as scenarios on rigged decks.

Role names: SB = the button (posts the small blind, acts first preflop), BB acts first postflop.
Hole cards are listed in dealt order; "discard Kd" names the card, the kit maps it to its index.
"""
import pytest
from kit.scenario import Scenario, ScenarioError, rigged_deck, run_scenario

from bot.actions import Action, LegalActions, SpecialOption
from bot.cards import format_card, parse_card, parse_cards
from bot.game.observation import observe
from bot.game.rules_spec import to_rules
from bot.game.state import ALL
from bot.game.steps.cards import fallback_discard, safe_action_for_hole
from lab.engine import Hand, Seat, play_match
from lab.players import PlayerSpec
from variant.spec import VariantSpec, load_catalog

SPEC = "discard_holdem"
HOLES = {"SB": ["As", "Kd", "7c"], "BB": ["Qs", "9h", "9c"]}
BOARD = ["Ah", "7d", "2s", "3c", "4h"]


def scenario(steps, expect=None, holes=HOLES, board=BOARD, stacks=None,
             unfinished=False) -> Scenario:
    return Scenario(SPEC, holes, board, steps, expect or {}, stacks, unfinished=unfinished)


def to_flop(extra=()):
    """SB limps, BB checks: both in for 2 each, flop next (BB acts first)."""
    return [("SB", "call", {}), ("BB", "check", {})] + list(extra)


# --------------------------------------------------------------------------- the spec

def test_spec_matches_the_rulebook() -> None:
    spec = load_catalog()[SPEC]
    assert spec.validate() == []
    b, m = spec.betting, spec.match
    assert (b.small_blind, b.big_blind, b.max_raises, b.blind_counts_as_raise) == (1, 2, 4, True)
    assert (m.starting_stack, m.reset_stacks, m.hands, m.time_bank_s) == (200, True, 400, 60.0)
    kinds = [s["type"] for s in spec.full_program()]
    assert kinds == ["post_blinds", "deal_hole", "betting", "deal_board", "betting", "discard",
                     "deal_board", "betting", "deal_board", "betting", "showdown"]
    assert spec.full_program()[1]["n"] == 3
    rules = to_rules(spec)
    assert rules.hole_cards == 3 and rules.board_cards == 5


def test_active_variant_is_discard_holdem() -> None:
    from bot.game.rules_spec import active_rules
    assert active_rules().name == SPEC


def test_blind_flag_is_off_for_every_other_preset() -> None:
    for name, spec in load_catalog().items():
        assert spec.betting.blind_counts_as_raise == (name == SPEC), name


def test_flag_needs_a_raise_cap() -> None:
    spec = VariantSpec.from_dict({"betting": {"blind_counts_as_raise": True}})
    assert any("max_raises" in p for p in spec.validate())


def test_flag_changes_the_spec_hash_only_when_on() -> None:
    from variant.spec import spec_hash
    base = VariantSpec.from_dict({"betting": {"max_raises": 4}})
    on = VariantSpec.from_dict({"betting": {"max_raises": 4, "blind_counts_as_raise": True}})
    assert spec_hash(base) != spec_hash(on)
    assert spec_hash(base) == spec_hash(VariantSpec.from_dict({"betting": {"max_raises": 4,
                                                          "blind_counts_as_raise": False}}))


# --------------------------------------------------------------------------- worked example

def test_protocol_section_10_example_hand() -> None:
    """Button raises to 6, BB calls; flop bet 6 called; discards Kd / Qs; river bet 10, fold."""
    run_scenario(scenario(
        [("SB", "raise 6", {"legal": {"fold", "call", "raise"}, "min": 4, "max": 200,
                            "street": "preflop", "pot": 3, "tocall": 1}),
         ("BB", "call", {"tocall": 4}),
         ("BB", "check", {"street": "flop", "pot": 12, "legal": {"check", "raise"},
                          "min": 2, "max": 194}),
         ("SB", "raise 6", {"min": 2}),
         ("BB", "call", {"tocall": 6}),
         ("SB", "discard Kd", {"street": "flop", "pot": 24, "legal": {"discard"},
                               "options": ("0", "1", "2"), "stack": 188}),
         ("BB", "discard Qs", {"options": ("0", "1", "2")}),
         ("BB", "check", {"street": "turn", "pot": 24, "min": 2, "max": 188}),
         ("SB", "check", {}),
         ("BB", "check", {"street": "river"}),
         ("SB", "raise 10", {}),
         ("BB", "fold", {"tocall": 10})],
        {"deltas": {"SB": 12, "BB": -12}, "showdown": False, "folded": "BB",
         "muck": ["Kd", "Qs"], "hole": {"SB": ["As", "7c"], "BB": ["9h", "9c"]}}))


# --------------------------------------------------------------------------- raise cap

def test_preflop_allows_exactly_three_voluntary_raises() -> None:
    run_scenario(scenario(
        [("SB", "raise 4", {"legal": {"fold", "call", "raise"}}),     # raise 1 (BB was the 0th)
         ("BB", "raise 6", {"min": 6}),                                # raise 2
         ("SB", "raise 8", {"min": 8}),                                # raise 3: the cap
         ("BB", "call", {"legal": {"fold", "call"}, "tocall": 2})],  # no raise offered
        unfinished=True))                                            # the flop is next
    st = run_scenario(scenario(
        [("SB", "raise 4", {}), ("BB", "raise 6", {}), ("SB", "raise 8", {}),
         ("BB", "fold", {"legal": {"fold", "call"}})], {"folded": "BB"}))
    assert st.raises == 4


def test_postflop_allows_exactly_four_bets_or_raises() -> None:
    steps = to_flop([("BB", "raise 2", {"legal": {"check", "raise"}, "min": 2}),
                     ("SB", "raise 4", {"min": 4}), ("BB", "raise 6", {"min": 6}),
                     ("SB", "raise 8", {"min": 8, "legal": {"fold", "call", "raise"}}),
                     ("BB", "call", {"legal": {"fold", "call"}, "tocall": 2}),
                     ("SB", "discard Kd", {}), ("BB", "discard Qs", {}),
                     # the count resets on the turn
                     ("BB", "raise 2", {"street": "turn", "legal": {"check", "raise"}})])
    run_scenario(scenario(steps + [("SB", "fold", {})], {"folded": "SB"}))


# --------------------------------------------------------------------------- minimum raise

def test_minimum_raises() -> None:
    run_scenario(scenario(
        [("SB", "raise 6", {"min": 4}),                    # first preflop minimum is 4
         ("BB", "call", {"min": 10}),                      # re-raise after a raise to 6: 6 + 4
         ("BB", "check", {"min": 2, "street": "flop"}),    # no bet yet: 2
         ("SB", "raise 10", {"min": 2}),
         ("BB", "call", {"min": 20}),                      # after a bet of 10: 10 + 10
         ("SB", "discard Kd", {}), ("BB", "discard Qs", {}),
         ("BB", "check", {"street": "turn", "min": 2}), ("SB", "check", {}),
         ("BB", "check", {"street": "river"}), ("SB", "check", {})],
        {"showdown": True}))


def test_minimum_raise_follows_the_last_raise_size() -> None:
    run_scenario(scenario(
        [("SB", "raise 4", {}), ("BB", "raise 12", {"min": 6}),      # a raise of 8 ...
         ("SB", "raise 20", {"min": 20}),                             # ... so the next minimum is 12 + 8
         ("BB", "call", {"tocall": 8})], unfinished=True))


def test_all_in_below_the_minimum_is_the_only_raise() -> None:
    run_scenario(scenario(
        [("SB", "raise 199", {"max": 200}),
         ("BB", "raise 200", {"legal": {"fold", "call", "raise"}, "min": 200, "max": 200}),
         ("SB", "call", {"legal": {"fold", "call"}}),
         ("SB", "discard Kd", {}), ("BB", "discard Qs", {})],
        {"showdown": True, "deltas": {"SB": 200, "BB": -200}}))


# --------------------------------------------------------------------------- discard rules

def test_no_discard_when_someone_folds() -> None:
    run_scenario(scenario([("SB", "fold", {})],
                          {"folded": "SB", "deltas": {"SB": -1, "BB": 1}, "muck": [],
                           "hole": {"SB": HOLES["SB"], "BB": HOLES["BB"]}}))
    run_scenario(scenario(to_flop([("BB", "raise 2", {}), ("SB", "fold", {})]),
                          {"folded": "SB", "muck": [], "deltas": {"SB": -2, "BB": 2},
                           "hole": {"SB": HOLES["SB"], "BB": HOLES["BB"]}}))


def test_discard_still_happens_when_both_are_all_in_preflop() -> None:
    run_scenario(scenario(
        [("SB", "raise 200", {}), ("BB", "call", {}),
         ("SB", "discard Kd", {"street": "flop", "legal": {"discard"}, "pot": 400, "stack": 0}),
         ("BB", "discard Qs", {})],
        {"showdown": True, "muck": ["Kd", "Qs"], "hole": {"SB": ["As", "7c"], "BB": ["9h", "9c"]},
         "deltas": {"SB": 200, "BB": -200}}))      # SB: two pair (aces and sevens) beats nines


def test_discards_are_public_and_dead() -> None:
    st = run_scenario(scenario(
        to_flop([("BB", "check", {}), ("SB", "check", {}),
                 ("SB", "discard Kd", {}), ("BB", "discard Qs", {}),
                 ("BB", "check", {}), ("SB", "check", {}), ("BB", "check", {}), ("SB", "check", {})]),
        {"showdown": True, "muck": ["Kd", "Qs"]}))
    kd, qs = parse_card("Kd"), parse_card("Qs")
    reveals = [(e.player, e.visible, e.data["cards"]) for e in st.events if e.kind == "reveal"]
    assert reveals == [(0, ALL, (kd,)), (1, ALL, (qs,))]        # public: visible to both
    for p in (0, 1):
        assert {kd, qs} <= observe(p=p, st=st).seen_cards
    assert kd not in st.board and qs not in st.board
    assert kd not in sum(st.hole, []) and qs not in sum(st.hole, [])
    assert len(st.board) == 5 and all(len(h) == 2 for h in st.hole)


def test_showdown_uses_the_two_remaining_cards() -> None:
    """SB's pair of sevens would win, but SB discards one: A-K-Q-7-4 loses to A-K-Q-9-8."""
    holes = {"SB": ["7h", "7c", "2d"], "BB": ["9s", "8s", "5d"]}
    board = ["Ah", "Kd", "Qs", "3c", "4h"]
    run_scenario(Scenario(SPEC, holes, board,
                          to_flop([("BB", "check", {}), ("SB", "check", {}),
                                   ("SB", "discard 7c", {}), ("BB", "discard 5d", {}),
                                   ("BB", "check", {}), ("SB", "check", {}),
                                   ("BB", "check", {}), ("SB", "check", {})]),
                          {"showdown": True, "deltas": {"SB": -2, "BB": 2}}))


def test_scenario_kit_rejects_a_wrong_discard_expectation() -> None:
    with pytest.raises(ScenarioError, match="muck"):
        run_scenario(scenario(
            to_flop([("BB", "check", {}), ("SB", "check", {}), ("SB", "discard Kd", {}),
                     ("BB", "discard Qs", {}), ("BB", "check", {}), ("SB", "check", {}),
                     ("BB", "check", {}), ("SB", "check", {})], ), {"muck": ["Kd", "9h"]}))


# --------------------------------------------------------------------------- fallbacks

@pytest.mark.parametrize("hole,discarded", [
    ("7s,7c,Kd", "7s"), ("2h,2d,Ac", "2h"), ("Ts,Jh,9c", "9c"),
    ("As,Ah,Ad", "As"), ("2c,2d,2h", "2h"), ("Ks,Qd,2c", "2c"), ("Ad,Ac,3s", "3s")])
def test_fallback_discard(hole, discarded) -> None:
    cards = list(parse_cards(hole))
    assert format_card(fallback_discard(cards)) == discarded


def test_safe_action_for_hole() -> None:
    discard = LegalActions(special=SpecialOption("discard", ("0", "1", "2")))
    hole = list(parse_cards("Ts,Jh,9c"))
    assert safe_action_for_hole(discard, hole) == Action.special("2")
    assert safe_action_for_hole(discard, ()) == Action.special("0")          # no cards known
    assert safe_action_for_hole(LegalActions(check=True, raise_min=2, raise_max=9), hole) == \
        Action.check()
    assert safe_action_for_hole(LegalActions(fold=True, call=True), hole) == Action.fold()
    other = LegalActions(special=SpecialOption("draw", ("none", "0")))      # not a discard
    assert safe_action_for_hole(other, hole) == Action.special("none")


class Scripted:
    """An in-process player replying from a function; records what it was told."""
    name = "scripted"

    def __init__(self, reply) -> None:
        self.reply, self.msgs = reply, []

    def notify(self, msg) -> None:
        self.msgs.append(msg)

    def act(self, req):
        self.msgs.append(req)
        return self.reply(req)

    def close(self) -> None:
        pass


def _hand(p_sb, p_bb, holes=HOLES, board=BOARD, on_illegal="fold") -> tuple:
    rules = to_rules(load_catalog()[SPEC])
    deck = rigged_deck(rules, holes, board)
    seats = [Seat(p_sb, 60.0), Seat(p_bb, 60.0)]
    res = Hand(rules, seats, [200, 200], deck, 0, on_illegal, audit=True).play()
    return res, seats


def _passive(req):
    if req.legal.can_special:
        return Action.special("0")
    return Action.check() if req.legal.check else Action.call()


def test_illegal_discard_discards_the_lowest_card() -> None:
    bad = Scripted(lambda r: Action.special("7") if r.legal.can_special else _passive(r))
    other = Scripted(_passive)
    res, seats = _hand(bad, other)
    assert seats[0].errors == 1 and seats[1].errors == 0
    from bot.protocol import Info
    mine = [m for m in bad.msgs if isinstance(m, Info) and m.kind == "reveal" and m.who == "me"]
    assert [format_card(c) for c in mine[0].cards] == ["7c"]       # lowest of As Kd 7c
    theirs = [m for m in other.msgs if isinstance(m, Info) and m.kind == "reveal" and m.who == "opp"]
    assert [format_card(c) for c in theirs[0].cards] == ["7c"]


def test_missing_discard_reply_discards_the_lowest_card() -> None:
    other = Scripted(_passive)
    bad = Scripted(lambda r: "garbage" if r.legal.can_special else _passive(r))
    res, seats = _hand(other, bad, holes={"SB": ["As", "Kd", "7c"], "BB": ["2h", "2d", "Ac"]})
    assert seats[1].errors == 1
    revealed = [m for m in other.msgs if type(m).__name__ == "Info" and m.who == "opp"]
    assert [format_card(c) for c in revealed[0].cards] == ["2h"]   # equal ranks: hearts before diamonds


def test_illegal_action_becomes_check_or_fold() -> None:
    def junk(req):
        return Action.raise_to(1) if not req.legal.can_special else Action.special("0")
    other = Scripted(_passive)
    # SB faces a to-call of 1 preflop: checking is illegal, so the illegal raise becomes a fold
    res, seats = _hand(Scripted(junk), other)
    assert res.folded == 0 and res.deltas == [-1, 1] and seats[0].errors == 1
    # BB checks its option instead: the hand goes on to showdown
    res, seats = _hand(Scripted(_passive), Scripted(junk))
    assert res.folded is None and res.showdown and seats[1].errors >= 3


# --------------------------------------------------------------------------- fuzz

@pytest.mark.parametrize("brains", [("random_legal", "random_legal"), ("maniac", "random_legal"),
                                    ("calling_station", "all_in")])
def test_fuzz_conserves_chips_and_hides_cards(brains) -> None:
    """500 hands per match (audit=True checks every event's visibility and chip conservation)."""
    spec = load_catalog()[SPEC]
    for seed in (1, 2):
        players = [PlayerSpec.brain(b, {"seed": seed + i}).build() for i, b in enumerate(brains)]
        res = play_match(players, spec, seed, 500, audit=True)
        assert res.hands_played == 500 and res.forfeit is None
        assert sum(res.chips) == 0
        assert res.errors == [0, 0]

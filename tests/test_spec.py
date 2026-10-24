"""Variant spec schema: defaults, JSON round-trips, validation messages, compilation."""
import json

import pytest

from bot.game.compile import NotSupported, compile_spec
from bot.game.rules_spec import active_rules, to_rules
from lab.random_variant import random_spec, random_supported_spec
from variant.spec import SpecError, VariantSpec, default_program, load_catalog


def test_defaults_are_holdem() -> None:
    spec = VariantSpec()
    assert spec.validate() == []
    assert spec.step_types() == [s["type"] for s in default_program()]
    rules = compile_spec(spec)
    assert len(rules.deck) == 52 and rules.streets == (0, 3, 1, 1)
    assert [s.type_name for s in rules.program] == [
        "post_blinds", "deal_hole", "betting", "deal_board", "betting", "deal_board",
        "betting", "deal_board", "betting", "showdown"]


def test_json_round_trip() -> None:
    for spec in load_catalog().values():
        again = VariantSpec.from_json(spec.to_json())
        assert again == spec


def test_unknown_keys_rejected() -> None:
    with pytest.raises(SpecError, match="unknown top-level keys"):
        VariantSpec.from_dict({"name": "x", "bogus": 1})
    with pytest.raises(SpecError, match="deck: unknown keys"):
        VariantSpec.from_dict({"deck": {"rank": "AKQ"}})


def errors(**kw) -> str:
    return "\n".join(VariantSpec.from_dict(kw).validate())


def test_card_count_message() -> None:
    msg = errors(deck={"ranks": "6789TJQKA"}, hole_cards=6, streets=[0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1])
    assert "deck has 36 cards but the program deals" in msg


@pytest.mark.parametrize("kw,fragment", [
    ({"program": [{"type": "post_blinds"}, {"type": "betting"}]}, "must end with a showdown"),
    ({"program": [{"type": "deal_hole"}, {"type": "showdown"}]}, "at least one betting step"),
    ({"program": [{"type": "post_blinds"}, {"type": "teleport"}, {"type": "betting"},
                  {"type": "showdown"}]}, "unknown step type 'teleport'"),
    ({"program": [{"type": "post_blinds"}, {"type": "deal_hole", "n": 2, "colour": 1},
                  {"type": "betting"}, {"type": "showdown"}]}, "unknown parameters ['colour']"),
    ({"betting": {"small_blind": 5, "big_blind": 2}}, "small_blind <= big_blind"),
    ({"betting": {"structure": "FL"}}, "fixed-limit needs betting.fixed_bets"),
    ({"evaluation": {"hole_exact": 3}}, "hole_exact 3 > hole cards"),
    ({"evaluation": {"hand_size": 9}}, "hand_size must be 1..7"),
    ({"evaluation": {"category_order": ["flush"]}}, "category_order must be a permutation"),
    ({"evaluation": {"wild": {"jokers": True}}}, "deck has none"),
    ({"match": {"starting_stack": 2}}, "must exceed blinds"),
    ({"deck": {"removed": ["Zz"]}}, "not a card of this deck"),
    ({"hole_cards": 1, "streets": [0, 1], "evaluation": {"hand_size": 5}}, "needs more cards"),
    ({"payoffs": [{"type": "lottery"}]}, "unknown type 'lottery'"),
])
def test_validation_messages(kw, fragment) -> None:
    assert fragment in errors(**kw)


def test_check_raises_with_all_messages() -> None:
    with pytest.raises(SpecError) as e:
        VariantSpec.from_dict({"betting": {"big_blind": 0}, "match": {"hands": 0}}).check()
    assert "big_blind > 0" in str(e.value) and "match.hands" in str(e.value)


def test_not_supported_names_phase() -> None:
    """Features without a plugin raise NotSupported naming where support would come from."""
    prog = default_program()
    prog.insert(3, {"type": "swap", "n": 2})
    with pytest.raises(NotSupported) as e:
        compile_spec(VariantSpec.from_dict({"hole_cards": 3, "program": prog}))
    assert f"phase {e.value.phase}" in str(e.value) and "more than one card" in str(e.value)


def test_compiled_program_describes_itself() -> None:
    text = compile_spec(load_catalog()["burn_revealed"]).describe()
    assert "burn 1 face up, then deal 3 board cards" in text


def test_random_specs_valid_and_deterministic() -> None:
    for seed in range(40):
        spec = random_spec(seed)
        assert spec.validate() == []
        assert random_spec(seed) == spec
    compile_spec(random_supported_spec(3))


def test_active_rules_env_override(tmp_path, monkeypatch) -> None:
    path = tmp_path / "v.json"
    path.write_text(json.dumps({"name": "omaha_test", "hole_cards": 4,
                                "evaluation": {"hole_exact": 2}}))
    monkeypatch.setenv("POKERBOT_VARIANT", str(path))
    assert active_rules().name == "omaha_test"
    path.write_text("{broken")
    assert active_rules().name in ("config", "holdem")      # falls back, never raises


def test_to_rules_accepts_everything() -> None:
    from variant.rules import GameConfig
    r = to_rules(VariantSpec())
    assert to_rules(r) is r and to_rules(GameConfig()).streets == (0, 3, 1, 1)

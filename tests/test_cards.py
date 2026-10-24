import pytest

from bot.cards import (DECK_SIZE, format_card, format_cards, parse_card, parse_cards,
                       rank_of, remaining_deck, suit_of)


def test_round_trip_all_cards() -> None:
    for c in range(DECK_SIZE):
        assert parse_card(format_card(c)) == c


def test_encoding_layout() -> None:
    assert parse_card("2c") == 0
    assert parse_card("As") == 51
    assert rank_of(parse_card("Kd")) == 11 and suit_of(parse_card("Kd")) == 1
    assert parse_card("ah") == parse_card("Ah")


def test_lists() -> None:
    assert parse_cards("-") == () and parse_cards("") == ()
    assert format_cards(()) == "-"
    assert format_cards(parse_cards("Ah,Kd,Tc")) == "Ah,Kd,Tc"


@pytest.mark.parametrize("bad", ["", "A", "Ahh", "1h", "Ax", "10h"])
def test_bad_card(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_card(bad)


def test_duplicates_rejected() -> None:
    with pytest.raises(ValueError):
        parse_cards("Ah,Ah")


def test_remaining_deck() -> None:
    rest = remaining_deck(parse_cards("Ah,Kd"))
    assert len(rest) == 50 and parse_card("Ah") not in rest

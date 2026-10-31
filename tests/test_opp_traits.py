"""X0: opponent records and the profile table (lab.opps.record, lab.opps.traits).

Unit tests pin each column's definition on hand-built hands. The fixture test checks that the
recorded matches in tests/fixtures/opp_records/ reproduce the book's profile table (Tier 3,
lock off, 9,600 hands per opponent; docs/book/pokerbot_book.html section 2.8) within sampling
error: the fixtures hold 4 matches (1,600 hands) per opponent.
"""
import math
from pathlib import Path

import pytest

from bot.cards import parse_card
from lab.opps import record, traits

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "opp_records"


def c(text: str) -> list[int]:
    return [parse_card(text[i:i + 2]) for i in range(0, len(text), 2)]


def hand(h, seat=0, hole3="AsKs2c", hole="AsKs", board="", opp="", delta=0, rv=()) -> dict:
    return {"id": 0, "seat": seat, "hole3": c(hole3), "hole": c(hole), "board": c(board),
            "opp": c(opp), "delta": delta, "h": [list(a) for a in h],
            "rv": [[who, c(cards)] for who, cards in rv]}


# --------------------------------------------------------------------------- definitions

def test_vpip_and_pfr_count_hands_where_the_opponent_had_a_preflop_decision() -> None:
    hands = [
        hand([(0, "m", "R", 5, None), (0, "o", "C", None, None)]),                # vpip
        hand([(0, "o", "R", 6, None), (0, "m", "F", None, None)], seat=1),        # vpip + pfr
        hand([(0, "m", "C", None, None), (0, "o", "K", None, None)]),             # BB checks: no
        hand([(0, "m", "F", None, None)]),                                         # no decision
    ]
    p = traits.profile(hands)
    assert (p["vpip"].hits, p["vpip"].n) == (2, 3)
    assert (p["pfr"].hits, p["pfr"].n) == (1, 3)


def test_fold_to_our_bet_counts_each_decision_facing_our_bet_per_street() -> None:
    pre = [(0, "m", "R", 5, None), (0, "o", "C", None, None)]
    hands = [
        hand(pre + [(1, "o", "K", None, None), (1, "m", "R", 4, None), (1, "o", "F", None, None)],
             board="2h7d9c"),
        hand(pre + [(1, "o", "K", None, None), (1, "m", "R", 4, None), (1, "o", "R", 12, None),
                    (1, "m", "R", 30, None), (1, "o", "C", None, None),
                    (1, "m", "S", None, "2"), (1, "o", "S", None, "0"),
                    (2, "o", "K", None, None), (2, "m", "K", None, None),
                    (3, "o", "K", None, None), (3, "m", "R", 40, None), (3, "o", "F", None, None)],
             board="2h7d9cTsJs"),
    ]
    p = traits.profile(hands)
    assert (p["fold_flop"].hits, p["fold_flop"].n) == (1, 3)      # F, R, C
    assert p["fold_turn"].n == 0
    assert (p["fold_river"].hits, p["fold_river"].n) == (1, 1)


def test_bet_river_counts_unfaced_river_decisions_and_after_check_needs_our_check() -> None:
    pre = [(0, "o", "C", None, None), (0, "m", "K", None, None)]
    flop_turn = [(1, "m", "K", None, None), (1, "o", "K", None, None),
                 (2, "m", "K", None, None), (2, "o", "K", None, None)]
    hands = [
        hand(pre + flop_turn + [(3, "m", "K", None, None), (3, "o", "R", 10, None),
                                (3, "m", "F", None, None)], seat=1, board="2h7d9cTsJs"),
        hand(pre + flop_turn + [(3, "m", "K", None, None), (3, "o", "K", None, None)],
             seat=1, board="2h7d9cTsJs"),
        # the opponent acts first on the river (we are the button): a lead, not after our check
        hand([(0, "m", "C", None, None), (0, "o", "K", None, None)]
             + [(1, "o", "K", None, None), (1, "m", "K", None, None),
                (2, "o", "K", None, None), (2, "m", "K", None, None),
                (3, "o", "R", 10, None), (3, "m", "F", None, None)], board="2h7d9cTsJs"),
    ]
    p = traits.profile(hands)
    assert (p["bet_river"].hits, p["bet_river"].n) == (2, 3)
    assert (p["bet_river_after_check"].hits, p["bet_river_after_check"].n) == (1, 2)


def test_weak_shown_river_bet_and_wtsd_and_discard_lowest() -> None:
    line = [(0, "m", "C", None, None), (0, "o", "K", None, None),
            (1, "o", "K", None, None), (1, "m", "K", None, None),
            (2, "o", "K", None, None), (2, "m", "K", None, None),
            (3, "o", "R", 10, None), (3, "m", "C", None, None)]
    board = "2h7d9cTsKd"
    bluff = hand(line, board=board, opp="3c4s", rv=[("m", "2c"), ("o", "Ah")], delta=10)
    nuts = hand(line, board=board, opp="KhKc", rv=[("m", "2c"), ("o", "5h")], delta=-10)
    folded_pre = hand([(0, "m", "R", 5, None), (0, "o", "F", None, None)])
    p = traits.profile([bluff, nuts, folded_pre])
    assert (p["weak_river_bet"].hits, p["weak_river_bet"].n) == (1, 2)
    assert (p["wtsd"].hits, p["wtsd"].n) == (2, 2)                 # two hands saw a flop
    # 3c4s + Ah discarded: not the lowest; KhKc + 5h: the lowest
    assert (p["discard_lowest"].hits, p["discard_lowest"].n) == (1, 2)


def test_discard_lowest_counts_a_tie_as_lowest() -> None:
    line = [(0, "m", "C", None, None), (0, "o", "K", None, None)]
    h = hand(line, board="2h7d9cTsKd", opp="5c9s", rv=[("o", "5d"), ("m", "2c")])
    assert traits.profile([h])["discard_lowest"].hits == 1


def test_match_summary_is_per_duplicate_pair() -> None:
    data = {"pairs": [
        {"seed": 0, "matches": [{"chips": 100, "score": 1.0, "hands": [{}] * 10},
                                {"chips": -40, "score": 0.0, "hands": [{}] * 10}]},
        {"seed": 1, "matches": [{"chips": 20, "score": 1.0, "hands": [{}] * 10},
                                {"chips": 0, "score": 0.5, "hands": [{}] * 10}]},
    ]}
    s = traits.match_summary(data)
    assert s["chips_per_hand"] == pytest.approx((60 / 20 + 20 / 20) / 2)
    assert s["wins"] == pytest.approx(2.5 / 4)
    assert s["matches"] == 4


# --------------------------------------------------------------------------- recorder

def test_hand_record_round_trips_through_a_hand_state() -> None:
    rec = hand([(0, "m", "R", 5, None), (0, "o", "C", None, None),
                (1, "m", "S", None, "2"), (1, "o", "S", None, "0")],
               board="2h7d9cTsKd", opp="3c4s", rv=[("m", "2c"), ("o", "Ah")], delta=-7)
    assert record.hand_record(record.to_hand_state(rec)) == rec


def test_record_pair_saves_every_hand_from_our_side() -> None:
    from lab.harness import load_variant
    from lab.players import PlayerSpec

    cfg = load_variant("discard_holdem")
    pair = record.record_pair(PlayerSpec.brain("tier1"), PlayerSpec.brain("calling_station"),
                              cfg, seed=3, hands=6)
    assert [len(m["hands"]) for m in pair["matches"]] == [6, 6]
    first = pair["matches"][0]["hands"]
    assert [h["seat"] for h in first] == [0, 1, 0, 1, 0, 1]     # we start on the button
    assert sum(h["delta"] for h in first) == pair["matches"][0]["chips"]
    assert all(len(h["hole3"]) == 3 for h in first)
    flops = [h for h in first if len(h["board"]) == 5]
    assert all(len(h["hole"]) == 2 and len(h["rv"]) == 2 for h in flops)


# --------------------------------------------------------------------------- the book's table

# Book section 2.8 (Tier 3 lock off, 24 matches x 400 hands per opponent). None = no data.
BOOK = {
    #                 vpip  pfr  f_flop f_turn f_river bet_rv weak  wtsd  disc_low
    "d_conv_opp3":     (.82, .35, .42, .68, .72, .46, .19, .22, .62),
    "d_new_rules":     (.77, .41, .62, .59, .59, .35, .05, .38, .62),
    "d_new_lag":       (.90, .59, .12, .18, .40, .66, .19, .39, .60),
    "d_new_trapper":   (.50, .03, .32, .21, .22, .24, .00, .61, .65),
    "d_new_exploiter": (.80, .32, .65, .79, .79, .34, .04, .26, .61),
    "d_new_minraise":  (.79, .52, .47, .40, .44, .44, .04, .45, .68),
    "starter":         (.80, .00, .00, .00, .00, .00, None, 1.0, 1.0),
    "calling_station": (.80, .00, .00, .00, .00, .00, None, 1.0, .36),
    "tight":           (.42, .09, .30, .30, .08, .36, .09, .52, .40),
    "maniac":          (.96, .74, .02, .03, .02, .70, .50, .69, .35),
    "random_legal":    (.64, .36, .37, .38, .47, .49, .51, .37, .36),
}
COLUMNS = ("vpip", "pfr", "fold_flop", "fold_turn", "fold_river", "bet_river",
           "weak_river_bet", "wtsd", "discard_lowest")
SLACK = 0.06       # definition / Tier 3 version differences on top of sampling error
MIN_N = 20


def _fixture(name: str) -> Path:
    return FIXTURES / f"{name}.json.gz"


@pytest.mark.parametrize("name", sorted(BOOK))
def test_fixtures_reproduce_the_book_profile_table(name: str) -> None:
    path = _fixture(name)
    if not path.is_file():
        pytest.fail(f"missing fixture {path} (record with lab.opps.record, then lab.opps.traits --fixtures)")
    data = record.load(path)
    assert sum(len(p["matches"]) for p in data["pairs"]) == 4
    prof = traits.profile(record.iter_hands(data))
    bad = []
    for col, book in zip(COLUMNS, BOOK[name]):
        rate = prof[col]
        if book is None or rate.n < MIN_N:
            continue
        tol = 3 * math.sqrt(max(book * (1 - book), 0.02) / rate.n) + SLACK
        if abs(rate.value - book) > tol:
            bad.append(f"{col}: {rate.value:.2f} (n={rate.n}) vs book {book:.2f} ± {tol:.2f}")
    assert not bad, f"{name}: " + "; ".join(bad)


def test_fixtures_stay_small() -> None:
    total = sum(p.stat().st_size for p in FIXTURES.glob("*.json.gz"))
    assert 0 < total < 1_000_000

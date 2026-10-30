"""Phase G: pot arithmetic (the spec's numbers) and board / draw features on hand-picked boards."""
import pytest

from bot.cards import parse_cards as P
from bot.strategy.potmath import bluff_share, mdf, required_fold, spr
from bot.strategy.texture import best_keep, blocker_score, board_texture, draw_features


# --------------------------------------------------------------------------- pot math

@pytest.mark.parametrize("frac, mdf_, share", [(1 / 3, 0.75, 0.20), (2 / 3, 0.60, 2 / 7),
                                              (0.75, 4 / 7, 0.30), (1.0, 0.50, 1 / 3)])
def test_spec_numbers(frac: float, mdf_: float, share: float) -> None:
    pot = 100.0
    assert mdf(frac * pot, pot) == pytest.approx(mdf_, abs=0.005)
    assert bluff_share(frac * pot, pot) == pytest.approx(share, abs=0.005)
    assert required_fold(frac * pot, pot) == pytest.approx(1 - mdf_, abs=1e-9)


def test_degenerate_inputs() -> None:
    assert mdf(0, 100) == 1.0 and required_fold(0, 100) == 0.0 and bluff_share(0, 100) == 0.0
    assert mdf(0, 0) == 1.0 and required_fold(0, 0) == 0.0
    assert spr(100, 50) == 2.0 and spr(100, 0) == float("inf")


# --------------------------------------------------------------------------- texture

def test_dry_high_card_board() -> None:
    t = board_texture(P("Ad,7c,2h"))
    assert not t.paired and t.suit_max == 1 and not t.connected
    assert t.wet < 0.2 and t.high_dry and not t.low_connected


def test_wet_connected_two_tone_board() -> None:
    t = board_texture(P("9h,8h,6d"))
    assert t.two_tone and t.connected and t.straight_window == 3
    assert t.wet > 0.5 and not t.high_dry
    assert t.low_connected                      # nine-high and connected: favours the caller


def test_monotone_and_paired_boards() -> None:
    mono = board_texture(P("Kh,9h,3h"))
    assert mono.monotone and mono.suit_max == 3 and mono.wet >= 0.5
    paired = board_texture(P("Qs,Qd,4c"))
    assert paired.paired and not paired.trips and paired.wet < 0.2
    trips = board_texture(P("7s,7d,7c"))
    assert trips.trips and trips.paired


def test_turn_and_river_boards() -> None:
    t = board_texture(P("9h,8h,6d,7c"))
    assert t.straight_window == 4 and t.wet >= 0.6
    r = board_texture(P("Kh,9h,3h,2h,Ah"))
    assert r.suit_max == 5 and r.monotone


# --------------------------------------------------------------------------- draws

def test_pair_types() -> None:
    assert draw_features(P("Ah,3c"), P("As,7d,2h")).pair_type == "top"
    assert draw_features(P("7h,3c"), P("As,7d,2h")).pair_type == "second"
    assert draw_features(P("2h,3c"), P("As,7d,2s")).pair_type == "third"
    assert draw_features(P("Kh,Kc"), P("9s,7d,2h")).pair_type == "overpair"
    assert draw_features(P("9h,9c"), P("As,7d,2h")).pair_type == "second"      # pocket pair under one board card
    assert draw_features(P("3h,3c"), P("As,Kd,Qh")).pair_type == "under"
    assert draw_features(P("Kh,Qc"), P("9s,7d,2h")).pair_type == "none"
    assert draw_features(P("Ah,7c"), P("As,7d,2h")).pair_type == "two_pair"
    assert draw_features(P("7h,7c"), P("As,7d,2h")).pair_type == "set_plus"


def test_flush_draws() -> None:
    d = draw_features(P("Ah,5h"), P("Kh,9h,2c"))
    assert d.flush_draw == 2 and d.nut_flush_draw and d.outs_class == "strong"
    d = draw_features(P("Qh,5c"), P("Kh,9h,2h"))
    assert d.flush_draw == 1 and not d.nut_flush_draw      # one card of the suit, board has three
    d = draw_features(P("Ah,5h"), P("Kc,9h,2d"))
    assert d.flush_draw == 0 and d.backdoor_flush
    d = draw_features(P("Ah,5h"), P("Kh,9h,2h"))
    assert d.made_straight_or_better and d.flush_draw == 0     # a made flush is not a draw


def test_straight_draws() -> None:
    open_ended = draw_features(P("8c,7d"), P("9h,6s,2c"))
    assert open_ended.straight_outs == 2 and open_ended.outs_class == "strong"
    gut = draw_features(P("Jc,9d"), P("8h,7s,2c"))
    assert gut.straight_outs == 1 and gut.outs_class == "gutshot"
    wheel = draw_features(P("Ac,2d"), P("3h,4s,Kc"))
    assert wheel.straight_outs >= 1                       # A-2-3-4 wants a five (and a six... ace low)
    made = draw_features(P("Tc,9d"), P("8h,7s,6c"))
    assert made.made_straight_or_better and made.straight_outs == 0
    board_only = draw_features(P("2c,2d"), P("9h,8s,7c,6d"))
    assert board_only.straight_outs == 0 or board_only.pair_type != "none"      # the board's draw is not ours


def test_overcards_and_backdoors() -> None:
    d = draw_features(P("Ac,Kd"), P("9h,6s,2c"))
    assert d.overcards == 2 and d.pair_type == "none" and not d.has_showdown_value
    bd = draw_features(P("Th,9c"), P("8d,2s,2c"))
    assert bd.straight_outs >= 1 or bd.backdoor_straight


def test_best_keep_of_three() -> None:
    keep, d = best_keep(P("Ah,Kd,7c"), P("As,7d,2h"))
    assert set(keep) == set(P("Ah,7c")) and d.pair_type == "two_pair"
    keep, d = best_keep(P("Kh,Qh,2c"), P("Jh,9h,3c"))
    assert set(keep) == set(P("Kh,Qh")) and d.flush_draw == 2
    keep2, _ = best_keep(P("Ah,Kd"), P("2s,7d,9h"))
    assert set(keep2) == set(P("Ah,Kd"))


def test_blockers() -> None:
    assert blocker_score(P("Ah,2c"), P("Kh,9h,3h,5d,7s")) == 1.0       # the nut flush blocker
    assert blocker_score(P("Qc,2c"), P("Kh,9h,3h,5d,7s")) == 0.0
    assert blocker_score(P("Kc,2d"), P("Kh,9h,3c,5d,7s")) == 0.5       # a top board rank

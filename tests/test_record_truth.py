"""S0: the recorder stores the opponent's dealt cards (opp_hole3) on every hand, fold hands included."""
from lab.eval import opponent_spec, parse_brain
from lab.harness import load_variant
from lab.opps import record


def test_opp_hole3_on_every_hand_round_trip(tmp_path) -> None:
    cfg = load_variant("discard_holdem")
    pair = record.record_pair(parse_brain("tier3", "off"), opponent_spec("tight", "off"),
                              cfg, seed=9000, hands=30)
    data = {"opponent": "tight", "pairs": [pair]}
    path = tmp_path / "x.json.gz"
    record.save(path, data)
    hands = list(record.iter_hands(record.load(path)))
    assert len(hands) == 60
    folds = 0
    for h in hands:
        assert len(h["opp_hole3"]) == 3 and len(set(h["opp_hole3"])) == 3
        assert not set(h["opp_hole3"]) & set(h["hole3"])          # distinct from our cards
        assert len(h["opp_dis"]) <= 1 and set(h["opp_dis"]) <= set(h["opp_hole3"])
        if h["opp"]:                                               # showdown cards agree
            assert set(h["opp"]) <= set(h["opp_hole3"])
        folds += not h["opp"]
    assert folds > 0                                               # fold hands carry it too
    assert any(h["opp_dis"] for h in hands)
    # old fields unchanged
    assert {"id", "seat", "hole3", "hole", "board", "opp", "delta", "h", "rv"} <= set(hands[0])

"""Universal fuzz: every catalog variant and many random variants, played by sparring bots
and Tier 2. Checks: no exceptions, chip conservation every hand, every action legal, no
information leaks (event audit), determinism, and duplicate seat swapping.

Catalog variants whose plugins don't exist yet are xfail with the phase that adds them;
EXPECTED_UNSUPPORTED must be updated as plugins land (a test enforces it).
"""
import pytest

from bot.game.compile import NotSupported, compile_spec
from bot.protocol import HandStart, HoleCards, Info
from lab.engine import play_match
from lab.players import PlayerSpec
from lab.random_variant import random_supported_spec
from variant.spec import load_catalog

CATALOG = load_catalog()
FAST = {"max_samples": 64}
BOTS = ["random_legal", "all_in", "calling_station", "tight", "maniac"]

# variant -> phase whose plugin it still needs
EXPECTED_UNSUPPORTED = {
    "short_bounty_rit": 15, "boards_discard_pl": 15,
    "auction_card": 15, "bounty_rank": 15, "side_market": 15, "three_boards": 15,
    "run_it_twice": 15,
}


def tier2():
    return PlayerSpec.brain("tier2", FAST).build()


def check_variant(spec, hands: int, seed: int) -> None:
    rules = compile_spec(spec)
    # Tier 2 against every sparring bot, and the sparring bots against each other.
    pairings = [(tier2, lambda b=b: PlayerSpec.brain(b).build()) for b in BOTS]
    pairings.append((lambda: PlayerSpec.brain("maniac").build(),
                     lambda: PlayerSpec.brain("tight").build()))
    for i, (make_a, make_b) in enumerate(pairings):
        m = play_match([make_a(), make_b()], rules, seed=seed + i, hands=hands, audit=True)
        assert m.errors == [0, 0], (spec.name, i, m.errors)
        assert m.forfeit is None, (spec.name, m.forfeit_reason)
        assert m.chips[0] + m.chips[1] == 0
    # Determinism: the same seed replays identically.
    runs = [play_match([PlayerSpec.brain("random_legal").build(),
                        PlayerSpec.brain("maniac").build()], rules, seed=seed,
                       hands=min(hands, 40)).hand_deltas for _ in range(2)]
    assert runs[0] == runs[1]
    check_duplicate_swap(rules, seed)


class Recorder:
    """Wraps a player and records the first cards dealt to it in each hand: its hole
    cards, or the cards it is offered when the variant deals by choice."""

    def __init__(self, inner) -> None:
        self.inner, self.holes, self._got_hole = inner, [], True

    def set_rules(self, rules) -> None:
        getattr(self.inner, "set_rules", lambda r: None)(rules)

    def notify(self, msg) -> None:
        if isinstance(msg, HandStart):
            self._got_hole = False
        elif not self._got_hole and (isinstance(msg, HoleCards) or
                                     (isinstance(msg, Info) and msg.kind == "offer")):
            self.holes.append(msg.cards)
            self._got_hole = True
        self.inner.notify(msg)

    def act(self, req):
        return self.inner.act(req)

    def close(self) -> None:
        self.inner.close()


def check_duplicate_swap(rules, seed: int, hands: int = 12) -> None:
    """Each seat gets the same initial cards across a duplicate pair."""
    a1, b1 = Recorder(PlayerSpec.brain("calling_station").build()), Recorder(tier2())
    play_match([a1, b1], rules, seed=seed, hands=hands)
    b2, a2 = Recorder(tier2()), Recorder(PlayerSpec.brain("calling_station").build())
    play_match([b2, a2], rules, seed=seed, hands=hands)
    n = min(len(a1.holes), len(b2.holes), len(b1.holes), len(a2.holes))
    assert n > 0
    assert a1.holes[:n] == b2.holes[:n] and b1.holes[:n] == a2.holes[:n]


# --------------------------------------------------------------------------- catalog

def test_catalog_is_big_enough() -> None:
    assert len(CATALOG) >= 25
    for name, spec in CATALOG.items():
        assert spec.validate() == [], name
        assert spec.description, name


def test_unsupported_list_is_current() -> None:
    """Forces EXPECTED_UNSUPPORTED to be updated when a plugin lands."""
    actual = {}
    for name, spec in CATALOG.items():
        try:
            compile_spec(spec)
        except NotSupported as e:
            actual[name] = e.phase
    assert actual == EXPECTED_UNSUPPORTED


def _catalog_case(name: str, hands: int) -> None:
    if name in EXPECTED_UNSUPPORTED:
        pytest.xfail(f"needs phase {EXPECTED_UNSUPPORTED[name]}")
    check_variant(CATALOG[name], hands, seed=7)


@pytest.mark.parametrize("name", sorted(CATALOG))
def test_catalog_quick(name: str) -> None:
    _catalog_case(name, hands=40)


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(CATALOG))
def test_catalog_full(name: str) -> None:
    _catalog_case(name, hands=500)


# --------------------------------------------------------------------------- random variants

@pytest.mark.parametrize("seed", range(8))
def test_random_variants_quick(seed: int) -> None:
    check_variant(random_supported_spec(seed), hands=30, seed=seed)


@pytest.mark.slow
@pytest.mark.parametrize("seed", range(200))
def test_random_variants_full(seed: int) -> None:
    check_variant(random_supported_spec(1000 + seed), hands=500, seed=seed)

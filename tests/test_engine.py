"""Rules engine tests: legality, chip conservation, all-ins, showdown, hooks, players."""
import random
import sys


from bot.actions import Action, LegalActions
from bot.brains.base import Brain
from bot.cards import parse_cards as P
from bot.protocol import ActRequest, BoardUpdate, HoleCards, OppAction, Showdown
from lab.engine import BB, SB, Hand, Seat, deck_for, play_match
from lab.players import InProcessPlayer, SubprocessPlayer
from lab.example_variants import EXAMPLES
from variant.spec import BettingSpec, MatchSpec, VariantSpec

CFG = VariantSpec()                       # plain Hold'em


class ScriptPlayer:
    """Replies from a fixed list (then check/fold); records everything it receives."""

    def __init__(self, replies=()) -> None:
        self.replies = list(replies)
        self.seen: list = []
        self.requests: list[ActRequest] = []

    def notify(self, msg) -> None:
        self.seen.append(msg)

    def act(self, req):
        self.seen.append(req)
        self.requests.append(req)
        if self.replies:
            return self.replies.pop(0)
        return "K" if req.legal.check else ("S 0" if req.legal.special else "F")

    def close(self) -> None:
        pass


class RandomBrain(Brain):
    def __init__(self, seed: int = 0) -> None:
        self.rng = random.Random(seed)

    def decide(self, state, legal, budget_s):
        opts = []
        if legal.fold:
            opts.append(Action.fold())
        if legal.check:
            opts.append(Action.check())
        if legal.call:
            opts += [Action.call()] * 2
        if legal.can_raise:
            opts.append(Action.raise_to(self.rng.randint(legal.raise_min, legal.raise_max)))
        if legal.can_special:
            opts.append(Action.special(self.rng.choice(legal.special.choices)))
        return self.rng.choice(opts)


def make_deck(sb: str, bb: str, board: str) -> list[int]:
    head = list(P(sb)) + list(P(bb)) + list(P(board))
    return head + [c for c in range(52) if c not in head]


def play_hand(sb_replies, bb_replies, deck=None, cfg=CFG, stacks=(400, 400)):
    p = [ScriptPlayer(sb_replies), ScriptPlayer(bb_replies)]
    hand = Hand(cfg, [Seat(p[0], 60), Seat(p[1], 60)], list(stacks),
                deck or deck_for(0, 0), 0)
    return hand, hand.play(), p


# --------------------------------------------------------------------------- legality

def test_preflop_legal_actions_and_min_raise() -> None:
    _, res, (sb, bb) = play_hand(["R 6", "F"], ["R 10"])
    assert sb.requests[0].legal == LegalActions(fold=True, call=True, raise_min=4, raise_max=400)
    assert (sb.requests[0].pot, sb.requests[0].tocall) == (3, 1)
    # BB facing a raise to 6 (raise size 4): min re-raise is to 10.
    assert bb.requests[0].legal == LegalActions(fold=True, call=True, raise_min=10, raise_max=400)
    assert sb.requests[1].legal.raise_min == 14
    assert res.deltas == [-6, 6] and res.folded == SB


def test_bb_option_after_limp() -> None:
    _, _, (sb, bb) = play_hand(["C"], ["K"] * 4)
    assert bb.requests[0].legal == LegalActions(check=True, raise_min=4, raise_max=400)
    assert bb.requests[0].mybet == 2 and bb.requests[0].oppbet == 2


def test_postflop_bb_acts_first_and_min_bet_is_bb() -> None:
    _, _, (sb, bb) = play_hand(["C", "K", "K", "K"], ["K", "K", "K", "K"])
    flop_req = bb.requests[1]
    assert flop_req.legal == LegalActions(check=True, raise_min=2, raise_max=398)
    assert flop_req.mybet == 0 and flop_req.pot == 4


def test_all_in_for_less_than_min_raise() -> None:
    # SB has only 5 chips: after BB raises to 4... use a raise that leaves SB short.
    _, res, (sb, bb) = play_hand(["C"], ["R 4"], stacks=(5, 400))
    legal = sb.requests[1].legal
    assert legal.raise_min == legal.raise_max == 5      # all-in for less is still offered
    assert sum(res.deltas) == 0


def test_short_all_in_is_refunded() -> None:
    # SB shoves 50, BB (stack 30) calls all-in for less: 20 is refunded to SB.
    deck = make_deck("Ah,Ad", "Kh,Kd", "2c,7s,9d,Jc,3h")
    hand, res, _ = play_hand(["R 50"], ["C"], deck, stacks=(400, 30))
    assert res.showdown and res.deltas == [30, -30]
    assert hand.stack == [430, 0]


def test_raise_cap() -> None:
    cfg = VariantSpec(betting=BettingSpec(max_raises=1))
    _, _, (sb, bb) = play_hand(["R 6"], ["C"], cfg=cfg)
    assert not bb.requests[0].legal.can_raise


def test_split_pot_and_showdown_messages() -> None:
    deck = make_deck("2c,3d", "4c,5d", "Ah,Kh,Qh,Jh,Th")   # royal flush on board
    _, res, (sb, bb) = play_hand(["C"] + ["K"] * 3, ["K"] * 4, deck)
    assert res.showdown and res.deltas == [0, 0]
    assert Showdown(P("4c,5d")) in sb.seen and Showdown(P("2c,3d")) in bb.seen


def test_showdown_winner() -> None:
    deck = make_deck("Ah,Ad", "Kh,Kd", "2c,7s,9d,Jc,3h")
    _, res, _ = play_hand(["R 100"] + ["K"] * 3, ["C"] + ["K"] * 3, deck)
    assert res.deltas == [100, -100]


def test_all_in_runs_out_board_without_betting() -> None:
    deck = make_deck("Ah,Ad", "Kh,Kd", "2c,7s,9d,Jc,3h")
    _, res, (sb, bb) = play_hand(["R 400"], ["C"], deck)
    assert len(sb.requests) == 1 and len(bb.requests) == 1
    assert res.deltas == [400, -400]
    assert sum(isinstance(m, BoardUpdate) for m in sb.seen) == 3


def test_illegal_replies_auto_check_fold() -> None:
    p = [ScriptPlayer(["garbage", "R 99999"]), ScriptPlayer(["K"] * 4)]
    m = play_match(p, CFG, seed=1, hands=1)
    assert m.errors[0] == 1    # "garbage" -> fold; (hand over so R 99999 never asked)
    assert m.forfeit is None


def test_illegal_reply_forfeit_mode() -> None:
    p = [ScriptPlayer(["nonsense"]), ScriptPlayer()]
    m = play_match(p, CFG, seed=1, hands=5, on_illegal="forfeit")
    assert m.forfeit == 0 and m.score(0) == 0.0 and m.score(1) == 1.0


# --------------------------------------------------------------------------- random play

def test_chip_conservation_random_play() -> None:
    for seed in range(300):
        rng = random.Random(seed)
        stacks = [rng.randint(1, 400), rng.randint(1, 400)]
        players = [InProcessPlayer(RandomBrain(seed)), InProcessPlayer(RandomBrain(seed + 1))]
        hand = Hand(CFG, [Seat(players[0], 60), Seat(players[1], 60)], stacks,
                    deck_for(seed, 0), 0)
        res = hand.play()
        assert sum(res.deltas) == 0
        assert sum(hand.stack) == sum(stacks) and min(hand.stack) >= 0
        assert players[0].bot.state.bankroll == res.deltas[0]
        assert players[1].bot.state.bankroll == res.deltas[1]


def test_bots_never_send_illegal_actions() -> None:
    m = play_match([InProcessPlayer(RandomBrain(1)), InProcessPlayer(RandomBrain(2))],
                   CFG, seed=5, hands=300)
    assert m.errors == [0, 0] and m.hands_played == 300
    assert sum(m.hand_deltas) == m.chips[0] == -m.chips[1]


def test_deterministic_per_seed() -> None:
    def run():
        return play_match([InProcessPlayer(RandomBrain(1)), InProcessPlayer(RandomBrain(2))],
                          CFG, seed=11, hands=50).hand_deltas
    assert run() == run()


def test_duplicate_seat_swap_gets_same_cards() -> None:
    a1, b1 = ScriptPlayer(), ScriptPlayer()
    play_match([a1, b1], CFG, seed=4, hands=6)
    b2, a2 = ScriptPlayer(), ScriptPlayer()
    play_match([b2, a2], CFG, seed=4, hands=6)
    hole = lambda p: [m.cards for m in p.seen if isinstance(m, HoleCards)]
    assert hole(a1) == hole(b2) and hole(b1) == hole(a2)
    assert hole(a1) != hole(b1)


def test_persistent_stacks_end_on_bust() -> None:
    cfg = VariantSpec(match=MatchSpec(reset_stacks=False, starting_stack=20))

    class Shover(ScriptPlayer):
        def act(self, req):
            super().act(req)
            return f"R {req.legal.raise_max}" if req.legal.can_raise else "C"

    m = play_match([Shover(), Shover()], cfg, seed=2, hands=100)
    assert m.hands_played < 100 and sorted(m.chips) == [-20, 20]


# --------------------------------------------------------------------------- special step

# The example lives in lab/example_variants.py (shared with the fuzzer):
# after the flop each player discards 1 of 3 hole cards face up onto the board, BB first.
DISCARD_CFG = EXAMPLES["discard3"]


def test_discard_example() -> None:
    hand, res, (sb, bb) = play_hand(["C", "S 2"] + ["K"] * 3, ["K", "S 0"] + ["K"] * 3,
                                    deck=deck_for(3, 0), cfg=DISCARD_CFG)
    assert len(hand.hole[SB]) == 2 and len(hand.hole[BB]) == 2
    assert len(hand.board) == 3 + 2 + 1 + 1                 # flop + 2 discards + turn + river
    # BB was asked first, with the special legal set; SB saw BB's choice.
    assert bb.requests[1].legal.special.choices == ("0", "1", "2")
    assert OppAction(Action.special("0")) in sb.seen
    # Both see the board with the discards on it; each gets its updated hole cards.
    assert any(isinstance(m, BoardUpdate) and len(m.cards) == 5 for m in sb.seen)
    assert any(isinstance(m, HoleCards) and len(m.cards) == 2 for m in bb.seen)
    # No card duplicated or lost.
    cards = hand.hole[SB] + hand.hole[BB] + hand.board + hand.deck
    assert sorted(cards) == list(range(52))
    assert sum(res.deltas) == 0


def test_discard_with_real_bot_brains() -> None:
    m = play_match([InProcessPlayer(RandomBrain(3)), InProcessPlayer(RandomBrain(4))],
                   DISCARD_CFG, seed=9, hands=200)
    assert m.errors == [0, 0] and m.hands_played == 200


# --------------------------------------------------------------------------- subprocess players

def test_subprocess_bot_plays_a_match() -> None:
    m = play_match([SubprocessPlayer(), InProcessPlayer(RandomBrain(5))], CFG, seed=0, hands=30)
    assert m.forfeit is None and m.errors[0] == 0 and m.hands_played == 30


def test_subprocess_timeout_forfeits() -> None:
    sleeper = SubprocessPlayer([sys.executable, "-c", "import time; time.sleep(30)"])
    m = play_match([sleeper, ScriptPlayer()], CFG, seed=0, hands=5, time_bank_s=0.3)
    assert m.forfeit == 0 and "time" in m.forfeit_reason


def test_subprocess_crash_forfeits() -> None:
    crasher = SubprocessPlayer([sys.executable, "-c", "import sys; sys.exit(1)"])
    m = play_match([ScriptPlayer(), crasher], CFG, seed=0, hands=5, time_bank_s=5)
    assert m.forfeit == 1 and "crash" in m.forfeit_reason

"""Adapters that seat the LLM-built opponent bots in Opps/ as lab brains (lab only).

Each adapter turns our neutral GameState / LegalActions into the bot's own API and its
answer back into an Action. The bots are third-party code, loaded unchanged from
Opps/<name>; nothing here is submitted.

  opp1  MIT-skeleton style (handle_new_round / get_action(game_state, round_state, active))
  opp2  dict API: on_hand_start / get_action(dict) / on_hand_end(summary dict)
  opp3  engine-independent core: pb.brain.Brain.act(Obs) / hand_over(HandResult)
  opp4  dict API like opp2, on_hand_end(hero_delta, opp_delta)

Play them on lab/opps/holdem_100bb.json: they were written for MIT rules (stacks 200,
blinds 1/2, stacks reset every hand), and opp1 hardcodes the 200-chip stack.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from bot.actions import Action, LegalActions, safe_action
from bot.brains.base import Brain
from bot.cards import format_card
from bot.protocol import HandEnd, HoleCards, Message
from bot.state import GameState

OPPS_DIR = Path(__file__).resolve().parents[2] / "Opps"
STREET_NAMES = {0: "preflop", 3: "flop", 4: "turn", 5: "river"}


def _load(folder: str, module: str, fresh: bool = True):
    """Import `module` from Opps/<folder>, as the bot's own top-level imports expect.

    opp2 and opp4 share module names (evaluator, strategy, ...), and opp1/opp3 both ship
    a `skeleton` package, so with `fresh` any module previously loaded from Opps/ is
    dropped first. Brains already built keep their own module objects."""
    root = OPPS_DIR / folder
    for name, mod in list(sys.modules.items()):
        f = getattr(mod, "__file__", None) or ""
        if fresh and f.startswith(str(OPPS_DIR)):
            del sys.modules[name]
    sys.path[:] = [p for p in sys.path if not p.startswith(str(OPPS_DIR))]
    sys.path.insert(0, str(root))
    if module.endswith(".py"):  # a file whose name clashes with ours (opp2/opp4 bot.py)
        spec = importlib.util.spec_from_file_location(f"{folder}_{module[:-3]}", root / module)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    return importlib.import_module(module)


def _strs(cards) -> list[str]:
    return [format_card(c) for c in cards]


def _mit_street(board) -> int:
    return len(board) if board else 0


class _OppBrain(Brain):
    """Common plumbing: start/end-of-hand hooks from engine messages, safe fallback."""

    def __init__(self, config: Optional[dict] = None) -> None:
        self.cfg = dict(config or {})

    def observe(self, state: GameState, msg: Message) -> None:
        h = state.hand
        if isinstance(msg, HoleCards) and h is not None:
            self.hand_start(state)
        elif isinstance(msg, HandEnd) and h is not None:
            self.hand_end(state)

    def hand_start(self, state: GameState) -> None: ...

    def hand_end(self, state: GameState) -> None: ...

    @staticmethod
    def hand_no(state: GameState) -> int:
        return state.hands_played + (0 if state.hand and state.hand.finished else 1)

    @staticmethod
    def from_kind(kind: str, amount, legal: LegalActions) -> Action:
        if kind == "raise" and legal.can_raise:
            return Action.raise_to(int(amount))
        if kind == "call" and legal.call:
            return Action.call()
        if kind == "check" and legal.check:
            return Action.check()
        if kind == "fold" and legal.fold:
            return Action.fold()
        return safe_action(legal)


# --------------------------------------------------------------------------- opp1
class _RoundState:
    """Duck-typed MIT RoundState as opp1 reads it (we are always player 0)."""

    def __init__(self, state: GameState, legal: LegalActions, acts) -> None:
        h = state.hand
        self.button = 0 if h.seat == 0 else 1     # opp1: is_button = (active == button)
        self.street = _mit_street(h.board)
        self.pips = (h.my_bet or 0, h.opp_bet or 0)
        self.stacks = (h.my_stack, h.opp_stack)
        self.hands = (_strs(h.hole), [])
        self.deck = _strs(h.board)
        self.previous_state = None
        self._legal, self._acts, self.pot = legal, acts, h.pot

    def legal_actions(self):
        a, out = self._acts, set()
        if self._legal.fold:
            out.add(a.FoldAction)
        if self._legal.check:
            out.add(a.CheckAction)
        if self._legal.call:
            out.add(a.CallAction)
        if self._legal.can_raise:
            out.add(a.RaiseAction)
        return out

    def raise_bounds(self):
        return (self._legal.raise_min or 0, self._legal.raise_max or 0)

    @property
    def pot_odds(self) -> float:
        c = self.pips[1] - self.pips[0]
        return c / (self.pot + c) if c > 0 else 0.0


class Opp1Brain(_OppBrain):
    name = "opp1"

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        player = _load("opp1", "player")
        self.acts = importlib.import_module("skeleton.actions")
        self.bot = player.TitanBot()

    def _gs(self, state: GameState):
        return SimpleNamespace(bankroll=state.bankroll, game_clock=state.timeleft or 60.0,
                               round_num=self.hand_no(state))

    def hand_start(self, state):
        self.bot.handle_new_round(self._gs(state), None, 0)

    def hand_end(self, state):
        self.bot.handle_round_over(self._gs(state), None, 0)

    def decide(self, state, legal, budget_s):
        a = self.bot.get_action(self._gs(state), _RoundState(state, legal, self.acts), 0)
        kind = type(a).__name__.replace("Action", "").lower()
        return self.from_kind(kind, getattr(a, "amount", 0), legal)


# --------------------------------------------------------------------------- opp2 / opp4
class _DictBrain(_OppBrain):
    folder = ""

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        self.bot = _load(self.folder, "bot.py").PokerBot()

    def hand_start(self, state):
        h = state.hand
        self.bot.on_hand_start(self.hand_no(state), _strs(h.hole), h.seat == 0,
                               h.my_stack, h.opp_stack)

    def decide(self, state, legal, budget_s):
        h = state.hand
        names = [k for k, ok in (("check", legal.check), ("call", legal.call),
                                 ("fold", legal.fold), ("raise", legal.can_raise)) if ok]
        gs = {"legal_actions": names, "min_raise": legal.raise_min or 0,
              "max_raise": legal.raise_max or 0, "pot": h.pot, "call_cost": h.tocall,
              "hero_stack": h.my_stack, "opp_stack": h.opp_stack,
              "time_bank": state.timeleft if state.timeleft is not None else 60.0,
              "street": STREET_NAMES.get(_mit_street(h.board), "river"),
              "board": _strs(h.board)}
        kind, amount = self.bot.get_action(gs)
        return self.from_kind(kind, amount, legal)


class Opp2Brain(_DictBrain):
    name = "opp2"
    folder = "opp2"

    def __init__(self, config: Optional[dict] = None) -> None:
        # opp2 as shipped cannot start: opponent_model.py imports TOTAL_COMBOS from
        # preflop, which doesn't define it (equity does). In a real match it would crash
        # at import and forfeit. Patch the one name so we can study its strategy.
        _load("opp2", "preflop").TOTAL_COMBOS = _load("opp2", "equity", fresh=False).TOTAL_COMBOS
        _OppBrain.__init__(self, config)
        self.bot = _load("opp2", "bot.py", fresh=False).PokerBot()

    def hand_end(self, state):
        h = state.hand
        summary = {"showdown": bool(h.opp_cards), "board": _strs(h.board)}
        if h.opp_cards:
            summary["opp_hole_cards"] = _strs(h.opp_cards)
        self.bot.on_hand_end(summary)


class Opp4Brain(_DictBrain):
    name = "opp4"
    folder = "opp4"

    def hand_end(self, state):
        d = state.hand.delta or 0
        self.bot.on_hand_end(d, -d, _strs(state.hand.opp_cards) or None)


# --------------------------------------------------------------------------- opp3
class Opp3Brain(_OppBrain):
    name = "opp3"

    def __init__(self, config: Optional[dict] = None) -> None:
        super().__init__(config)
        brain_mod = _load("opp3", "pb.brain")
        self.types = importlib.import_module("pb.types")
        self.parse = importlib.import_module("pb.cards").parse
        self.core = brain_mod.Brain(fold_out=bool(self.cfg.get("fold_out", True)))
        self.started = False
        self.last_kind = None

    def _cards(self, cards):
        return tuple(self.parse(s) for s in _strs(cards))

    def hand_start(self, state):
        if not self.started:  # same setup as opp3's own player.py
            m = state.match
            self.core.new_match(m.hands)
            bank = float(state.timeleft or m.timebank)
            self.core.clock.initial_bank = bank
            self.core.clock.reserve = max(1.5, 0.10 * bank)
            self.started = True
        self.last_kind = None
        self.core.new_hand(self.hand_no(state), self._cards(state.hand.hole), state.hand.seat == 0)

    def hand_end(self, state):
        h = state.hand
        opp = self._cards(h.opp_cards) if h.opp_cards else None
        self.core.hand_over(self.types.HandResult(
            delta=h.delta or 0, opp_hole=opp if opp and len(opp) == 2 else None,
            board=self._cards(h.board), hero_folded=self.last_kind == "fold"))

    def decide(self, state, legal, budget_s):
        h, m = state.hand, state.match
        n = self.hand_no(state)
        obs = self.types.Obs(
            hand_no=n, hole=self._cards(h.hole), board=self._cards(h.board),
            street={0: 0, 3: 1, 4: 2, 5: 3}.get(_mit_street(h.board), 0), button=h.seat == 0,
            pot=h.pot, hero_pip=h.my_bet or 0, opp_pip=h.opp_bet or 0,
            hero_stack=h.my_stack, opp_stack=h.opp_stack, to_call=h.tocall,
            min_raise=legal.raise_min or 0, max_raise=legal.raise_max or 0,
            can_check=legal.check, can_raise=legal.can_raise, can_call=legal.call,
            can_fold=legal.fold, time_left=state.timeleft, hands_left=max(1, m.hands - n + 1),
            bankroll=state.bankroll, big_blind=m.bb, small_blind=m.sb, start_stack=h.start_stack)
        act = self.core.act(obs)
        self.last_kind = act[0]
        return self.from_kind(act[0], act[1] if len(act) > 1 else 0, legal)

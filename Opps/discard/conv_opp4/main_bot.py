"""
bot.py - Discard Hold'em bot ("Titan"): protocol layer plus the decision flow of the original bot.

Style kept from the original: stack-stratified preflop charts, range-weighted Monte Carlo equity,
calling rule = pot odds + street margins + sampling error, candidate bet sizes (33 / 66 / 110 % pot
and all-in) chosen by expected value, river bluffs with blockers, Bayesian opponent stats
(fold to bet, fold to c-bet), a time governor with hard per-decision deadlines.

Discard Hold'em changes: 3 hole cards (preflop charts applied by frequency to the best 2-card
keep; equity = best keep), a discard decision after the flop (equity of each keep against the
opponent's range), and the opponent's revealed discard (out of play, narrows its range).
Opponent stats and range updates now come from the `history` of each request.

Run:  python3.11 bot.py        stdout = protocol messages only, debug goes to stderr.
"""

import json
import os
import random
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402

from equity import calculate_equity, calculate_keep_equities  # noqa: E402
from evaluator import card_from_str  # noqa: E402
from keep3 import keep_equity  # noqa: E402
from meta_controller import MatchUtilityModel, TimeGovernor  # noqa: E402
from opponent_model import OpponentModel  # noqa: E402
from safety import ActionSanitizer  # noqa: E402
from strategy import StrategyEngine  # noqa: E402

BOARD_LEN = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
RANK_ORDER = "23456789TJQKA"
SUIT_ORDER = "shdc"


class PokerBot:
    """Opponent 4 (Titan) decision engine for Discard Hold'em."""

    def __init__(self, total_hands: int = 400, time_budget: float = 58.0) -> None:
        self.total_hands = total_hands
        self.time_budget = time_budget
        self.model = OpponentModel()
        self.meta = MatchUtilityModel(total_hands=total_hands)
        self.governor = TimeGovernor(total_budget_sec=time_budget, total_hands=total_hands)
        self.strategy = StrategyEngine(self.model, self.meta)
        self.rng = np.random.default_rng(4)

        self.hand_num = 0
        self.hero_cards: List[int] = []
        self.dead: List[int] = []
        self.is_button = False
        self.hero_stack = 200
        self.opp_stack = 200
        self.cumulative_score_margin = 0.0
        self.time_bank = time_budget

        self.villain_weights = self.model.get_initial_villain_weights()
        self.we_were_preflop_aggressor = False
        self.seen = 0                       # history entries already processed this hand
        self.prev_entry: Optional[dict] = None

    # ------------------------------------------------------------------ hand lifecycle
    def on_hand_start(self, hand_id: int, hole_cards_str: Sequence[str], is_button: bool,
                      hero_stack: int = 200, opp_stack: int = 200) -> None:
        try:
            self.hand_num = hand_id
            self.hero_cards = [card_from_str(c) for c in hole_cards_str]
            self.dead = []
            self.is_button = is_button
            self.hero_stack = hero_stack
            self.opp_stack = opp_stack
            self.villain_weights = self.model.get_initial_villain_weights()
            self.we_were_preflop_aggressor = False
            self.seen = 0
            self.prev_entry = None
        except Exception:
            self.hero_cards = [0, 4, 8]

    def on_hand_end(self, hero_delta: int, history: Optional[list] = None) -> None:
        try:
            if history:
                self.ingest(history, board=[], stats_only=True)      # the opponent's last response (e.g. a fold)
            self.cumulative_score_margin += float(hero_delta)
            self.model.hands_observed += 1
        except Exception:
            pass

    # ------------------------------------------------------------------ opponent observation
    def ingest(self, history: Sequence[dict], board: Sequence[int], stats_only: bool = False) -> None:
        """Process the history entries not seen yet: Bayesian stats and range weights."""
        cheap = stats_only or self.time_bank < 0.12 * self.time_budget   # low on time: stats only, no range updates
        for e in history[self.seen:]:
            self.seen += 1
            try:
                actor, act, street = e.get("actor"), e.get("action"), e.get("street", "preflop")
                prev = self.prev_entry
                if actor == "me":
                    if act == "raise" and street == "preflop":
                        self.we_were_preflop_aggressor = True
                elif actor == "opp":
                    facing = bool(prev and prev.get("actor") == "me" and prev.get("action") == "raise"
                                  and prev.get("street") == street)
                    cbet_spot = facing and street == "flop" and self.we_were_preflop_aggressor
                    self.model.observe_action(street, act, facing_bet=facing, is_cbet_opportunity=cbet_spot)
                    if not cheap and act in ("raise", "call", "check"):
                        b = list(board)[:BOARD_LEN.get(street, 0)] if street != "preflop" else []
                        if street == "preflop" and act == "check":
                            pass
                        else:
                            self.villain_weights = self.model.update_weights_for_action(
                                self.villain_weights, act, b, 0, 0, dead=self.dead)
                self.prev_entry = e
            except Exception:
                continue

    # ------------------------------------------------------------------ decisions
    def get_action(self, game_state: Dict[str, Any]) -> Tuple[str, int]:
        """Main decision method. Receives the request as a dict and returns (action, amount)."""
        legal = game_state.get("legal_actions", ["check", "fold"])
        min_raise = game_state.get("min_raise", 0)
        max_raise = game_state.get("max_raise", 0)
        pot = game_state.get("pot", 3)
        call_cost = game_state.get("call_cost", 0)
        hero_stack = game_state.get("hero_stack", self.hero_stack)
        opp_stack = game_state.get("opp_stack", self.opp_stack)
        time_bank = game_state.get("time_bank", 50.0)
        street = game_state.get("street", "preflop")
        board_str = game_state.get("board", [])
        history = game_state.get("history", [])
        self.time_bank = time_bank

        # Set monotonic clock deadline
        deadline = self.governor.get_action_deadline(time_bank, self.hand_num)

        try:
            board = [card_from_str(c) for c in board_str]
            self.ingest(history, board)

            # 1. PREFLOP
            if street == "preflop":
                act, amt = self.strategy.decide_preflop(
                    self.hero_cards,
                    self.is_button,
                    pot,
                    call_cost,
                    min_raise,
                    max_raise,
                    hero_stack,
                    opp_stack,
                    self.cumulative_score_margin,
                    self.hand_num,
                )
                return ActionSanitizer.sanitize(act, amt, legal, min_raise, max_raise)

            # 2. POSTFLOP: range-weighted equity with the specified samples
            equity, se = calculate_equity(
                self.hero_cards,
                board,
                self.villain_weights,
                street,
                deadline=deadline,
                rng=self.rng,
                dead=self.dead,
            )

            # Facing a bet or raise
            if call_cost > 0:
                should_call = self.strategy.decide_calling(
                    street,
                    equity,
                    se,
                    pot,
                    call_cost,
                    self.is_button,
                )

                if should_call:
                    # Monster hand re-raise (equity > 0.85)
                    if equity > 0.85 and "raise" in legal and max_raise >= min_raise:
                        raise_amt = min(max_raise, max(min_raise, call_cost * 2 + pot // 2))
                        return ActionSanitizer.sanitize("raise", raise_amt, legal, min_raise, max_raise)
                    return ActionSanitizer.sanitize("call", 0, legal, min_raise, max_raise)
                else:
                    return ActionSanitizer.sanitize("fold", 0, legal, min_raise, max_raise)

            # Uncontested (facing check)
            else:
                is_cbet = (street == "flop" and self.we_were_preflop_aggressor)
                best_act, best_amt, best_util = self.strategy.evaluate_bet_candidates(
                    street,
                    equity,
                    pot,
                    hero_stack,
                    min_raise,
                    max_raise,
                    self.cumulative_score_margin,
                    self.hand_num,
                    is_cbet=is_cbet,
                )

                # Check if river bluff applies on check
                if street == "river" and best_act == "check" and equity < 0.35:
                    bluff_size = max(min_raise, int(round(0.66 * pot)))
                    if min_raise <= bluff_size <= max_raise and "raise" in legal:
                        if self.strategy.should_river_bluff(self.hero_cards, board, bluff_size, pot):
                            return ActionSanitizer.sanitize("raise", bluff_size, legal, min_raise, max_raise)

                return ActionSanitizer.sanitize(best_act, best_amt, legal, min_raise, max_raise)

        except Exception as e:
            log("action error", repr(e))
            # Emergency crash-proof fallback
            if "check" in legal:
                return ("check", 0)
            if "call" in legal and call_cost <= 2:
                return ("call", 0)
            return ("fold", 0)

    def choose_discard(self, hole: Sequence[int], flop: Sequence[int], time_bank: float,
                       history: Sequence[dict]) -> int:
        """Index of the hole card to throw away: keep the 2 cards with the best equity against
        the opponent's range on this flop (same samples for all three keeps)."""
        self.time_bank = time_bank
        deadline = self.governor.get_action_deadline(time_bank, self.hand_num)
        try:
            self.ingest(history, flop)
            options, eqs, n = calculate_keep_equities(
                hole, flop, self.villain_weights, "flop", deadline=deadline, rng=self.rng)
            if n > 0:
                kept = options[max(range(len(options)), key=lambda i: eqs[i])]
                return [i for i, c in enumerate(hole) if c not in kept][0]
        except Exception as e:
            log("discard error", repr(e))
        return self.discard_heuristic(hole, flop)

    @staticmethod
    def discard_heuristic(hole: Sequence[int], flop: Sequence[int]) -> int:
        """No simulation: keep the pair with the best preflop equity, plus a bonus for each card
        that pairs the flop."""
        ranks = {c >> 2 for c in flop}
        best_i, best_v = 0, -1.0
        for i in range(len(hole)):
            keep = [c for j, c in enumerate(hole) if j != i]
            v = keep_equity(keep[0], keep[1]) + 0.15 * sum(1 for c in keep if (c >> 2) in ranks)
            if v > best_v:
                best_i, best_v = i, v
        return best_i

    def on_discard_result(self, my_discard: int, opp_discard: int, hole: Sequence[int],
                          flop: Sequence[int]) -> None:
        try:
            self.hero_cards = list(hole)
            self.dead = [my_discard, opp_discard]
            self.villain_weights = self.model.apply_discard(
                self.villain_weights, flop, opp_discard, self.dead)
        except Exception as e:
            log("discard_result error", repr(e))


# ---------------------------------------------------------------------- protocol layer

def log(*a) -> None:
    try:
        print(*a, file=sys.stderr, flush=True)
    except Exception:
        pass


def send(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


class Runner:
    def __init__(self) -> None:
        self.bot = PokerBot()
        self.total_hands = 400
        self.flop: List[int] = []
        self.hole_strs: List[str] = []
        self.last_history: list = []

    def on_init(self, m: dict) -> None:
        self.total_hands = int(m.get("total_hands", 400))
        bank = float(m.get("time_bank_ms", 60000)) / 1000.0
        self.bot = PokerBot(total_hands=self.total_hands, time_budget=bank * 0.97)

    def on_new_hand(self, m: dict) -> None:
        self.hole_strs = list(m.get("hole_cards", []))
        self.flop = []
        self.last_history = []
        self.bot.on_hand_start(int(m.get("hand_id", 0)), self.hole_strs, m.get("seat") == "button",
                               int(m.get("stack", 200)), int(m.get("opp_stack", 200)))

    def on_action_request(self, m: dict) -> dict:
        legal = m.get("legal_actions", ["check", "fold"])
        try:
            gs = {
                "legal_actions": legal,
                "min_raise": int(m.get("min_raise", 0)) if "raise" in legal else 0,
                "max_raise": int(m.get("max_raise", 0)) if "raise" in legal else 0,
                "pot": int(m["pot"]),
                "call_cost": int(m.get("to_call", 0)),
                "hero_stack": int(m.get("my_stack", 200)),
                "opp_stack": int(m.get("opp_stack", 200)),
                "time_bank": float(m.get("time_left_ms", 60000)) / 1000.0,
                "street": m.get("street", "preflop"),
                "board": m.get("board", []),
                "history": m.get("history", []),
            }
            if len(gs["board"]) >= 3 and not self.flop:
                self.flop = [card_from_str(c) for c in gs["board"][:3]]
            act, amt = self.bot.get_action(gs)
            if act == "raise":
                return {"type": "action", "action": "raise", "amount": int(amt)}
            return {"type": "action", "action": act}
        except Exception as e:
            log("request error", repr(e))
            if "check" in legal:
                return {"type": "action", "action": "check"}
            if "call" in legal and int(m.get("to_call", 0)) <= 2:
                return {"type": "action", "action": "call"}
            return {"type": "action", "action": "fold"}

    def on_discard_request(self, m: dict) -> dict:
        hole_strs = list(m.get("hole_cards", self.hole_strs))
        try:
            hole = [card_from_str(c) for c in hole_strs]
            self.flop = [card_from_str(c) for c in m.get("board", [])]
            idx = self.bot.choose_discard(hole, self.flop,
                                          float(m.get("time_left_ms", 60000)) / 1000.0,
                                          self.last_history)
            return {"type": "discard", "card": hole_strs[int(idx)]}
        except Exception as e:
            log("discard request error", repr(e))
        low = min(hole_strs, key=lambda c: (RANK_ORDER.index(c[0]), SUIT_ORDER.index(c[1])))
        return {"type": "discard", "card": low}

    def on_discard_result(self, m: dict) -> None:
        mine, theirs = m.get("my_discard"), m.get("opp_discard")
        hole = [card_from_str(c) for c in m.get("hole_cards", [])]
        if mine and theirs and len(hole) == 2:
            self.bot.on_discard_result(card_from_str(mine), card_from_str(theirs), hole, self.flop)

    def on_hand_result(self, m: dict) -> None:
        self.bot.on_hand_end(int(m.get("net", 0)), m.get("history") or [])

    def handle(self, line: str) -> Optional[dict]:
        """One protocol line in; the reply (action or discard) out, or None. Never raises."""
        line = line.strip()
        if not line:
            return None
        try:
            m = json.loads(line)
        except ValueError:
            return None
        if not isinstance(m, dict):
            return None
        t = m.get("type")
        try:
            if t == "init":
                self.on_init(m)
            elif t == "new_hand":
                self.on_new_hand(m)
            elif t == "action_request":
                self.last_history = m.get("history", [])
                return self.on_action_request(m)
            elif t == "discard_request":
                return self.on_discard_request(m)
            elif t == "discard_result":
                self.on_discard_result(m)
            elif t == "hand_result":
                self.on_hand_result(m)
            elif t == "notice":
                log("notice", m.get("code"), m.get("applied"))
            elif t == "match_end":
                self.over = True
        except Exception as e:  # never let anything escape
            log("handler error", t, repr(e))
            if t == "action_request":
                return {"type": "action", "action": "check" if "check" in m.get("legal_actions", []) else "fold"}
            if t == "discard_request":
                return self.on_discard_request(m)
        return None

    over = False

    def run(self) -> None:
        for line in sys.stdin:
            reply = self.handle(line)
            if reply is not None:
                send(reply)
            if self.over:
                break


if __name__ == "__main__":
    try:
        Runner().run()
    except Exception as e:
        log("fatal", repr(e))

"""The step interface. Every step type (plugin) subclasses `Step`.

Lifecycle, driven by bot/game/runner.py:
    begin(state)                     once, when the program reaches the step
    apply(state, rng)                automatic steps (decision = False): do the work
    next_actor(state) -> player|None decision steps: who must choose now (None = step done)
    legal(state, player)             decision steps: the legal options (a LegalActions)
    apply_choice(state, player, a)   decision steps: apply one (legal) choice
    end(state)                       once, when the step finishes

Information: a step reveals things ONLY through state.emit(kind, player, visible, ...).
`visible` is ALL or the single player allowed to see the event (see state.py).

Other hooks:
    default_policy(view, legal, rules, budget_s)  a generic bot decision for this step
    encode_choice(action) / decode_choice(text)    protocol tokens (None = standard F/K/C/R/S)
    describe()                                     one line of plain English
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from bot.actions import Action, LegalActions, safe_action


@dataclass
class CompileContext:
    """What a plugin may need to know while being built from a spec entry."""
    spec: Any                # the VariantSpec
    round_index: int = 0     # betting rounds compiled so far
    board_total: int = 0     # board cards per board over the whole program


class Step:
    type_name = "step"
    decision = False          # True if players make choices in this step
    skip_on_fold = True       # skipped once someone has folded (settlement steps say False)

    def __init__(self, **params: Any) -> None:
        self.params = params

    @classmethod
    def from_spec(cls, s: dict, ctx: CompileContext) -> "Step":
        """Build the step from its program entry `s` (defaults already filled in).
        Default: pass every parameter except "type" to the constructor."""
        return cls(**{k: v for k, v in s.items() if k != "type"})

    # ---- lifecycle
    def begin(self, st) -> None:
        pass

    def apply(self, st, rng) -> None:
        pass

    def next_actor(self, st) -> Optional[int]:
        return None

    def legal(self, st, p: int) -> LegalActions:
        return LegalActions()

    def apply_choice(self, st, p: int, action: Action) -> None:
        raise NotImplementedError

    def end(self, st) -> None:
        pass

    # ---- bot / protocol / docs
    def default_policy(self, view, legal: LegalActions, rules, budget_s: float) -> Action:
        return safe_action(legal)

    def encode_choice(self, action: Action) -> Optional[str]:
        return None

    def decode_choice(self, text: str) -> Optional[Action]:
        return None

    def describe(self) -> str:
        args = ", ".join(f"{k}={v}" for k, v in self.params.items())
        return f"{self.type_name}({args})"

    def __repr__(self) -> str:
        return self.describe()

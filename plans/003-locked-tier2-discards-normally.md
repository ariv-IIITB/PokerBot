# Plan 003: A locked Tier 2 still discards its worst card, not whichever card is first

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 39ca8f8..HEAD -- bot/brains/tier2.py tests/test_tier2.py bot/actions.py bot/situation.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `39ca8f8`, 2026-10-31

## Why this matters

The game is **Discard Hold'em**: each player holds 3 hole cards and discards one on the flop.
Tier 2 (the shipped brain) has an **endgame lock**. Once its lead covers the worst case of the
remaining hands, it check/folds everything so the match cannot be lost (`GLOSSARY.md`: "Endgame
lock: check/fold everything once the lead covers the worst case of the remaining hands").
But when locked it also answers the *discard* request with Tier 0's generic choice, the first
listed option `"0"`, which discards whatever card sits in slot 0. With `Ah Ad 2c` that throws
away an ace. A discard puts no chips in, so it is not something the lock needs to block. Locked
hands that check down to showdown lose chips they would have won. Chips count in the
tie-break (capped chips per hand) between bots on equal match points. The fix: when locked, play
the discard with the normal discard policy.

## Current state

- `bot/brains/tier2.py:151-160`, the decision entry point:
  ```python
      def decide(self, state: GameState, legal: LegalActions, budget_s: float) -> Action:
          s = self.situation(state)
          if s.locked():
              self.locked_decisions += 1
              return safe_action(legal)
          h = s.hand
          action = self.play(s, legal, budget_s, self.adjusted(h.street if h is not None else 0))
          if action.kind == RAISE and h is not None:  # the opponent's next action answers this bet
              self.opponent.spots.note_raise(h.street, raise_fraction(action, h))
          return action
  ```
- `bot/actions.py:142-155`, `safe_action`. For a discard-only request (no check or fold legal)
  it returns `Action.special(legal.special.default())`, and `SpecialOption.default()`
  (`bot/actions.py:70-72`) returns `self.choices[0]`, i.e. `"0"`, the first hole card.
- `bot/situation.py:88-101`, `Situation.special(legal, budget_s)`: the normal discard policy
  (a simulation, "PIMC"). On any failure it falls back to
  `safe_action_for_hole(legal, hole)`, which discards the rules' fallback card: the lowest rank
  (`bot/game/steps/cards.py:40-59`). This is what an unlocked Tier 2 uses, through
  `Tier1Brain.play` (`bot/brains/tier1.py:99-102`: `if legal.can_special: return s.special(legal, budget_s)`).
- Measured at `39ca8f8` with the test below: locked, hole `Ah,Ad,2c`, flop `Kh,Ks,7d` →
  `Action(kind='S', choice='0')`, which discards the `Ah`. Unlocked, the same spot →
  `choice='2'` (the `2c`).
- Test conventions: `tests/test_tier2.py`, section `# --- lock on discard_holdem` (around
  lines 166-235). It uses the helper `lock_state(hands, played, bankroll, seat, committed)`
  (line 110) and `DH_RULES = to_rules(load_catalog()["discard_holdem"])`. The exemplar to copy is
  `test_the_lock_lifts_as_soon_as_the_lead_is_gone`, which shows `lock_state(10, 8, 60, 0, 1)`
  being locked: hand 8 of 10, lead 60.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| The new test | `.venv/bin/python -m pytest -q tests/test_tier2.py -k locked_discard` | `1 passed` (after the fix) |
| Tier 2 tests | `.venv/bin/python -m pytest -q tests/test_tier2.py` | 0 failed |
| Fast suite | `.venv/bin/python -m pytest -n auto -q` | 0 failed |
| Time bank check (required after any `bot/` change, per `CLAUDE.md`) | `.venv/bin/python -m lab.timing_bench --variant discard_holdem --hands 1000` | a line `... projected x2 = ...s (P% of bank)` with P ≤ 50 |
| Memory check | `.venv/bin/python -m lab.memory_check --variant discard_holdem` | exit 0, RSS well under 1024 MB |

If `.venv/` is missing: `uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt`.

## Scope

**In scope**:
- `bot/brains/tier2.py`: the `decide` method only.
- `tests/test_tier2.py`: add one test in the lock section.

**Out of scope** (do NOT touch):
- `bot/actions.py` (`safe_action`, `SpecialOption.default`). Other callers rely on the generic
  Tier 0 behaviour; changing it there would change the lab engine and every fallback.
- `bot/situation.py`, `lock_margin`, the lock's betting behaviour. Betting stays check/fold.
- `bot/config/*.json`, `bot/embedded.py`. No parameter changes.
- `lab/harness.py`, `lab/engine.py`, `lab/eval.py` and the opponent bots: the owner forbids edits there.

## Git workflow

- Work on the branch you were given; if none, create `advisor/003-locked-discard`.
- One commit, e.g. `tier2: a locked hand still discards with the normal policy (it was discarding slot 0)`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Write the failing test

Add this test to `tests/test_tier2.py`, directly after
`test_the_lock_lifts_as_soon_as_the_lead_is_gone`. `BoardUpdate` and `SpecialOption` may need
imports: `BoardUpdate` is already imported from `bot.protocol` at the top of the file; add
`SpecialOption` to the `from bot.actions import ...` line at the top.

```python
def test_a_locked_hand_still_discards_its_worst_card() -> None:
    """The lock stops betting, not discarding: a discard puts no chips in, so a locked hand
    plays it normally instead of throwing away whatever card is listed first (an ace here)."""
    brain = Tier2Brain(game=DH_RULES)
    st = lock_state(10, 8, 60, 0, 1)                      # locked: see the test above
    st.apply(HoleCards(P("Ah,Ad,2c")))
    st.apply(BoardUpdate(1, P("Kh,Ks,7d")))
    discard = LegalActions(special=SpecialOption("discard", ("0", "1", "2")))
    assert brain.decide(st, discard, 0.05) == Action.special("2")    # the 2c, keeping the aces
    assert brain.locked_decisions == 1
```

The expected `"2"` comes from the game, not from the code: keeping `Ah Ad` on a `Kh Ks 7d` flop
(aces and kings) dominates either `A 2` hand, and `2c` is also the rules' fallback (the lowest card).

**Verify**: `.venv/bin/python -m pytest -q tests/test_tier2.py -k locked_discard` → `1 failed`,
and the failure shows `choice='0'` on the left of the `==`. A stderr warning
`reconstruction failed` may appear; that is expected for this hand-built state.

### Step 2: Apply the fix

In `bot/brains/tier2.py`, `decide`, change the locked branch to:

```python
        if s.locked():
            self.locked_decisions += 1
            if legal.can_special:           # a discard puts no chips in: play it normally
                return s.special(legal, budget_s)
            return safe_action(legal)
```

Nothing else in the file changes.

**Verify**: `.venv/bin/python -m pytest -q tests/test_tier2.py -k locked_discard` → `1 passed`.

### Step 3: Full checks

1. `.venv/bin/python -m pytest -q tests/test_tier2.py` → 0 failed. This includes
   `test_a_locked_match_cannot_be_lost_on_discard_holdem`, which plays whole locked matches.
2. `.venv/bin/python -m pytest -n auto -q` → 0 failed.
3. The time bank check from the table → P ≤ 50.
4. The memory check from the table → exit 0.

**Verify**: all four as stated. Then commit.

## Test plan

- New: `test_a_locked_hand_still_discards_its_worst_card` in `tests/test_tier2.py` (Step 1). It
  goes red before the fix and green after.
- Existing regression net: `test_a_locked_match_cannot_be_lost_on_discard_holdem` (whole matches
  with the lock, vs `all_in` and `maniac`, 400 and 1000 hands) must stay green. It proves the
  change does not let a locked match be lost.

## Done criteria

- [ ] `.venv/bin/python -m pytest -q tests/test_tier2.py -k locked_discard` → `1 passed`
- [ ] `.venv/bin/python -m pytest -n auto -q` → 0 failed
- [ ] `lab.timing_bench` projected x2 ≤ 50 % of the bank; `lab.memory_check` exits 0
- [ ] `git diff 39ca8f8 --stat` (or vs your base) shows only `bot/brains/tier2.py` and `tests/test_tier2.py`
- [ ] `plans/README.md` row 003 updated

## STOP conditions

Stop and report back (do not improvise) if:

- `decide` in `bot/brains/tier2.py` does not match the excerpt (for example a Tier 3 brain now
  overrides it, or the lock moved elsewhere).
- Step 1's test passes *before* the fix (the bug is already gone), or fails for a reason other
  than `choice='0'` (for example `locked_decisions == 0`: the state is not locked).
- After the fix the test returns a choice other than `"2"`. Do not change the expected value;
  report what came back.
- `test_a_locked_match_cannot_be_lost_on_discard_holdem` fails after the fix.
- The time bank check exceeds 50 %.

## Maintenance notes

- Any future brain built on Tier 2 (the planned Tier 3) that has its own lock branch needs the
  same rule: the lock blocks chips, not discards.
- A reviewer should check that the lock still never bets or calls: only the `legal.can_special`
  branch changed.
- Not done here: `safe_action`'s generic special choice (`choices[0]`) is still used by Tier 0
  where no hole cards are known. That is by design (`bot/actions.py:142`); the bot's own
  fallbacks use the hole-aware `safe_action_for_hole`.

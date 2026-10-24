# Writing a step plugin

Use this when the variant has a mechanic no existing step covers (see the red flags in
`VARIANT_INTERVIEW.md`). Budget: 1–3 hours including tests. The worked example below,
`redraw_board`, was written by following exactly these steps.

## 0. Is it really new?

Check `variant/spec.py` → `STEP_PARAMS` first. Most "new" mechanics are an existing step with
parameters: discard (board / muck / opponent, public / private / later), draw, swap
(opponent / board / deck, optional / forced / random), choose, peek, expose, bounty, auction
(4 prizes, 3 payment rules), market, multiple boards, run it twice, antes, straddles,
fixed/pot limit, bet-size menus, blind schedules.

## 1. Write the rule in one sentence

> "Each player in turn (BB first) may pay `cost` chips to replace one board card with the next
> deck card; the old card is shown to both."

Decide: who acts and in what order, what each player sees, what it costs, where every card
goes. This sentence becomes the module docstring.

## 2. The plugin module — `bot/game/steps/<name>.py`

Start from `bot/game/steps/_template.py`. For a per-player choice, subclass `CardStep`
(`bot/game/steps/cards.py`): you then only write

```python
class RedrawBoard(CardStep):
    type_name = "redraw_board"
    def options(self, st, p): ...          # choice tokens for player p, () = skip p
    def perform(self, st, p, choice): ...   # move cards, emit events
    @classmethod
    def from_spec(cls, s, ctx): ...         # build from the spec entry
    def describe(self): ...                 # one line of plain English
```

and `CardStep` handles order (`BB_first` / `SB_first` / `simultaneous`), costs, and telling the
opponent the choice (`visibility="public"`) or only `"hidden"` (`"private"`).

Rules that keep the rest of the system correct:

- **Information only through `st.emit(kind, player, visible=..., cards=...)`.** `visible` is
  `ALL` or one player. Use kind `"hole"` (a player's own cards), `"board"`, or a reveal kind
  (`"reveal"`, `"expose"`, `"peek"`) for cards shown to someone who doesn't own them. The
  state audit fails any event that shows a hidden card under another kind.
- **Cards only move**, between `st.deck`, `st.hole[p]`, `st.board` / `st.boards`, `st.muck`
  (and `st.extra["offers"]` while offered). Never create or drop a card.
- **Re-emit `"hole"`** to a player whenever their hole cards change, and `"board"` whenever the
  board changes (the bot's simulator rebuilds the hand from these).
- **Chips:** bets via `st.pay`, side costs via `st.pay_cost` (pot, not a bet), chips leaving the
  table go to `st.house`.
- **Simulations copy states**: anything you put in `st.step_state` or `st.extra` must be safe
  to copy (use `.copy()`-able objects or replace values instead of mutating them).
- **Choice tokens**: no spaces, commas, pipes or colons (`"none"`, `"b3"`, `"0+2"`), or a
  numeric range `SpecialOption(name, (), lo, hi)`. Every adapter then carries them unchanged.

## 3. Register it (three lines)

- `bot/game/steps/__init__.py` → `STEP_TYPES["redraw_board"] = "bot.game.steps.redraw:RedrawBoard"`
- `variant/spec.py` → `STEP_PARAMS["redraw_board"] = {"cost": 0, "order": "BB_first"}`
- `variant/spec.py` → `_check_cards`: count any cards it deals (`used += spec.players`)

## 4. A catalog preset and a fuzz entry

- `variant/catalog/redraw_board.json` — a preset using it (`tests/test_universal.py` then fuzzes
  it automatically: conservation, legality, leaks, determinism, duplicate seats).
- `lab/random_variant.py` → add it to `_card_step` (or `_side_step`) so random variants use it.

## 5. Default policy

Usually nothing to do: the generic layer (`bot/sim/policies.py`) evaluates every finite choice
with PIMC rollouts. Add a special case only if rollouts can't value it (information,
signalling) or there are too many options; the peek and expose policies are examples.

## 6. Tests — copy `tests/test_redraw.py`

It has one test per checklist item:

1. legality — who is asked, with which options, cost rule
2. effects + card conservation on a rigged deck
3. no leaks — random play with `audit=True` and the observation check
4. protocol — its tokens round-trip through every adapter
5. default policy — the generic layer makes the obvious choice in an obvious spot
6. full matches with real bots, in-process and over the wire

Then run everything: `.venv/bin/python -m pytest -n auto` and `-m slow`.

## Worked example: what was written for `redraw_board`

| File | Change |
|---|---|
| `bot/game/steps/redraw.py` | new: 44 lines (rule docstring, `options`, `perform`, `from_spec`, `describe`) |
| `bot/game/steps/__init__.py` | 1 line in `STEP_TYPES` |
| `variant/spec.py` | 1 line in `STEP_PARAMS`, 2 lines of card accounting |
| `variant/catalog/redraw_board.json` | new preset |
| `lab/random_variant.py` | 3 lines (fuzz entry) |
| `tests/test_redraw.py` | new: 8 tests |

No engine, protocol, bot or simulator code changed: the lab engine, the generic policies, the
replay/reconstruction and every protocol adapter picked it up automatically.

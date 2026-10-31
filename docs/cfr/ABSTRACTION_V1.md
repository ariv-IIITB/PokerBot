# Abstraction v1: the contract between the CFR trainer and the Tier 4 runtime

Build map step **C0** (`docs/CFR_BUILDMAP.md` §4). Written 2026-10-31. Status: **draft, frozen
after the Problem Statement (1 Nov)**; re-check §1 then.

The trainer (`lab/cfr/fast/`, Numba) and the runtime (`bot/abstraction.py` v2, `bot/brains/tier4.py`,
NumPy) must agree on every number below, or keys stop matching and the blueprint plays the wrong
strategy without any error. The **reference implementation** of the betting part is
`lab/cfr/fast/tree.py` (plain Python); its tests (`tests/test_cfr_tree.py`) check its chips against
the rules engine `bot/game`. Anything in this document that is not yet code is marked *(C1)*,
*(C2)*, *(C3)* or *(C5)*: the step that implements it and adds the test that pins it.

Any change to this contract bumps the version (`v1` → `v2`), retrains, and re-exports. The blueprint
artifact carries the version, and the runtime refuses a table with another version.

## 1. Game parameters (from the variant spec, never hardcoded)

`tree.Params.from_variant("discard_holdem")` reads `variant/catalog/discard_holdem.json`:

| Parameter | Value | Spec field |
|---|---|---|
| starting stack (reset every hand) | 200 | `match.starting_stack` |
| blinds | 1 / 2 | `betting.small_blind`, `betting.big_blind` |
| bets/raises per street | 4 | `betting.max_raises` |
| the big blind counts as the first preflop raise | yes | `betting.blind_counts_as_raise` |
| hole cards / discard | 3, discard 1 after flop betting, both shown, removed | `program` |

Seats: **seat 0 = button** (posts the small blind, acts first preflop, last postflop); seat 1 = big
blind. Streets 0 preflop, 1 flop, 2 turn, 3 river. Chips are integers. The pot is every chip
committed this hand, this street's bets included (as `bot/game` and the protocol report it).

Legal raise range (as `bot/game/steps/betting.py`): with `high` = the larger street bet,
`min raise-to = high + max(last full raise this street, BB)`, `max raise-to = all-in`
(own street bet + stack); if all-in is below the minimum, only all-in is legal. No raise when the
street's cap is reached, when the actor cannot cover the call, or when the other player is all-in.

## 2. The action menu ("lean", build-map decision D4)

Labels, always listed in this order: `F C H P R A`.

| Label | Meaning | Raise-to amount |
|---|---|---|
| `F` | fold (only when facing a bet) | — |
| `C` | check, or call (one label for both: the history makes it unambiguous) | — |
| `H` | bet ½ pot (unopened postflop street only) | `round(0.5 × pot)` |
| `P` | bet 1 pot (unopened postflop street only) | `round(1.0 × pot)` |
| `R` | raise facing a bet (preflop the BB is a bet) | `round(m × high)`, m = **2.5**, or **3.0** preflop when `high` > BB |
| `A` | all-in | max raise-to |

- The `H`/`P` formula is `bot.actions.pot_fraction_raise` with nothing to call: own street bet + to-call
  + f × (pot + to-call). Preflop and when facing a bet, `R` is the only sized raise.
- **Rounding:** Python `round()` (half to even): 2.5 × 7 = 17.5 → 18, 2.5 × 5 = 12.5 → 12. NumPy and
  Numba `round` agree; never use `int(x + 0.5)`.
- **Clamping:** a size is clamped into [min raise-to, max raise-to]. A size that lands **on all-in is
  labelled `A`**, not `H`/`P`/`R`. Two sizes with the same amount keep the first label in `F C H P R A` order.
  `A` is always offered when a raise is legal.
- **Sized-raise cap (abstraction only): 3.** Once a street has 3 bets/raises (preflop: the BB, an
  open and a 3-bet), only `F C A` are offered. The engine allows a 4th raise; the abstraction
  drops its sized version (rare at 100 BB; all-in stays). Knob: `Params.sized_raise_cap`.

So preflop: button `F C R(5) A`; facing an open `F C R(15) A`; facing a 3-bet `F C A`.
Postflop unopened: `C H P A`; facing a bet `F C R(2.5×) A`; facing a raise `F C R(2.5×) A` until the cap.

## 3. History, key and table layout

**History string:** the labels of every betting action this hand, in order, with `/` appended
when a street closes (`bot.abstraction.extend_history`). The discard leaves no symbol.
Example: `RRC/CHRC/CC/CP` = preflop open, 3-bet, call; flop check, ½-pot bet, raise, call; turn
check-check; river check, pot bet.

**Infoset key (string):** `f"{street}|{bucket}|{history}"` (`bot.abstraction.infoset_key`), where
`bucket` is the **acting player's own** bucket (§5) and `history` is the string before the action.

**Table (integer) layout** *(C3)*: per street `s`, the decision-node histories get dense ids
`0 .. n_hist[s]-1` in the enumeration order of `tree.decision_nodes` (depth first, children in
`F C H P R A` order); `tree.history_ids` builds the map. Row of an infoset:

```
row(s, hid, b) = offset[s] + hid * n_buckets[s] + b,   offset[s] = Σ_{t<s} n_hist[t] * n_buckets[t]
```

Each row has `len(actions(node))` probabilities in label order, quantized to uint8 summing to 255
(`lab/cfr/mccfr.export_uint8`'s rule). Rows the trainer never visited enough (C4's threshold) are
stored as all-zero: the runtime treats an all-zero row as a miss.

**Blueprint artifact** *(C4/C5)*: `ARTIFACTS["blueprint"] = {"meta": {...}, "files": {...}}` via
`tools/embed_data.py`, with `meta = {"version": "v1", "spec_hash", "params", "n_buckets": [1755,100,100,50],
"thresholds": {...§5...}, "histories": [[...], ...] (the strings per street, id order),
"iterations", "trained_at"}` and `files = {"probs": uint8 [rows, 6] (unused columns 0)}`. Shipping the
history strings means the runtime never re-enumerates the tree: it builds `history → id` dicts at
start-up (inside the 5 s start budget, not charged to the bank). `bot/artifacts.built_for` already
rejects a table built for another spec.

## 4. The discard in training (D3)

Both players discard with a fixed policy: **keep the 2 cards with the highest flop E[HS] (§5.2)**,
ties to the first keep in sorted-card order. Both discards are public dead cards for the rest of
the hand. CFR learns betting only. At run time our discard stays Tier 3's PIMC discard; the
turn and river buckets are computed from the cards we actually kept.

## 5. Buckets (D5)

| Street | Bucket | Count |
|---|---|---|
| preflop | lossless 3-card class (`bot/sim/canonical.ClassIndex`, embedded `classes`) | 1,755 |
| flop | 10 × 10 grid over (E[HS], E[HS²]) of the best keep, before the discard | 100 |
| turn | 10 × 10 grid over (E[HS], E[HS²]) of the kept 2 cards | 100 |
| river | 25 bins of exact HS × 1 flush-blocker bit | 50 |

**HS** = showdown share (win 1, tie ½) of a 2-card hand on a 5-card board against one opponent
2-card hand drawn uniformly from the unseen cards. Evaluator: best 5 of 7, standard rankings
(`bot/evaluator.py`; the C1 lookup tables are generated from it).

### 5.1 The shared sampler *(C2)*

Both twins must draw the **same samples**, so the contract fixes the generator:

```
SplitMix64 step (all arithmetic mod 2^64):
    state += 0x9E3779B97F4A7C15
    z = state
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9
    z = (z ^ (z >> 27)) * 0x94D049BB133111EB
    output = z ^ (z >> 31)

seed(street, cards...):  s = 0x5EED0000 + street
                         for c in sorted(hole) + [255] + sorted(board) + [255] + sorted(dead):
                             s = SplitMix64 output of a generator whose state is (s XOR c)
draw index in [0, m):    output % m
two distinct of m:       i = draw(m); j = draw(m - 1); if j >= i: j += 1
```

`dead` = cards out of play that the actor knows: on the turn and river, both discards. The
"unseen" list is `sorted(deck − hole − board − dead)`; draws index into it. A draw from a list with
positions removed (the runout, or the river) indexes the shortened list and is mapped back by
`k += (k >= p)` for each removed position p, in ascending order.

**Exact arithmetic.** A "count" is 2 × wins + ties (an integer). Every feature is an integer sum of
counts divided once by an integer denominator (e.g. flop `E[HS] = Σ_r cnt_r / (2·O·R)`,
`E[HS²] = Σ_r cnt_r² / ((2O)²·R)`), so NumPy and Numba produce the same float bit for bit.
Implemented in `bot/abstraction.py` (runtime) and `lab/cfr/fast/buckets.py` (trainer).

### 5.2 Flop (3 hole cards, before the discard)

`unseen` = 46 cards. Draw **R = 50 runouts** (turn, river: two distinct of `unseen`) and, per runout,
**O = 40 opponent hands** (two distinct of `unseen − runout`); the same samples serve all three keeps.
For each keep K (3 choices), with `share_r` = mean over the O hands of K's showdown share on runout r:
`E[HS](K) = mean_r share_r`, `E[HS²](K) = mean_r share_r²`. The best keep K* = argmax E[HS] (§4).
Features: `x = E[HS](K*)`, `y = E[HS²](K*)`. Draw order per runout: the two runout draws, then
(a, b) for each of the O opponent hands. Ties between keeps go to the first keep.
Cost: 2,000 opponent and 150 own evaluations per player (the opponent samples are shared by the keeps).

### 5.3 Turn (2 kept cards, 4 board, 2 dead)

`unseen` = 44 cards. **Every river card** r (44, exact, in `unseen` order), **O = 24** opponent hands
each from `unseen − r` → 1,056 evaluations. Features as on the flop.

### 5.4 River (2 kept cards, 5 board, 2 dead)

Exact HS against all `C(43, 2) = 903` opponent hands. **Blocker bit** = 1 if any of our 2 cards has a
suit that appears 3 or more times on the board, else 0.

### 5.5 Thresholds *(C2)*

Equal-mass (quantile) cuts fitted once from **200,000 random deals** (both players discarding by §4),
using exactly the estimators above:

- flop and turn: 9 cuts on x; then, inside each x bin, 9 cuts on y (10 × 9) → cell = `10 · xbin + ybin`;
- river: 24 cuts on HS → bucket = `2 · hsbin + blocker`;
- `bin = number of cuts ≤ value` (`np.searchsorted(cuts, value, side="right")`).

The cuts are stored in the blueprint's `meta.thresholds` (so trainer and runtime cannot drift) and in
`lab/cfr/fast/cuts_v1.json` (fitted on 200,000 deals of pool seed 1; cuts sit halfway between two
attainable feature values, so no feature ever equals a cut). Flop and turn cells come out equal-mass
(3,985–4,017 per cell of 400,000 seat-deals); river HS bins are equal-mass and the blocker bit splits them
unevenly (by design).

**Runtime budget:** ≤ 15 ms per decision on the laptop (C2 measures; the server is ~2× slower).
Over budget: precompute the flop features per (canonical flop, 3-card class) offline (size check first).

### 5.6 Training data path *(C1–C3)*

Per-deal features cost ~0.3 ms per core in Numba (both seats, all streets), too much to recompute in
every MCCFR iteration. The trainer therefore samples deals from a **precomputed deal pool**: per deal,
each seat's bucket on every street (with §4's discards) and the showdown result. The betting is the
same for every deal, so the trainer walks `tree.flatten`'s arrays (node → children, actor, street,
history id, chips put in at terminals) instead of running betting logic.

## 6. Worked example (one full hand, every key)

Line (`tree --line "R R C | C H R C | C C | C P C"`). Button: **As Kd 7c**, big blind: **Qh Qs 3d**.
Flop **Kh 8d 2c**; discards 7c (button) and 3d (big blind); turn **5s**; river **Jh**.

Bucket features, computed exactly by enumeration (the sampled §5 values differ in the second
decimal: button flop .892/.799, turn .895/.806; big blind flop .798/.646, turn .791/.635):

| | Button (As Kd 7c) | Big blind (Qh Qs 3d) |
|---|---|---|
| preflop class (exact, `ClassIndex`) | **1486** | **683** |
| flop keeps: E[HS] / E[HS²] | AK .896/.804 · K7 .855/.734 · A7 .498/.281 → keep AK | QQ .784/.622 · Q3 .377/.172 (×2) → keep QQ |
| turn E[HS] / E[HS²] | .890 / .793 | .776 / .606 |
| river HS, blocker | .893, 0 | .784, 0 (board Kh 8d 2c 5s Jh: no suit 3 times) |

With the sampled features (§5) and `lab/cfr/fast/cuts_v1.json` (§5.5) the buckets are: button flop
**93**, turn **89**, river **40**; big blind flop **80**, turn **74**, river **32**
(`tests/test_cfr_deals.py::test_worked_example_bucket_ids`).

Decisions:

| # | Street | Actor | Pot | History before | Menu (raise-to) | Action | Key |
|---|---|---|---|---|---|---|---|
| 1 | pre | button | 3 | `` | F C R5 A200 | R | `0|1486|` |
| 2 | pre | BB | 7 | `R` | F C R15 A200 | R | `0|683|R` |
| 3 | pre | button | 20 | `RR` | F C A200 | C | `0|1486|RR` |
| 4 | flop | BB | 30 | `RRC/` | C H15 P30 A185 | C | `1|80|RRC/` |
| 5 | flop | button | 30 | `RRC/C` | C H15 P30 A185 | H | `1|93|RRC/C` |
| 6 | flop | BB | 45 | `RRC/CH` | F C R38 A185 | R | `1|80|RRC/CH` |
| 7 | flop | button | 83 | `RRC/CHR` | F C R95 A185 | C | `1|93|RRC/CHR` |
| — | discard | both | 106 | | (fixed policy: 7c, 3d) | | no key |
| 8 | turn | BB | 106 | `RRC/CHRC/` | C H53 P106 A147 | C | `2|74|RRC/CHRC/` |
| 9 | turn | button | 106 | `RRC/CHRC/C` | C H53 P106 A147 | C | `2|89|RRC/CHRC/C` |
| 10 | river | BB | 106 | `RRC/CHRC/CC/` | C H53 P106 A147 | C | `3|32|RRC/CHRC/CC/` |
| 11 | river | button | 106 | `RRC/CHRC/CC/C` | C H53 P106 A147 | P | `3|40|RRC/CHRC/CC/C` |
| 12 | river | BB | 212 | `RRC/CHRC/CC/CP` | F C A147 | C | `3|32|RRC/CHRC/CC/CP` |

Notes on the example: at #3 the street has 3 raises (BB, open, 3-bet), so only all-in is left as a
raise. At #12, 2.5 × 106 = 265 is above all-in (147), so `R` merges into `A`. Showdown: the button's
pair of kings beats queens; pot 318. A second example in `tests/test_cfr_tree.py` reaches an all-in on the turn.

## 7. Run time: from the real hand to a key *(C5)*

1. Rebuild the abstract history from `state.hand.history` (betting actions only; `S` skipped).
2. Our past actions were chosen from the menu, so they map exactly. An opponent action maps as
   `bot.abstraction.observed_label` does: fold → `F`, check/call → `C`, a raise whose amount equals
   a menu amount at that node → that label, an all-in → `A`, any other raise → **pseudo-harmonic**
   between the two neighbouring menu sizes, measured as pot fractions at that node
   (`x = (amount − own bet − to-call) / (pot + to-call)`), with the seeded RNG; counted in
   `stats["translations"]`.
3. A raise at a node whose menu has no sized raise (the cap of §2), or any state the tree cannot
   reach (e.g. a history id not in the table) → **miss**: Tier 3 plays the rest of the hand.
4. Our chosen label becomes chips from the **real** state with §2's formulas and
   `LegalActions.nearest_raise` (the real pot can differ from the abstract one after a translation).
5. Misses, translations and lookup time go to `stats`; `cfr_streets` (a brain param) says which
   streets use the blueprint. Any error → Tier 3 (safety layer 1).

## 8. Sizes (from `tree --count`)

| Menu | Histories (pre / flop / turn / river) | Infosets (1755/100/100/50) | uint8 cells |
|---|---|---|---|
| sized-raise cap 4 (engine) | 14 / 176 / 1,444 / 7,776 | 575 k | 1.55 MB |
| **cap 3 (v1)** | **12 / 132 / 1,196 / 6,964** | **502 k** | **1.37 MB** |
| cap 2 (fallback if C3 is slow) | 8 / 60 / 540 / 3,820 | 265 k | 0.73 MB |

The river holds ~70 % of the infosets. The zip limit (5 MB) is not the constraint; visits per
infoset are. If C3 measures < 20,000 iterations/s, drop to cap 2 before cutting buckets.

## 9. What pins this contract

| Test | Status |
|---|---|
| tree chips, pot, to-call and raise bounds equal `bot/game` on 1,200 random lines (caps 4, 3, 2) | `tests/test_cfr_tree.py`, passing |
| the worked example's menus, pots and histories (§6) | `tests/test_cfr_tree.py`, passing |
| history ids dense per street, sizes of §8 | `tests/test_cfr_tree.py`, passing |
| flat tree (`tree.flatten`) == reference tree; terminal payoffs == `bot/game` on 600 random hands | `tests/test_cfr_tree.py`, passing |
| 7-card evaluator == `bot/evaluator.py` on 100 k hands (1 M: slow) | `tests/test_cfr_fast.py`, passing |
| SplitMix64 reference vectors; NumPy and Numba streams, seeds and all features identical on 120 situations (5,000: slow) | `tests/test_cfr_fast.py`, passing |
| the worked example's sampled features (close to the exact ones) | `tests/test_cfr_fast.py`, passing |
| the worked example's bucket ids with `cuts_v1.json` | `tests/test_cfr_deals.py`, passing |
| pool features == runtime features (with the training discard); cuts equal-mass on a fresh pool | `tests/test_cfr_deals.py`, passing |
| runtime key == trainer key on 1,000 random hands | *(C5)*, extends `tests/test_cfr_runtime.py` |

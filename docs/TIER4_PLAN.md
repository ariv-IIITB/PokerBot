# Tier 4 plan (v3, 2026-11-02)

At `main` = `1b29915`, with `origin/x/exploit-layer` (`43df7e8`: X1 traits, X2 type posterior,
X3 λ-layer `tier3x`). Phase H is a separate plan (`docs/PHASE_H_PLAN.md`).

**Scope: our track alone, until 10 Nov.** The teammate's CFR (`cfr/tier4`) is independent. Merging the
two is **Tier 5** (after 10 Nov) and is not in this plan. Nothing here waits for CFR.

**Tier 4 = Tier 3 + a Hyperborean-style portfolio that picks the best counter-strategy for this
opponent online + much better use of the discard + a live river solver.** Tier 3 stays the fallback
inside every decision. Brain name: `tier4p` (`tier4` is taken by the CFR brain).

Order: **P (portfolio) → D (discard) → R (river)**. P and D touch different code and can run in parallel.

---

## P. The portfolio (Hyperborean "implicit modelling", built on our own policies)

**Idea (Bard, Johanson, Burch, Bowling 2013):** carry several strategies. After every hand, estimate how
much *each* would have won against this opponent, even the ones we didn't play, using importance
sampling. Play the one with the best estimate. Hyperborean's members were restricted-Nash / data-biased
responses from CFR. Ours are **Tier 3 with different parameter sets**, each tuned offline against one
opponent family, so this works now without CFR. In Tier 5 the CFR counter-strategies can join the same portfolio.

Why this before more hand-written counter-moves: the selection picks **whatever actually wins against
this opponent**, measured in this match. It doesn't rely on us guessing the right LLM pattern.

### P0. Baseline (1 command, overnight, 3 Nov)
Run gate X as written in `docs/CFR_BUILDMAP.md` §3: `tier3x` vs `tier3` on the training pool, 50 pairs, locks on.
`tier3x` becomes one portfolio member either way; this gives the number P must beat.

### P1. Policies return a distribution (3–4 Nov)
Importance sampling needs **the probability each member gives to the action we took**, at every one
of our decisions. Today a brain samples and returns one action.
- Add `Tier3Brain.policy(situation, params) -> list[(Action, prob)]`. Tier 3's mixing already
  computes the probabilities; return them instead of sampling. `play()` samples from `policy()`, so
  play is unchanged (test: same seed → same actions as before).
- Deterministic spots get an ε-floor (ε = 0.03 on every legal abstract action) so no member's
  probability is 0.
- The **situation is built once** per decision (equity, inference, ranges). Members differ only in
  parameters, so computing K distributions costs K cheap policy calls, not K equity runs. Measure it:
  K = 6 must add < 10 % to decision time.

### P2. Members (4–6 Nov)
K = 5–6 parameter sets over Tier 3, each a dict of overrides (same mechanism as `exploit.adjust`):

| member | aimed at (pool bots) | direction |
|---|---|---|
| `base` | anyone, safe | Tier 3 as shipped |
| `x` | mixed | Tier 3 + the X3 λ-layer |
| `anti_folder` | exploiter, conv_opp3, rules, geometric | bet and bluff much more, smallest size whose break-even fold rate is below theirs |
| `anti_value` | six of nine (rarely bluff the river) | fold bluff-catchers to river bets and raises, value-bet thinner |
| `anti_station` | starter, calling_station, trapper | no bluffs, bigger and thinner value bets |
| `anti_aggro` | lag, maniac | call down wider, trap, fewer bluffs |

**Offline tuning per member (the "restricted" part of RNR, measured instead of solved):** tune each
member's numbers with the league loop (book §2.11) to **maximise chips against its family**, subject to
**not losing more than 0.5 chips/hand head-to-head vs Tier 2 and Tier 3**. Tier 2/3 stand in for
"a balanced opponent", so the restriction keeps each member hard to punish. Use the training pool only;
held-out bots stay unseen.

### P3. Online selection (5–7 Nov)
- After each hand, for each member k: `v_k += w_k · Δ`, with `w_k = Π π_k(our action) / Π π_played(our action)`
  over our decisions in the hand, Δ = our net chips. The opponent's play cancels out of the ratio, so this is
  unbiased for every member from the same hands. Clip w_k at 20 (variance), and track the SE of each v_k.
- Start on `base`. Switch to member k only when `v_k − v_current > 2 · SE`. A prior from the X2 type
  posterior can break ties early (e.g. a confident over-folder → `anti_folder` first).
- Safety: `base` is always in the set. If the played member's running result drops 2 SE below `base`'s
  estimate, switch back (this replaces the X3 CUSUM bail-out).
- **Safe-exploitation budget** (Ganzfried & Sandholm 2015, "Safe Opponent Exploitation"): a counter-member
  may play only while our match result is above what `base` would have earned (its IS estimate) minus a small
  allowance (start: 1 SE). Wins beyond `base`'s estimate are what we risk on exploitation; money we're behind is not.
- The endgame lock works as today, before the portfolio.
- Stage 2 matches are ~1000 hands, so the selection has 2.5× more data there: check it in both lengths.

### P4. Tests and gate P (7–8 Nov)
- Unit: the IS estimate equals the true value on a toy game with a known opponent; `policy()` sums to 1
  and covers only legal actions; same seed → same play when K = 1.
- Detection: on recorded matches, the right member is chosen by hand ~100 against each family.
- Adversary: a lab bot that over-folds for 100 hands, then calls everything. The portfolio must return to
  `base` and lose less than `tier3x` does.
- **Gate P:** `tier4p` vs `tier3` and vs `tier3x`: 100 duplicate pairs head-to-head > 0.5 by 2 SE; training
  pool `--compare` KEEP (no bot down > 2 SE); fresh seeds; timing ≤ 50 % at 2× slower.

**Is this aimed at LLM patterns?** The members are, deliberately: real competitors' bots are also LLM-written,
then tuned by people. But the selection only picks a member that is measured to win against *this*
opponent. Against a balanced bot no counter-member wins, so it stays on `base`.

---

## D. The discard (our biggest untapped edge)

Hold'em has no discard theory, and LLM bots treat it simply (most discard their lowest card 60–68 % of
the time, book §2.8). Today we: pick our own discard well (`bot/sim/discard.py`, sampled), and weight the
opponent's hand by a fixed "sensible discard" model (`bot/sim/inference.py`, `beta`). Gaps found 2 Nov:
**(1) the flop equity's simulations discard at random for both players** (`smart_rollout_discard` is off,
`bot/sim/rollout.py`), so every flop bet/call decision mis-values the hand; **(2) the opponent's discard
model is fixed**, not learned from this opponent.

### D1. Flop equity with real discards (3–5 Nov)
- Turn `smart_rollout_discard` on (both players keep their best two in every rollout). In Phase E it lost
  1.3 ± 0.4 vs tier1 only because the betting thresholds were tuned on the random-discard equity.
  **Retune** `raise_equity`, `call_margin` and the flop thresholds with it on (small grid, 30 pairs per point).
- Better: in rollouts, the opponent discards by **their learned rule** (D2), not ours.
- Check the cost per rollout; keep only if timing passes.

### D2. Learn the opponent's discard rule (4–6 Nov)
- **Every showdown after a discard reveals all 3 of their cards** (the 2 shown + the discarded one) and the
  flop. So each showdown is a labelled example of their discard rule.
- Library of rules: `lowest_rank` (the engine default), `keep_highest_two`, `keep_pair`,
  `keep_flush_draw`, `keep_straight_draw`, `best_made_hand`, `equity_max` (our own), `random`.
  The posterior over rules is updated per showdown (likelihood with a 10 % noise floor).
- Prior from the X2 type (recorded pool bots: measure which rule each one follows, from X0 recordings).
- Feed it to `inference.py`: replace the fixed softmax with the rule mixture. Under `lowest_rank`, a
  discarded 9 means both kept cards are ≥ 9: a huge range cut on the turn and river.
- Measure: how many showdowns until the right rule has 90 % (aim: ≤ 8), and inference error before/after.

### D3. Use the range cut in betting (5–7 Nov)
- Turn/river decisions already use the inferred range; with D2 it is much sharper. Check that the river
  bluff-catch and value thresholds use the *range* (not just equity vs random) after the discard.
- How much a discard tells us depends on their rule: under `lowest_rank` a high discard means two higher
  cards kept; under `keep_pair` it means a pair or a draw. Measure chips per spot with `lab.opps.accounting`.

### D4. Our discard vs their likely keep (5–6 Nov)
- The fast discard samples opponent hands. Make it sample from their **inferred range after the flop
  betting** and let them keep by **their learned rule**, not uniformly at random.
- Spend more compute here if it pays: `lab.discard_bench` at 1×, 2×, 4× budget; raise the discard's share in
  `bot/timing.py` only if the gain is > 2 SE.

### D5. Do they read our discard? (6–7 Nov)
- Measure per pool bot: their turn fold and bet rates conditioned on the rank of the card we discarded.
- If they ignore it: discard purely for equity (`hide_discard` off).
- If they read it naively ("threw a high card → strong"): among near-equal discards, choose the one that
  sends the signal we want (throw the high card when we want folds, the low one when we want calls).
  A/B it; this is G7's `hide_discard` turned into a deliberate signal.

### Gate D
Each of D1–D5 is kept only by the keep rule: training pool up, no bot down > 2 SE, timing passes.
Report every result, kept or dropped, in `docs/reports/TIER4_DISCARD.md`.

---

## R. Live river solver = restricted Nash response on the river (7–10 Nov, after P and D)

Method: **continual depth-limited restricted Nash response (CDRNR)**, Milec, Kubíček & Lisý, AAMAS 2024
(arXiv 2112.12594): solve the subgame live with the opponent fixed to our model with probability p and free
otherwise. It needs no precomputed CFR. Earlier streets would need a value function at the depth limit; the
river is the last street, so it needs none. That is why we do it on the river.

- `bot/cfr/river.py`: vector CFR+ over ≤ 903 opponent hands × our range, sizes ½ / pot / all-in, ≤ 2 raises,
  O(n) sorted showdowns. Our range from `OwnRange`; theirs from inference **with D2's discard cut**.
- Restricted: the opponent's river strategy = p · (model from the X2 type and their per-spot stats) + (1 − p) · free
  (the solver's best response). p = 0 is the plain equilibrium solve; p comes from our confidence (X1/X2 λ).
  A/B p = 0 vs p = λ.
- The portfolio decides how to use it: the solver's line becomes `base`'s river, and the counter-members
  apply their shifts on top.
- Tests: equals `lab/cfr/exact.py` on toy rivers; ≥ 50 iterations ≤ 100 ms at 2× slower, else Tier 3's river.
  About 40 % of hands reach the river; at 100 ms that is ~16 s of a 60 s bank before the 2× slowdown, so cap it.
- **Gate R:** `tier4p` with vs without the solver, 100 pairs + pool + accounting (river showdown losses
  shrink). Fail → drop it.

---

## Rules for every step

- Tier 3 is the fallback for every error, timeout or missing piece. Never forfeit.
- Duplicate pairs, fresh seeds, ± SE; one eval at a time per machine (budgets are wall-clock).
- `tests/test_timing_slow.py` after any `bot/` change. Nothing reads files at runtime (`tools.embed_data`).
- Upload `tier4p` as soon as gate P passes; later passes become later uploads.

## Dropped from v2

- "Measure Tier 3's style": it doesn't change any decision. The style is a means; match results are the goal.
- Hand-written counter-moves X3b: they become portfolio members (P2), tuned and selected by measurement.
- Waiting for gate A, the merge, `tier4x`: Tier 5, after 10 Nov.

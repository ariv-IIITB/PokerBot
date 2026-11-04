# PF: offline preflop chart (Sonnet; starts only after RC is pushed, user-approved 2026-11-04)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/reports/TIER4_RIVER.md` (so you know what RC left in `tier3.py`), and on
`tier4/r` how Tier 3 plays preflop today (`bot/brains/tier1.py` / `tier2.py` preflop path, `data/discard_holdem/` classes + `eq_*.npy`).
Branch `tier4/pf` from `origin/tier4/r` (after RC). Seeds 60000–60999. Light-testing rules of the README apply.

**Idea (from a friend's architecture sketch; treat as unproven):** the 1,755 suit-isomorphic 3-card classes already exist and are
embedded. Solve the small preflop betting game offline (SB/BB, raise cap as in the rules) per class and embed the resulting
action frequencies and sizes, so preflop costs a table lookup at play time (no time-bank cost).

## Steps (each ends with a go/no-go; stop and hand off on NO-GO)
1. **Is there anything to win?** From S0's recordings (`logs/records/s0_9000/`, Tier 3's play) and the accounting: chips/hand won or
   lost preflop (folds, blind steals, 3-bet pots) per bot. If preflop leaks < 0.15 chips/hand against every over-folder, NO-GO: write the
   numbers and stop.
2. **Leaf values.** After a preflop call there is a flop; the value needs an equity-realisation model (class vs class equity x a
   realisation factor by position). Build the 1,755 x 1,755 class-vs-class equity matrix offline (exact or ≥ 2,000 samples per
   pair, report SE) and fit the realisation factor on recordings. State its error. (This is the "no value estimate" problem that
   rules out solving earlier streets live; offline it is only acceptable if the fitted factor reproduces recorded preflop-call EVs.)
3. **Solve** the preflop game with CFR+ (the sequence-form LP is allowed if SciPy is faster and exact; pick one, measure
   exploitability in the abstract game). Embed as a compact table via `tools/embed_data.py` (≤ 1 MB).
4. **Use it** behind a Tier 3 flag `t3_preflop_chart` (default off): a lookup; if the spot is outside the table, Tier 3's old preflop.
5. **Gate** vs `tier3` (RC's final defaults): head-to-head 50 pairs, score ≥ 0.5 − 2 SE; one 50-pair pool run, two-part KEEP;
   timing ratio unchanged (a lookup). Held-out bots are I1's. KEEP → flag on in `DEFAULTS`, `tools.embed_data`.

Files: `tools/preflop_chart.py` (new), `data/discard_holdem/preflop*.npy` (new), `bot/brains/tier3.py` (preflop hook only),
`docs/reports/TIER4_PREFLOP.md`, tests. Handoff: `docs/tier4/handoff/PF.md` (≤ 40 lines).
Slip rule: PF is dropped first (before everything else in the README's list).

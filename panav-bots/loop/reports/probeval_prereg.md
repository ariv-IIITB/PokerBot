# PROBEVAL pre-registration (written BEFORE any probeval run; 15 Nov 2026)

Question: ship raw (ungated) `probe`? base = `evalbuilds/final_seeded.py`; cand = `meta1/builds/sw_probe.py` (both seeded, so paired).
META1 evidence (29 bots, seeds 13000-13023, 14000-14023): +7.2 pp match wins, +0.31 chips/hand, but new_trapper -46 pp (replicated).
That evidence selected the question, so it is NOT counted here. This run uses fresh single-use seeds.

## Seeds (single-use, disjoint from META1's 13000-13023 / 14000-14023; ledger in results/SEEDS.md)
- Stage 1, 200h legs: 30000-30039 (40 pairs per bot)
- Stage 2, 500h legs, lakshya1 and new_eqrandom: 30100-30123 (24 pairs)
- head-to-head cand vs base, 200h: 30200-30239 (40 pairs); also 500h h2h 30300-30315 only if Stage 2 is judged.
No seed is rerun. A crashed run may be relaunched with the same seeds (same experiment, not a new look). No sealed `holdout/*` bots are opened.

## Validation bots (30): Opps/discard x9 (conv_opp3, conv_opp4, new_eqrandom, new_exploiter, new_geometric, new_lag, new_minraise, new_rules, new_trapper),
eval_bots spar x10, strong x10, opponents/lakshya1. These are the same bots as META1's table; they are disjoint only in SEEDS, not in identity,
because the question asked is "does raw probe survive fresh deals across the whole zoo". No bot was used to design probe's move beyond META1's selection, stated here.
"Trapper-type" bots (adversary class) = new_trapper, spar/trapper.

## Metrics
Match = one duplicate pair (both seat-swapped legs); win if total chips of cand/base > 0, draw 0.5. Per seed s and bot b: d(s,b) = result_cand - result_base (paired by seed).
Pooled win-rate gain = mean over all bots and seeds of d, in pp. SE = SD over the 40 seeds of the per-seed mean over bots / sqrt(40) (also reported: SE across bots).
Chips: per-pair chips/hand delta, pooled the same way. Always printed: MATCH WINS W/N and % for base and cand, per bot and pooled, BEFORE chips.
s1_ranges (degenerate folder, base wins ~all) stays IN the pooled number; a sensitivity line without it is reported but is not the pass rule.

## PASS rule (Stage 1; all must hold; fixed now, not to be relaxed)
1. PRIMARY: pooled match-win gain cand - base over ALL 30 validation bots INCLUDING trapper-type bots >= +2.0 pp. (Also report excluding trapper-type: informational.)
2. Pooled chips/hand gain (cand - base) >= 0.0 over the same field.
3. Per bot: list every bot down by > 2 SE of its paired difference (reported; trapper-type losses are named as the adversary cost; any other bot down > 2 SE is a FAIL unless it is a single bot of ~30 and its loss < the pooled gain / 10 - to avoid post-hoc wiggle: simply, any non-trapper bot down > 2 SE = FAIL).
4. lakshya1 (500h legs, Stage 2): cand match wins not lower than base. Head-to-head cand vs base (200h, 40 pairs): cand wins >= 50% of matches (draws 0.5).
5. Zero forfeits / illegal replies; reply time within 5 ms of base (checked in the packaging step).
Adversary cost rule: the match-win loss vs trapper-type bots is reported in pp and as its contribution to the pooled average; probe passes only if the pooled gain INCLUDING them is >= +2.0 pp (rule 1).
Stage 2 (500h): lakshya1 + new_eqrandom only (24 pairs): reported separately; with 2 bots it is evidence, not a Stage-2 pass. If Stage 1 passes but Stage 2 fails, enable for Stage 1 only (bot knows total_hands).
If rule 1-5 pass, then build `cands/final_probe.py` (normal, non-seeded) + legality fuzz / timing / memory / sandbox as in INT1. Otherwise ship nothing.

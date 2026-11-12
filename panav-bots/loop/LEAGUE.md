# LEAGUE: search for the opponents that beat final, then make final robust to them (12 Nov)

Why: final already beats most hand-written bots, so leak-hunting in their logs is noisy. The opponents that matter in the tournament are those that BEAT final
(lakshya1 is one). So we build a parametric bot family, search its settings for the ones that win the most chips against final, and read off the weakness.
Fixes later must make final robust over the WHOLE region, validated on random settings the search never touched AND on the real bots (ZOO.md folds, lakshya1 included).

## EX1 deliverables (no edits to final)
1. `panav-bots/loop/league/param_bot.py`: ONE stdlib-only bot template (real protocol, never crashes, every reply legal, <= 20 ms mean reply, no stdout noise) that reads a PARAMS dict
   and a generator `league/make_bot.py PARAMS.json OUT.py` that writes a standalone bot file with the params baked in (file_duel runs files; both players share the environment, so no env vars).
   You may copy and adapt `panav-bots/eval_bots/spar/common.py` (own evaluator, 3-card preflop table, MC equity). Params (about 12-16, each with a sane range): preflop open freq and 3-bet freq and fold-to-3-bet;
   per street (flop/turn/river): bet freq when first to act, bet freq when checked to as the non-aggressor (probe), size as a pot fraction in {0.25 ... 2.5}, bluff share of its bets, check-raise freq,
   raise freq when bet into, call threshold (equity minus pot odds margin), give-up probability after a called bet; use of the revealed discard (on/off). Include corner styles: nit, station, maniac, overbettor, check-raiser, probe-bettor.
2. A search driver `league/search.py`: random sampling then cross-entropy refinement (population ~24, 4-5 rounds), fitness = chips/hand of the param bot vs `panav-bots/final/bot.py` (via `tools/file_duel.py`, paired deals, 200-hand legs).
   Budget with care: first measure the time of one 8-pair evaluation; keep the total under ~3 hours wall-clock; <= 3 processes. Seeds: search 1000-1999 (ledger in `results/SEEDS.md`), confirmation of top configs 2000-2099 (24 pairs, 200 hands; AND 8 pairs x 500 hands), random-config holdout 3000+ (RESERVE: do not use).
3. Report `panav-bots/loop/reports/ex1_vulnerabilities.md` (<= 90 lines): the top 5 distinct vulnerabilities (cluster the winners; describe each as observable behaviour: bet rates, sizes, how final responds, which decision class loses the chips via leak_report on logs of the confirmed winners),
   the chips/hand each wins with CI, whether it still wins on the confirmation seeds (shrinkage = noise), and, as a diagnostic only, which cluster lakshya1 sits nearest to (run lakshya1's behaviour stats against the params; do not tune to it).
   Also report: which of these configs do WELL against the zoo bots (spar/strong/Opps) — i.e. are they just generally strong, or specifically anti-final. Commit configs (json), the winners' bot files, the logs summary. Branch `loop/ex1`. Push partial results every ~45 min.
Honest outcome allowed: 'no config beats final by more than noise'. Do not claim wins the confirmation does not support.

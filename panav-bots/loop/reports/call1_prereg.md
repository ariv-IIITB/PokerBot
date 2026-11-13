# call1 PRE-REGISTRATION (written before any validation run; not to be changed)
Candidate = `cand_v1`: config potfold=on, pf_p = 0.75 on every (street, seat), pf_cut = 0.9 on every street (S1/max proxy),
size window 0.75-1.2 pot, not all-in, gate off when the exploit layer's aggressor or riverbluff trait says yes,
ledger prior mu0=-15 chips/call, sigma=70, n0=25 (g = clip(posterior mean / mu0, 0, 1)). Source: `call1_src/`.
Chosen on the 7 dev bots only (seeds 6000-6059 logs; A/B on 6000-6029: p=.75 pooled +0.32 +- 0.08 over 7 bots; p=1.0 on 4 bots +0.79 vs +0.60
for p=.75; p=.75 kept because p=1 leaves the ledger no data). Cut .9 from the table: px .90-.95 calls are ~0 EV, px<.9 -15.4/call.
VALIDATION: 22 bots (spar/{trapper,polar,betfold,light3b,donk,adapt,tilt,discardread}, Opps/discard/{new_rules,new_trapper,conv_opp4,new_lag},
strong/{s1..s10}), seeds 10000-10039, 40 pairs x 200h, base = final_seeded, cand = cand_v1, same seeds (paired).
PASS = all of:
 1. pooled mean delta (cand - base, chips/hand) over the validation bots >= +0.15 and >= 1.5 x its SE (SE = sqrt(sum SE_i^2)/k);
 2. pooled match wins (pair = match, won if chips > 0, tie 0.5) cand >= base;
 3. no validation bot with delta < -2 SE_i;
 4. lakshya1 500h, 24 pairs, seeds 10100-10123: delta >= +0.30;
 5. new_eqrandom 500h, 24 pairs, seeds 10200-10223: delta >= -1 SE (not worse);
 6. head-to-head cand vs base, 40 pairs, seeds 10300-10339: mean >= 0;
 7. potbluffer, 40 pairs, seeds 10400-10439: loss (base - cand chips/hand, if positive) < pooled validation gain;
 8. mean reply time (from the bot's own per-decision timing log, all validation matches) within 5 ms of base; no forfeits, no errors.
Stage 1 (200h) and Stage 2 (500h) are reported separately. Sensitivity arm p=1.0 (info only) on a subset.

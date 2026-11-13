# DISC1 seed ledger (single-use)
| range | purpose | bots |
|---|---|---|
| 9000-9029 | discard audit logs (final_seeded as A, 200h legs, logs on) | spar trapper, betfold, donk, light3b; Opps new_exploiter, new_lag |
| 9100-9139 | pass-rule check, base vs cand, 40 pairs x 200h, paired | 9 spar (trapper potctl polar betfold light3b donk adapt tilt discardread) + 9 Opps/discard |
| 9100-9139 | head-to-head cand vs base (200h) | - |
| 9200-9223 | 500h legs (Stage 2 length), base vs cand | lakshya1, new_eqrandom |
Note: bots used for the audit (9000s) are DEV for the discard fix; the 9100+ check re-uses them with fresh deals (seeds never overlap).

# call1 seed ledger (single-use)
| range | purpose | bots |
|---|---|---|
| 6000-6059 | base logs for the counterfactual table (200h, 60 pairs) | 7 dev bots |
| 6000-6029 | dev A/B, base vs cand_v1 (p=.75) and cand_p1 (p=1.0, 4 bots) | 7 dev bots |
| 10000-10039 | VALIDATION, 40 pairs x 200h, base and cand paired | the 22 validation bots |
| 10100-10123 | lakshya1 500h legs, 24 pairs | lakshya1 |
| 10200-10223 | new_eqrandom 500h legs, 24 pairs | new_eqrandom |
| 10300-10339 | head-to-head cand vs base, 40 pairs x 200h | final_seeded base |
| 10400-10439 | potbluffer, 40 pairs x 200h, base and cand | adversaries/potbluffer.py |

# DB: what their discard tells us (Opus, cloud)

Read: `CLAUDE.md`, `docs/tier4/README.md`, this file, `docs/TIER4_PLAN.md` §D0, D2, D4, `docs/tier4/handoff/S0.md`,
and `bot/sim/discard.py` (`opponent_keeps`), `bot/sim/inference.py` (`_discard_ll`, `beta`, `Trust`).
Branch `tier4/d-learn` from `origin/tier4/base` (start after S0 has pushed its recordings; merge `origin/tier4/s0` in
for them). Files: `lab/opps/discard_rules.py` (new), `bot/sim/inference.py`, `tests/test_discard_rules.py`,
`docs/reports/TIER4_DISCARD.md` (append a DB section; DA writes its own section). Seeds 21000+.

## Part 1: measure (offline, on S0's recordings 9000–9011)
1. **D0, rule fit:** for each training bot, compare its real discards with these rules: `opponent_keeps` (our current
   model, the baseline), `drop_lowest`, `keep_pair`, `keep_flush_draw`, `keep_straight_draw`, `random`. Report per bot:
   the share of hands where the bot disagrees with `opponent_keeps`, and the share each rule explains.
   **Go for part 2 only if** some training bot disagrees with `opponent_keeps` on ≥ 15 % of its hands *and* one rule
   explains ≥ 80 % of its discards.
2. **D4, do they read our discard:** per training bot, their turn fold rate by the rank of the card we discarded
   (low / mid / high), chi-square, p < 0.01 with Holm across bots. Report which bots react. (DC uses this.)
3. Write both tables to `docs/reports/TIER4_DISCARD.md`. If part 1 says no-go, write the handoff and stop.

## Part 2: learn their keep rule (only if go)
4. A posterior over the D0 rules, updated at each showdown after a discard (all 3 of their cards are then known), with
   a 10 % noise floor. The prior per X2 type comes from D0's measured mix, fitted on seeds 9000–9005 and embedded
   through `tools.embed_data`.
5. `inference.py`: the discard likelihood uses the rule mixture instead of the fixed softmax, behind a param
   (`discard_rule_model`, default off). Any error → the old softmax.
6. **Selection bias check:** on 9006–9011, the posterior's accuracy with showdown-only data vs with all data.
7. **Gate:** on 9006–9011, the log-likelihood of their shown turn hand is better by > 2 SE. Then
   `tier3:{"discard_rule_model":true}` vs `tier3`, 50 pairs, two-part KEEP, plus a fresh-seed confirmation. Read the
   param with `p.get("discard_rule_model", False)`; don't add it to any `DEFAULTS` or create `bot/config/tier3.json`
   (DA owns that file on another branch). On KEEP, say so in the handoff and DC turns it on.
8. Tests: the posterior moves to the right rule on synthetic showdowns; an error falls back to the softmax.
   Fast suite green, push, handoff.

**Provisional (cloud):** part 2's KEEP is a cloud number; DC's step 0 re-runs it on the laptop.

## Done when
- `docs/tier4/handoff/DB.md`: the D0 table and the go/no-go; the D4 list of reacting bots; if part 2 ran, KEEP or DROP
  with numbers, the param name, the commit.

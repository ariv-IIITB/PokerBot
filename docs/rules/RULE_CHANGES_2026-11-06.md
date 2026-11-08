# Rule changes in the updated rulebook, problem statement and protocol (user-supplied PDFs, 2026-11-06)
New PDFs are in `docs/rules/`; the 2026-10-28 versions are in `docs/rules/old_2026-10-28/`. Deadline unchanged (15 Nov 2026, 23:59 IST).
Where the starter kit (incl. `engine.py`) differs from these documents, the documents prevail.

- **Two legs per match.** A match = two legs between the same two bots; each leg has every deal once; leg 2 swaps hole cards and seats (same boards). Each leg is a
  FRESH bot process, so no process plays both hands of a duplicate deal. State may be kept within a leg only. Result = net chips over both legs.
- **Sizes and banks (provisional):** Stage 1 = 2 legs x 200 hands, bank 30 s per leg; Stage 2 = 2 legs x 500 hands, bank 75 s per leg. Same 0.15 s/hand as before.
  `init.total_hands` is 200 / 500 and `time_bank_ms` 30000 / 75000. `match_end` is sent at the end of each leg. Wall-clock kill 90 s / 225 s per leg.
- **Start-up:** 5 s at the start of each leg. A request's clock starts at the later of "sent" and "5 s after launch"; the first reply may come up to 10 s after launch.
- **Files:** a bot MAY read files inside its own submission (still no writes, sockets, or processes). Not needed by us (data is embedded).
- **Forfeit:** in either leg forfeits the whole match (leg 2 not played): loss with delta = -C, opponent +C; Hm for a forfeit = scheduled hands (400 / 1000).
  No reply at all = timeout. Illegal discard or bad card field = lowest-ranked card discarded (as before).
- **Stdout:** a debug print while a request is outstanding is read as the reply (malformed) and the real reply is ignored: stdout must be protocol only.
- **Protocol:** `raise` may be absent from `legal_actions` while `raises_left > 0` (opponent all-in): always choose from `legal_actions`. `hand_id` is 1-indexed within the leg.
- **Other:** round robin if < 64 valid bots (was "about 64"); a team may upload several times, the last valid upload counts; trying to identify the two hands of a duplicate
  deal or to carry information between legs is prohibited; the number of Swiss rounds is announced before Round 1.
- **Impact on us:** the bot sees 200 hands per opponent, then restarts from zero. Everything adaptive (exploit layer, O3 narrowing, H1) was tuned at 400 hands in one process.
  Lab equivalent of the new format: `lab.eval ... --hands 200 --bank 30` (a duplicate pair = one match = 2 legs). `variant/catalog/discard_holdem.json` and `variant/active.json`
  still say 400 hands / 60 s (to update, then `python -m tools.embed_data`).

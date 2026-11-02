# Phase H: the Problem Statement (for a Sonnet session)

Read `CLAUDE.md`, `docs/STATUS.md` and `docs/rules/SUMMARY.md` first. Work on a branch `phase-h`,
then merge into `main` and push. Tests on Python 3.11: `.venv/bin/python -m pytest -n auto`.

## Input

The Problem Statement, released 1 Nov 2026: `docs/rules/problem_statement.pdf` (8 pages, already committed).
Checked on 2 Nov: **it changes no rule.** Every rule matches `docs/rules/SUMMARY.md` and
`variant/active.json`. It settles one open question: **at showdown each player uses the best 5 of the 7
cards (both, one or none of the 2 hole cards).** Provisional limits are unchanged.

## Tasks

1. **Filed.** The PDF is already at `docs/rules/problem_statement.pdf`; nothing to do.
2. **SUMMARY.md.** In "Game", replace "Our reading is that any 5 of the 7 count … To confirm on 1 Nov"
   with the confirmed rule (cite PS §6). Replace "Still unknown" with what is still open: final values
   of the provisional limits, and the organisers' starter kit match runner (PS §9 tells teams to use it;
   we don't have it). Add a source line for the Problem Statement, and note PS §10 (precedence: PS wins
   on game rules).
3. **Check the evaluator** does best-5-of-7 with 0, 1 or 2 hole cards (play-the-board): find the
   existing test or add one (PS example 8.5, split pot on T♠ J♠ Q♢ K♡ A♣).
4. **Worked examples as tests**, in a new `tests/test_problem_statement.py`. Use the existing scenario
   and transcript kits (see `tests/test_pokerbots.py`, `tests/test_discard_holdem.py`, and the Phase A
   kits; read them before writing). One test per example, asserting the numbers printed in the PS:
   - **8.1** full hand: pots after each action, min raise 16 on the flop re-raise, 170 / 130 behind,
     the `discard_result` line for A (`my_discard` 4c, `opp_discard` Kc, `hole_cards` [Qh, Jh]),
     the showdown (flush beats trips), net +140 / −140. Also the duplicate: the same board with the seats swapped.
   - **8.2** raising war: min raise 4 → 10 → 30, raises left 3 → 2 → 1 → 0, then B's legal actions are
     exactly fold and call; after the call the pot is 100 with 150 behind each.
   - **8.3** preflop all-in: no flop betting, **both players still get a discard request**, three aces win,
     net +200 / −200.
   - **8.4** fold on the flop: **no discard request**; A's `hand_result` lists A's 3 hole cards, with
     `opp_hole_cards` and `opp_discard` null; net −2 / +2. The bot must parse this without error.
   - **8.5** kicker (A-A-K-Q-8 beats A-A-K-J-8) and the split pot (both play the board, net 0).
   - **8.6** engine corrections: illegal discard Kh from 7♢ 7♠ A♣ → 7s discarded and the
     `notice` `{"code":"illegal_discard","applied":"7s"}` is sent; raise to 1 with to_call 0 → check;
     check facing a bet → fold. Our bot must never trigger these: add a check that the bot's own
     replies in 8.1 to 8.4 are always legal.
5. **The bot side of the protocol.** Run the shipped bot (`python3.11 bot.py`, the real `pokerbots`
   adapter) through the 8.1 and 8.4 transcripts and assert it handles `discard_result` with
   `hole_cards`, and a `hand_result` with null opponent fields, and that stdout carries only protocol lines.
6. If any test fails, **fix the code, not the test**, and note the fix in the report. If a PS number
   disagrees with our engine and the PS is clearly right, the PS wins (PS §10).
7. Update `docs/STATUS.md` (Phase H row: done) and the "Phases" line in `CLAUDE.md` if it mentions H as open.

## Done when

- The new tests pass, the fast suite is green on 3.11, and `tests/test_timing_slow.py` passes.
- `tools.package_submission --zip --stage2` still passes. Don't upload; just report.
- Commit `phase H: Problem Statement filed, worked examples as tests`, merge into `main`, push.
- Short report: what was added, any engine/adapter fixes, test counts.

Do not change any strategy code or brain parameters in this phase.

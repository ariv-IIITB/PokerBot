# Recursive-improvement loop for `final` (read all of it; written 12 Nov 2026)

Goal: find chip leaks of `panav-bots/final/bot.py` ("final": CFR blueprint + river solver + exploit layer) against bots it has not
seen, fix only the leaks that are **general principles**, and prove the fixes help on bots that were never used to find them.

## How the older work trained (so we do the same, not worse)
- Tier 3 (docs/reports/TIER3.md): tuned on a training pool of the 9 Opps/discard bots, 3 held out (`lab/opps/discard_pool.json`);
  a change is KEPT only on `lab.eval --compare` sum of per-bot chips/hand deltas > 0 with no bot clearly down, and held-out checked once.
- Lessons that cost us before: (1) a "leak" that looks real in the logs can be selection bias (12 Nov `overbetdef` made the
  fold rate better and lost 0.69 chips/hand: the extra calls were marginal losers); (2) a fix tuned on one bot (`panav5_lk`,
  lakshya1) is overfit by construction; (3) noise: 8 duplicate pairs give about +-1 chip/hand, so single-bot totals prove nothing.
- Therefore: judge a fix by **mechanism** (did the changed decisions gain EV? log them) AND by **pooled** result on UNSEEN bots.

## Bots
- Fresh bots (4 batches of 5, `panav-bots/eval_bots/`):
  - B1: spar/eqtag, spar/trapper, strong/s1_ranges, strong/s2_rollout, strong/s3_exploit
  - B2: spar/potctl, spar/polar, strong/s4_balanced, strong/s5_preflop, strong/s6_discard
  - B3: spar/betfold, spar/light3b, strong/s7_solver, strong/s8_meta, strong/s9_sizing
  - B4: spar/donk, spar/adapt, spar/tilt, spar/discardread, strong/s10_regret
  (each is `<dir>/bot.py`; run it with its own folder as cwd, which `file_duel` does)
- Old pool (overfit-check set, 9 bots): `Opps/discard/{conv_opp3,conv_opp4,new_eqrandom,new_exploiter,new_geometric,new_lag,new_minraise,new_rules,new_trapper}/bot.py`.
- Regression-only: `panav-bots/opponents/lakshya1.py` (already analysed; never tune on it; just make sure we do not get worse).
- A batch's bots are "dev" for that batch. Bots in LATER batches are the "forward holdout" (never opened until their batch).

## Tools (repo root; run `panav-bots/loop/setup.sh` first)
- Match: `PYTHONPATH=. .venv/bin/python panav-bots/loop/tools/file_duel.py A.py B.py --seeds 20 --hands 200 --processes 3 --logdir DIR --out DIR/sum.json`
  (duplicate deals, seats swapped, real protocol; A is the logged bot; prints chips/hand +- SE, match score). 200 hands = a Stage 1 leg.
  Same `--first-seed` => same deals, so base-vs-candidate deltas are paired. final's solver is wall-clock driven, so runs are not bit-identical.
  Use at most 3 processes (4 cores); never run two heavy things at once.
- Leaks: `.venv/bin/python panav-bots/loop/tools/leak_report.py DIR` (chips by how hands end, seat, size; the opponent's bet/fold rates).
- Edit the bot: `bundle_tool.py unpack panav-bots/final/bot.py WORK` -> edit `WORK/src/botsrc.*.py` and `WORK/config.json` (`exploit` lists
  the moves that are on) -> `bundle_tool.py pack panav-bots/final/bot.py WORK NEW.py`. Round-trip of an unedited unpack is byte-identical.
  The exploit layer is `botsrc.exploit` (traits learned per leg by SPRT + moves that shift action distributions; see its docstring),
  gates in `botsrc.hooks`, decisions in `botsrc.policy`. Never touch the strategy blob. Stdlib + numpy only; every reply legal; speed:
  mean reply <= 20 ms, worst <= 80 ms; no file/network access; no prints to stdout.

## What counts as a leak
A **leak** = a decision class where final loses chips against an opponent AND a different action would win more AND the alternative is
a **general principle**. Examples of general: "fold less / call more when the opponent's bet frequency is far above value-density",
"bet bigger for value vs a station", "stop bluffing a station". Not general: anything keyed to one bot's name, one seed, one
exact bet size seen in one match, hard-coded card/board lists. A leak needs: n >= 30 occurrences in the logs, a chip total, and a mechanism.
General means it should hold for any opponent whose observed behaviour (trait) matches; gate it on a within-leg trait (SPRT) so it
turns on only when the opponent shows it, and is OFF against a balanced opponent.

## The Phil Ivey test (required for every candidate fix, written down)
Write 3-5 sentences as Phil Ivey, heads-up expert, would say them: "Is this how a great player adjusts to an opponent that does X? Would it
still be right against a good opponent who started doing Y (i.e. can it be exploited back, and how badly)?" Verdict one of
PRINCIPLE (ship if numbers agree) / SITUATIONAL (only behind the trait gate) / OVERFIT (reject). A fix that has a clean principle but fails
the numbers is rejected; a fix that passes the numbers but has no principle is rejected.

## Roles in one batch k (bots B_k)
1. DIAG x5 (one session per bot): play final vs bot (30 pairs x 200 hands, logs), run leak_report, find leaks in the table above, list <= 4
   candidates with n, chips, mechanism, general-or-specific, proposed move (one sentence), Ivey verdict. NO bot edits. Write
   `panav-bots/loop/reports/b<k>_diag_<bot>.md` (<= 60 lines), commit, push to branch `loop/b<k>-diag-<bot>`.
2. INTEGRATE x1: read the 5 diag reports; keep leaks seen against >= 2 bots, or with PRINCIPLE verdict and strong mechanism; implement as moves
   gated by traits (default OFF in CONFIG unless they pass); unit-test legality/fuzz; build `cand_b<k>.py`.
   Dev check on the batch bots (>= 20 pairs each, same seeds as base). Then the OVERFIT CHECK (below). Report + candidate on branch `loop/b<k>-cand`.
3. OVERFIT CHECK (after every batch of 5): for each bot in {forward-holdout bots (later batches), old pool, lakshya1 (regression only)}
   run base final and candidate on the same seeds (>= 16 pairs x 200 hands each; for the old pool 12 pairs is enough), compute per-bot paired delta cand-base
   and the pooled sum with SE, plus the head-to-head cand vs base (16 pairs: must not lose). PASS = dev improved (pooled) AND holdout pooled
   delta >= 0 AND no holdout bot down by > 2 SE AND head-to-head not worse AND time limits OK AND zero forfeits/illegal replies.
   Dev up but holdout flat/down => OVERFIT: shrink, gate harder, or revert that move and say so.
   After the last batch there is no forward holdout: use the old pool + a fresh-seed rerun on all 20 bots + 500-hand legs against 3 bots.

## Rules for every session
- Never open a bot's source of a LATER batch's bots before its batch (it would leak into the design). Never copy another bot's code into final.
- Match budget is limited; do not run more than the planned matches. Never hang a command: use `timeout`.
- Be honest: report the numbers with their SE, say when something is noise. Do not claim wins the interval does not support.
- Final message <= 200 words: files, branch, numbers, verdicts. Details belong in the report files.
- git: commit only your report/candidate files (and edited sources under `panav-bots/loop/`), push with `git push -u origin <branch>`; never push to `panav-bots-12nov` or main.

# panav-bots (pushed 12 Nov 2026, branch panav-bots-12nov)

Everything from the owner's pokerbot repo that plays, in one additive folder. Nothing outside `panav-bots/` was touched.

- `final/`: the best bot, "final" = panav 2 (`bot.py` is dist/bot.py, git b2d350f; `final.py`/`final.zip` are the tagged copy).
- `eval_bots/spar/` (10 rule-based sparring bots) and `eval_bots/strong/` (10 strong bots) = the 20 new bots; `eval_bots/spar_v4/` = ten improved sparring variants.
- `eval_bots/*.py`: every built variation of the bot (B-*, F-*, X-*, S*, a2-*, fm-*, pilot-*, panav-seeded) and the 12 Nov candidates
  `panav3_overbetdef.py`, `panav4_D.py`, `panav4_B.py`, `panav4_DB.py`, `panav5_lk.py` (overfitted to lakshya1).
- `eval_bots/oracle_lk.py`: EVAL ONLY, cheats on purpose (reads the deal from the match seed). Never ship.
- `src_changes/`: botsrc/exploit.py with the new moves (overbetdef, foldbet, lkprior; all off by default), tools/build_bot.py, the tests,
  the lakshya1 report script and the analysis (lakshya1_analysis_12nov.md).

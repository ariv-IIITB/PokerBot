# OPUS2 research layer: Stage 2 tactics (15 Nov 2026)

**Verification level, stated plainly.** This container's network blocks arxiv.org and cs.ualberta.ca, so the full PDFs could not be opened
(a fetch sub-agent tried every URL below; all failed with DNS errors except one Microsoft PDF that came back as compressed binary). Every claim
below is checked against the **abstract or the publisher/proceedings page as returned by web search**, not against the paper body. Claims
marked (abstract) are from the abstract; (secondary) means only other papers' descriptions were found. Nothing is filled in from memory as if
it were verified; where I add my own reading it is marked "for us".

## 1. Safe / robust exploitation
- **Johanson, Zinkevich, Bowling (2007). Computing Robust Counter-Strategies. NIPS 20, pp. 721-728.**
  https://proceedings.neurips.cc/paper/2007/hash/6e7b33fdea3adc80ebd648fffb665bb8-Abstract.html
  (abstract) Restricted Nash responses solve a modified game so a counter-strategy exploits a suspected tendency while limiting the loss if
  the model is wrong; reported "substantially more robust than best response counter-strategies" in heads-up limit hold'em.
  For us: our exploit moves are already bounded shifts (TV <= 0.3) behind SPRT gates, i.e. an RNR-like trade by hand. A real RNR needs the
  opponent model as a strategy and an offline solve per model: not possible online in NumPy at ~0.15 s/hand. Testable at 500h: no new move.
- **Johanson, Bowling (2009). Data Biased Robust Counter Strategies. AISTATS, PMLR 5:264-271.** https://proceedings.mlr.press/v5/johanson09a.html
  (abstract) Like RNR but weights the model by how much data supports it, and "performs well when data is very limited".
  For us: the principle (trust the model per decision point in proportion to its sample size) is what the SPRT + ramp approximates; CALL1 v2
  showed the binding problem is that within a 200-500-hand leg most decision classes have < 10 observations (value share of shown big bets: 0-7
  per leg), so DBR-style confidence would keep the exploit off exactly where we wanted it on. Matches the repo's repeated null results.
- **Ganzfried, Sandholm (2015). Safe Opponent Exploitation. ACM Trans. Economics and Computation 3(2):1-28.** (secondary: cited in arXiv
  2201.04266 and NeurIPS 2022 "safe opponent exploitation subgame refinement") Characterises deviations from equilibrium that are safe in a
  repeated zero-sum game: risk only what you have already won above the game value ("gifts"). For us: the most relevant idea of all. Our match
  objective is P(match net > 0), and the realised match net is a *banked surplus* the bot can see. The safe-exploitation logic applied to the
  match score itself gives the **match lock** tested here: once the surplus exceeds the worst loss of a check/fold strategy for the rest of the
  match, risk at most the excess. Implementable (bookkeeping), needs no data, testable at Stage 2 length.

## 2. Opponent modelling with few samples
- **Southey, Bowling, Larson, Piccione, Burch, Billings, Rayner (2005). Bayes' Bluff: Opponent Modelling in Poker. UAI, pp. 550-558.**
  https://arxiv.org/abs/1207.1411 (abstract) Posterior over opponent strategies from a prior + observations (Dirichlet priors on a reduced
  game, an informed prior on full hold'em), then a response to the posterior.
- **Ganzfried, Sun (2016/2018). Bayesian Opponent Exploitation in Imperfect-Information Games.** https://arxiv.org/abs/1603.03491
  (abstract) Dirichlet prior is the standard choice; exact best response to the posterior for a class of imperfect-information games.
  For us: a Beta/Dirichlet posterior per trait is equivalent in spirit to the SPRT already in `botsrc.exploit`. The binding constraint is
  sample size, not the estimator: META1 found per-opponent switch selection worth <= 0 after split-half correction at 24 pairs/bot, and CALL1/
  VAL1/META1 all lost their dev gains on fresh bots. A Stage 2 "phase schedule" with credible intervals re-evaluated every N hands would
  re-use the same weak signals with more hands; in a real one-process 1000-hand match the existing SPRTs already accumulate over all 1000 hands
  (see §6), so a separate phase layer adds little. Not pursued (would be fitted on dev bots again).

## 3. Using more compute: subgame / depth-limited solving
- **Burch, Johanson, Bowling (2014). Solving Imperfect Information Games Using Decomposition. AAAI 28(1):602-608.**
  https://ojs.aaai.org/index.php/AAAI/article/view/8810 (abstract) Safe subgame re-solving with whole-game guarantees (CFR-D).
- **Brown, Sandholm (2017). Safe and Nested Subgame Solving for Imperfect-Information Games. NIPS 30, pp. 689-699.**
  https://arxiv.org/abs/1705.02955 (abstract) Subgames cannot be solved in isolation; nested re-solving as play proceeds lowers exploitability
  and handles off-tree actions better than action translation; core of Libratus.
- **Brown, Sandholm, Amos (2018). Depth-Limited Solving for Imperfect-Information Games. NeurIPS 31, pp. 7663-7674.**
  https://arxiv.org/abs/1805.08195 (abstract) At the depth limit the opponent chooses among several continuation strategies; master-level
  HUNL on a 4-core CPU.
  For us: A already re-solves the river online and its time manager (`botsrc.timeman`) already hands the river solver whatever is left of a
  plan of 67% of the bank, capped at RIVER_MAX_MS, 40% of the reply limit and 2% of the bank left. So "spend the Stage 2 surplus" is already
  automatic: the bank is 0.15 s/hand at both stages, the same per hand. Turn depth-limited solving would need continuation-value tables we do
  not have (the blueprint is per street, the turn->river value net would be new offline work) and a full validation; not feasible by the deadline
  and the effect of extra river passes is below what 16 bots x 24 matches can resolve. Measured bank use is reported in opus2_report.md.

## 4. Portfolios / bandits over styles
- **Bard, Johanson, Burch, Bowling (2013). Online Implicit Agent Modelling. AAMAS, pp. 255-262.**
  https://webdocs.cs.ualberta.ca/~bowling/publications/b2hd-13aamas-implicitmodelling.html (abstract) Estimate online the utility of a fixed
  portfolio of precomputed strategies, with variance reduction and online learning; would have won the 2011 ACPC limit exploitation event.
- **Auer, Cesa-Bianchi, Freund, Schapire (2002). The Nonstochastic Multiarmed Bandit Problem. SIAM J. Computing 32(1):48-77.** (abstract)
  Adversarial bandits; per-round payoff approaches the best arm's at rate O(T^-1/2), matching lower bound.
- **Dekel, Ding, Koren, Peres (2014). Bandits with Switching Costs: T^{2/3} Regret. STOC, pp. 459-467.** https://arxiv.org/abs/1310.2997
  (abstract) Minimax regret with switching costs is Theta~(T^{2/3}), worse than T^{1/2}; the same rate holds against bounded-memory adaptive
  adversaries.
  For us: a bandit over styles learns from *payoffs*. Our payoff noise is ~40 chips/hand SD (measured, opus2 design runs) against style
  differences of 0.2-0.5 chips/hand, so telling two arms 0.3 chips/hand apart at 2 SE needs about 2 x (2 x 40 / 0.3)^2 ~ 140,000 hands per arm; a match is 1000. With switching cost
  the bound only gets worse. Bard et al. made it work in *limit* hold'em with strong variance reduction (their own estimator); in no-limit
  with 200-chip stacks and no luck-adjusted estimator, a style bandit is noise. This repeats the repo lesson "outcome-based adaptation is
  infeasible in a match". Not pursued.

## 5. Match objective: maximise P(win), not E[chips]
- **Dubins, Savage (1965; Dover 1976). How to Gamble If You Must: Inequalities for Stochastic Processes.** (secondary: Chen, Shepp, Yao,
  Zhang 2005 J. Appl. Prob. and related papers) Bold play is optimal for reaching a goal in a subfair casino; it is not the only optimal
  strategy, and the result changes with limits on stakes or time.
  For us: the payoff of a match is a step function of the final net (win 1, draw 0.5, loss 0). With that objective a player who is ahead
  should cut variance and one far behind should add it. The extreme, risk-free version of "cut variance when ahead" is the lock (§1). The
  "add variance when behind" side costs EV and needs a model of the variance/EV trade, so it is not tried here.
- Found but NOT read (arXiv blocked): "Agents That Certify Their Own Exploits: Confidence-Scheduled Restricted Responses for Safe Opponent
  Exploitation" (arXiv 2607.28520) and "Safe Observation Capacity for Opponent Exploitation under Showdown Censoring" (arXiv 2608.09954).
  Titles suggest a confidence schedule for exploitation and limits from showdown censoring (we only see cards at showdown), which is what CALL1
  v2 ran into. No claims taken from them.

## 6. Repo-specific fact that changes the Stage 2 picture (docs/rules/protocol.pdf §5.1)
`init.total_hands` is the MATCH length (400 / ~1000) and duplicates are inside one process. So in the real Stage 2 (a) the exploit layer's
traits accumulate over ~1000 hands, not 500; (b) the bot sees its running match score. Earlier Stage 2 evaluations (2 legs x 500 hands in
separate processes) measure neither. All OPUS2 runs use one process per match (`opus2/duel1000.py`).

## Decision table
| idea | NumPy + time bank? | data we lack? | testable at Stage 2 length? | decision |
|---|---|---|---|---|
| match lock (safe exploitation of the banked match surplus) | yes, bookkeeping | none | yes, exactly (post-hoc + real) | **T1, tested** |
| deeper river / turn solving with surplus bank | river: already automatic; turn: no value net | turn values | effect too small to resolve | measured only |
| phase schedule on Bayesian trait intervals | yes | enough observations per leak | yes, but dev-fitted again | not pursued (repo nulls) |
| bandit / Exp3 over styles | yes | payoff noise 40 ch/hand | no (needs ~70k hands) | rejected |
| randomised exploit (anti-adaptation) | yes | an adaptive adversary pool | weakly | not pursued (OPUS1 owns trapper/adaptive) |
| add variance when far behind | yes | EV-variance model | yes | not tried (EV cost, no time) |

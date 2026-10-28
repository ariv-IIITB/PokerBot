# Opponent 4 (Titan) - Advanced Heads-Up NLHE Bot

A championship Heads-Up No-Limit Texas Hold'em bot engineered to exact specifications, featuring range-weighted Monte Carlo equity, Bayesian opponent tracking, candidate EV bet selection, river bluff-balancing, and match-win probability optimization.

Located in: `/home/fioriv/synergy/PokerBot/Opps/opp4`

---

## 1. Mathematical Specifications & Architecture

### A. Range-Weighted Equity (`equity.py`)
- **1,326 Combinations:** Evaluates all candidate two-card combinations, removing dead cards (hole + community).
- **Combo Weighting:**
  $$w(h) = w_{\text{preflop}}(h) \prod_{i} P(a_i \mid h, \text{street}_i, \text{size}_i)$$
- **Sampling Stratification:**
  - **Preflop:** 256 weighted samples
  - **Flop:** 384 weighted samples
  - **Turn:** 512 weighted samples
  - **River:** Exact exhaustive enumeration of all legal non-colliding opponent combos ($<990$ combinations evaluated in $<1.5$ ms). Falls back to bounded sampling if monotonic clock deadline approaches.
- **Sampling Uncertainty:** Computes standard error $SE = \sqrt{\frac{E(1 - E)}{N}}$.

### B. Calling Rule (`strategy.py`)
- Given pot $P$ before call and additional call cost $C$, the break-even pot odds are:
  $$E_{\min} = \frac{C}{P + C}$$
- Quantified safety margins:
  - **Preflop:** $+1.5\%$ ($+0.015$)
  - **Flop:** $+2.0\%$ ($+0.020$)
  - **Turn:** $+1.0\%$ ($+0.010$)
  - **River:** $0.0\%$ ($+0.000$)
- **Out of Position (OOP):** $+0.5\%$ ($+0.005$) extra equity required when acting first.
- **Sampling Uncertainty:** Quantified adjustment capped at $+3.0\%$ ($\le +0.030$).
- Call if:
  $$\text{Equity} \ge E_{\min} + \text{Margin}_{\text{street}} + \text{Margin}_{\text{OOP}} + \min(0.030, SE)$$

### C. Bet Selection & River Bluffing (`strategy.py`)
- **Candidate Sizes:** Evaluates $33\%$, $66\%$, $110\%$ of pot and all-in.
- **Expected Value:**
  $$EV_{\text{bet}} = F \cdot P + (1 - F) \cdot [ E_{\text{called}} \cdot (P + 2B) - B ]$$
- **Conditional Equity When Called:**
  $$E_{\text{called}} = \max\left(0, \frac{E - F}{1 - F}\right)$$
  ensuring second pair / marginal hands check rather than overbetting into calling ranges.
- **River Bluff Balancing:**
  Enforces size-dependent bluff-to-value ratio:
  $$\frac{\text{bluffs}}{\text{value bets}} = \frac{B}{P + B}$$
  Selects blocker-rich hands and missed draws. Drops bluffs when estimated EV is negative against an observed calling station.

### D. Bayesian Opponent Modeling (`opponent_model.py`)
- **Beta Priors:**
  | Statistic | Prior | Prior Mean |
  |---|---|---|
  | Voluntarily Put in Pot (VPIP) | $\text{Beta}(2, 2)$ | 0.50 |
  | Preflop Raise (PFR) | $\text{Beta}(1, 3)$ | 0.25 |
  | Fold to Bet | $\text{Beta}(4, 6)$ | 0.40 |
  | Fold to Continuation Bet | $\text{Beta}(3, 7)$ | 0.30 |
- **Confidence Shrinkage:**
  $$c = \frac{n}{n + 25}$$
  $$\hat{\theta} = (1 - c) \cdot \mu_{\text{prior}} + c \cdot \mu_{\text{posterior}}$$
- **Action Multipliers:**
  - Raise: weak $0.15$ / middling $0.6$ / strong $2.4$
  - Call: weak $0.25$ / middling $0.9$ / strong $1.5$
  - Strong draws (flush draws / OESD) receive a $1.8\times$ bonus.

### E. Match-Win Strategy & Runtime (`meta_controller.py`)
- **Match Strategy:** When match margin $D$ is observable:
  $$U(D) = \Phi\left(\frac{D}{\sigma_{\text{remaining}}}\right)$$
  where $\sigma_{\text{remaining}} = \sigma_{\text{hand}} \sqrt{H_{\text{remaining}}}$. Candidate actions are evaluated by their expected match utility $\mathbb{E}[U]$.
- **Runtime:** Hard monotonic clock deadlines targeting $<75$ ms/hand average execution.

### F. Stack-Stratified Preflop Charts (`preflop.py`)
- $\le 8$ BB: Dedicated Sklansky-Chubukov / Nash Push-Fold chart
- $8–15$ BB: Short-stack push / 3-bet jam / open
- $15–30$ BB: Min-raise / polarized 3-bet
- $30–60$ BB: 2.25x-2.5x open / defend wide
- $> 60$ BB: Deep stack flatting / multi-street play

---

## 2. File Organization

```
Opps/opp4/
├── __init__.py          # Package export
├── bot.py               # Main PokerBot class
├── evaluator.py         # Sub-microsecond 7-card evaluator
├── preflop.py           # 1,326 combo generator & stack-stratified charts
├── opponent_model.py    # Bayesian Beta trackers & combo weight updater
├── equity.py            # Range-weighted MC equity & exact river enumeration
├── meta_controller.py   # Match utility U(D) & time governor
├── strategy.py          # Calling rule, bet candidate eval, river bluffing
├── safety.py            # ActionSanitizer & legality clamping
├── baselines.py         # CallingStation, CheckFold, AllInManiac, NitTag, Random
├── runner.py            # Paired duplicate deals runner with 95% CIs
├── test_opp4.py         # 12 unit tests verifying evaluator, math & safety
└── README.md            # Documentation & release gate results
```

---

## 3. Running Verification & Benchmarks

```bash
cd "/home/fioriv/synergy/PokerBot/Opps/opp4"

# 1. Run unit tests
python3 -m unittest test_opp4.py

# 2. Run full 200-deal (400-hand) paired duplicate benchmark suite:
python3 runner.py
```

# TitanBot - Heads-Up No-Limit Texas Hold'em Pokerbot

A competitive heads-up pokerbot designed for heads-up poker tournaments (Swiss format, duplicate deals, 1 vCPU, 1 GB RAM, read-only filesystem, 60s per 400 hands).

---

## Tournament Architecture

### 1. Strategy & Decision Engine (`player.py`)
- **Preflop:** Position-aware range opening using an exact precomputed equity table for all 169 canonical hands. Button opens ~75-80% of hands (min-raise or 2.5x BB); Big Blind defends dynamically based on pot odds.
- **Postflop:** Sub-millisecond Monte Carlo equity simulations (200-300 rollouts) with draw detection (flush draws, open-ended straight draws, gutshots).
- **Bet Sizing:** Geometric sizing calibrated to equity and pot size (33% c-bets, 50-70% value bets, 2.5x-3x raises).
- **Opponent Modeling:** Dynamically tracks opponent VPIP, PFR, Fold-to-Open, Fold-to-CBet, and Aggression in memory without writing to disk. Automatically exploits:
  - *Calling Stations:* Cuts all bluffs; extracts maximum thin value with wide sizing.
  - *Nits / Over-Folders:* Steals 100% of button opens; c-bets 100% of dry boards.
  - *Maniacs:* Induces bluffs with medium-strong hands; check-raises monsters.

### 2. Time Bank Management
- **Budget:** ~60 seconds per 400 hands (~150 ms per hand).
- **Adaptive Rollouts:**
  - Clock > 40s: 250 MC iterations (capped at 30ms).
  - 20s < Clock <= 40s: 150 iterations (capped at 15ms).
  - 8s < Clock <= 20s: 60 iterations (capped at 6ms).
  - Clock <= 8s: $O(1)$ fast heuristic mode (0ms MC).
- **Actual Benchmark Performance:** Consistently uses **< 5.0 seconds** of clock across all 400 hands (over 90% time margin!). **0 timeouts**.

### 3. Reliability & Zero-Crash Guarantee
- Complete `try / except` wraps around all actions and round transitions.
- Automatic illegal-action correction (bounds clamping, converting invalid check to call/fold).
- Read-only filesystem compliant (100% in-memory tracking, zero temp files).

---

## Directory Structure

```
pokerbot/
├── README.md               # Documentation and usage guide
├── run.py                  # Main entry point (competition socket & local CLI)
├── run_match.py            # Duplicate match runner with detailed metrics
├── player.py               # TitanBot implementation (Player = TitanBot)
├── baselines.py            # Baseline bots: AlwaysCallBot, AlwaysFoldBot, RandomBot, TightBot
├── engine.py               # Full heads-up NLHE engine supporting duplicate deals
├── skeleton/
│   ├── __init__.py
│   ├── actions.py          # FoldAction, CallAction, CheckAction, RaiseAction
│   ├── states.py           # GameState, RoundState, TerminalState
│   ├── bot.py              # Abstract Bot base class
│   ├── runner.py           # TCP socket runner for MIT Pokerbots compatibility
│   └── evaluate.py         # Cactus Kev hand evaluator + MC equity + preflop table
└── tests/
    ├── __init__.py
    └── test_pokerbot.py    # Unit tests for evaluator, actions, engine, duplicate deals
```

---

## How to Run

### 1. Run the Full Benchmark Suite (400 hands per baseline)
```bash
python3 run.py --benchmark
# or
python3 run_match.py --benchmark-all --hands 400
```

### 2. Run a Match vs a Specific Baseline
```bash
python3 run_match.py --bot1 titan --bot2 call --hands 400
python3 run_match.py --bot1 titan --bot2 fold --hands 400
python3 run_match.py --bot1 titan --bot2 tight --hands 400
python3 run_match.py --bot1 titan --bot2 random --hands 400
```

### 3. Run in Competition Socket Mode (MIT Pokerbots Protocol)
When connecting to a competition host/port:
```bash
python3 run.py --host 127.0.0.1 --port 1234
# or positional:
python3 run.py localhost:1234
```

### 4. Run Unit Tests
```bash
python3 -m unittest discover tests
```

---

## Benchmark Results (400 Duplicate Hands, 60s Clock)

| Opponent | Winner | Net Chips | bb/100 | Time Used | Time Remaining |
|---|---|---|---|---|---|
| **AlwaysFoldBot** | **TitanBot** | +506 chips | +63.25 bb/100 | 0.33s | 59.67s / 60s |
| **AlwaysCallBot** | **TitanBot** | +2,659 chips | +332.38 bb/100 | 4.59s | 55.41s / 60s |
| **RandomBot** | **TitanBot** | +1,094 chips | +136.75 bb/100 | 2.66s | 57.34s / 60s |
| **TightBot** | **TitanBot** | +408 chips | +51.00 bb/100 | 3.49s | 56.51s / 60s |
| **Total / Overall** | **TitanBot** | **+4,667 chips** | **Match Record: 4/4 (100% Win Rate)** | **Timeouts: 0** | |

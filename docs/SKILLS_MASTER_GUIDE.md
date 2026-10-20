# PokerBot Skills Master Reference Guide

Every skill and agent installed in your `PokerBot` environment, categorized by lifecycle phase, invocation mode, and exact usage instructions.

---

## 🟢 Category 1: Auto Invocations (Cheap / Silent Background Guards)
These skills **do not** require slash commands. They run automatically during conversation and code edits without eating up large token budgets.

| Skill | Mode | What It Does | When It Triggers / When to Rely On It |
|---|---|---|---|
| **`python-patterns`** | Auto | Enforces idiomatic Python 3.11, PEP 8 standards, and strict NumPy/SciPy practices. | Every time Claude writes or edits bot logic. Prevents hallucinating unauthorized libraries outside NumPy/SciPy. |
| **`python-testing`** | Auto | Standardizes `pytest` fixtures, parametrized tests, and unit testing conventions. | Active whenever writing tests for the hand evaluator or match runner. |
| **`coding-standards`** | Auto | Enforces clean naming, function modularity, and readable structure. | Active during every coding turn. |
| **`search-first`** | Auto | Tells Claude to check existing files, helpers, and utilities before writing new duplicate code. | Active before implementing any new function. |
| **`diagnosing-bugs`** | Auto | Structured debugging protocol: reproduce $\to$ minimize $\to$ hypothesize $\to$ instrument $\to$ fix. | Triggers automatically whenever you say "debug this", paste an exception trace, or report an unexpected card result. |
| **`codebase-design`** | Auto | Vocabulary for deep modules and interface boundaries (seams). | Active when designing or refactoring module boundaries (e.g., game state vs. strategy lookup). |
| **`ponytail`** | Auto (`lite`) | Aggressively suppresses boilerplate, complex class hierarchies, and bloat. | Runs on every turn via the active UI widget to keep code concise. |

---

## 🔴 Category 2: Manual Invocations (`disable-model-invocation: true`)
These skills **never** run unprompted. They are high-power, high-context tools that you trigger deliberately using slash commands.

### A. Strategy, Architecture & Design Grilling
Use these at the start of a feature or big architectural pivot.

| Skill | Command | What It Does | When to Use for Pokerbots |
|---|---|---|---|
| **`grill-me`** | `/grill-me` | Relentlessly interviews you with multi-round questions to stress-test an idea before coding. | **Day 1 / Big Decisions:** Run when deciding table precomputations vs. real-time lookups or hand-abstraction buckets. |
| **`grill-with-docs`** | `/grill-with-docs` | Runs `/grill-me` and simultaneously writes architectural decision records (`docs/adr/`) and a `GLOSSARY.md`. | Use when agreeing on domain terms with your teammate (e.g., card representations, pot odds formulas). |
| **`codebase-design`** | `/codebase-design` | Deep-module design inspection. | When deciding where to place the seam between the stdin/stdout parser and the decision engine. |
| **`ask-matt`** | `/ask-matt` | Skill router that suggests which skill fits your current problem. | Whenever you're unsure which tool to use. |

### B. Test-Driven Development (TDD)
Use strictly for core deterministic modules (hand evaluator, pot calculator, duplicate deal runner).

| Skill | Command | What It Does | When to Use for Pokerbots |
|---|---|---|---|
| **`tdd`** (Pocock) | `/tdd` | Strict red-green-refactor loop: writes failing test first, minimal pass, then refactors. | **Mandatory** for the 7-card evaluator and the duplicate-deal match runner. |
| **`tdd-workflow`** (ECC) | `/tdd-workflow` | Evidence-based TDD loop that demands test output proofs before proceeding. | Alternative to `/tdd` if you want rigid step-by-step verification logs. |

### C. Performance, Latency & Fitting (The ~0.15s / 1 GB Crunch)
Use these once the bot functions correctly and you need to optimize for competition rules.

| Skill | Command | What It Does | When to Use for Pokerbots |
|---|---|---|---|
| **`benchmark-optimization-loop`** | `/benchmark-optimization-loop` | Bounded speedup loop: takes baseline measurement, tries single-variable code variants, verifies correctness, and keeps the fastest safe version. | **Essential:** Use when per-hand decision time exceeds 0.10s–0.12s or when table lookup speed needs tuning. |
| **`latency-critical-systems`** | `/latency-critical-systems` | Hard telemetry discipline: forbids unmeasured latency claims and tracks p50/p95/p99 times. | Use when benchmarking response latency across 400 hands to ensure the time bank never exhausts. |
| **`strategic-compact`** | `/strategic-compact` | Proactively compacts conversation context while retaining crucial architectural state. | Call during long marathon coding sessions when token counts get high. |

### D. Audits, Code Quality & Pre-Submission Reviews
Use these before committing big PRs or freezing the bot for submission.

| Skill | Command | What It Does | When to Use for Pokerbots |
|---|---|---|---|
| **`improve`** (`shadcn/improve`) | `/improve quick` or `/improve branch` | Comprehensive read-only audit. Produces prioritized action plans without editing source code. | Run `/improve quick` weekly, and `/improve branch` before merging any major branch. |
| **`thermo-nuclear-code-quality-review`** | `/thermo-nuclear-code-quality-review` | Extreme zero-tolerance maintainability review. Flags giant files, spaghetti conditionals, and abstraction leaks. | Run once before the Nov 15 freeze day to ensure the codebase is clean and robust. |
| **`code-review`** | `/code-review` | Compares git diff along two axes: spec compliance and repository coding standards. | Run on diffs before submitting pull requests. |
| **`improve-codebase-architecture`** | `/improve-codebase-architecture` | Analyzes code structure and outputs an interactive HTML friction report. | Optional post-build cleanup. |
| **`verification-loop`** | `/verification-loop` | Runs standing done-checks (tests + benchmarks + linting). | Final sanity check before committing. |
| **`eval-harness`** | `/eval-harness` | Verification evaluation loop. | Optional verification framework. |
| **`santa-method`** | `/santa-method` | Two independent reviewer agents must both approve output before shipping. | High-token cost: Run only once right before final submission on Nov 15. |
| **`handoff`** | `/handoff` | Dumps current session state, remaining tasks, and context into a handoff file. | Run at the end of every work session so your teammate or next session can pick up immediately. |
| **`git-guardrails-claude-code`** | `/git-guardrails-claude-code` | Hooks that block dangerous git commands (`git push --force`, `reset --hard`, `clean`). | One-time setup to protect git history. |

---

## 🤖 Category 3: Scoped Subagents (`.claude/agents/`)
Subagents run in their own isolated context. You invoke them by name (e.g. *"Use the silent-failure-hunter agent to check bot/decision.py"*).

| Subagent | Role & Specialty | When to Dispatch |
|---|---|---|
| **`performance-optimizer`** | **Critical.** Profiles bottlenecks, memory leaks, algorithmic complexity, and cache locality. | Use to ensure RAM stays under 1 GB and per-hand time stays under 0.15s. |
| **`silent-failure-hunter`** | **Critical.** Audits code for swallowed errors, blank `except:` blocks, dangerous fallbacks, and missing return values. | **Pre-submission must:** A bot crash or unhandled exception forfeits the match. |
| **`planner`** | High-level feature roadmap planner. | Before starting major subsystems (e.g., preflop ranges vs. postflop heuristic solver). |
| **`architect`** | System design decision specialist. | When restructuring data models or storage formats for offline tables. |
| **`tdd-guide`** | Guides step-by-step test-first cycles. | When pairing on complex test setups for duplicate deals. |
| **`code-reviewer`** | Security and quality diff reviewer. | Pre-merge branch review. |
| **`python-reviewer`** | Specialized Python 3.11 static analysis reviewer. | Verifying pure Python/NumPy conformity inside `bot/`. |
| **`refactor-cleaner`** | Dead code and unused import remover. | During final cleanup before submission. |
| **`loop-operator`** | Autonomous loop runner. | Use sparingly only for bounded repetitive tasks. |

---

## 📅 Suggested Workflow Timeline (Deadline: Nov 15)

```text
Week 1 (Oct 21 - Oct 27): Architecture & Foundations
  ├── Run `/grill-me` on precomputed lookup tables vs online decision algorithm
  ├── Use `/tdd` to write hand evaluator and duplicate-deal match runner
  └── Verify with `python-testing` and `python-patterns`

Week 2 (Oct 28 - Nov 05): Strategy & Baseline Opponents
  ├── Build offline training scripts in `tools/`
  ├── Generate compact numpy tables in `bot/`
  └── Test against simple baselines in `opponents/`

Week 3 (Nov 06 - Nov 12): Fitting to Competition Limits
  ├── Dispatch `performance-optimizer` agent (1 GB RAM & 0.15s wall-clock)
  ├── Run `/benchmark-optimization-loop` on decision path
  └── Keep `ponytail` on `lite` (or click `Review` to trim bloat)

Final Days (Nov 13 - Nov 15): Zero-Crash Audit & Submission Freeze
  ├── Dispatch `silent-failure-hunter` agent (wrap every path to prevent forfeits)
  ├── Run `/improve branch` and `/thermo-nuclear-code-quality-review`
  └── Create final freeze commit
```

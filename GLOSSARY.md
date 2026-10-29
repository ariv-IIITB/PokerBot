# Glossary

Domain terms used in the code and docs. Keep entries short; link the module that owns each one.

**Variant spec**: the JSON description of a poker variant (`variant/spec.py`, presets in
`variant/catalog/`, the played one in `variant/active.json`). The only variant format; it compiles
into **Rules** (`bot/game/compile.py`). `holdem_rules()` is the default where none is given.

**Rules**: a compiled variant: the hand program (a tuple of step plugins) plus its numbers
(`bot/game/rules_spec.py`).

**Hand program**: the ordered steps of one hand (blinds, deals, betting rounds, discard, showdown).

**Event**: something that happened in a hand, emitted by a step with a visibility (`ALL` or one
player) (`bot/game/state.py`).

**Visibility rule**: `messages_for(event, viewer)` in `bot/game/observation.py`: the messages a
player receives for an event. The lab engine sends exactly these; the bot's replay aligns against
exactly these through `card_entry`.

**Hidden choice**: `bot.protocol.HIDDEN_CHOICE`: the opponent made a special choice the wire format
doesn't identify (pokerbots: which slot they discarded; the card arrives as a reveal).

**Reconstruction**: the current hand rebuilt inside `bot.game` from what we observed, with
placeholder tokens for unseen cards (`bot/sim/replay.py`).

**Situation**: everything about one decision that is not strategy: the reconstruction, equity,
the special-step policy and the endgame lock (`bot/situation.py`). **Perception** builds one per
decision. Brains are policies over it.

**Equity / share**: our expected fraction of the pot at showdown (1 win, 0.5 tie, hi-lo splits);
one showdown rule, `bot.equity.showdown_share`.

**Opponent**: everything learned about the opponent: frequency stats, the inference model, and the
trust in it (`bot/opponent.py`). Answers stats, sample weights and `range_weights` over explicit hands.

**Inference**: weighting the opponent's possible cards by how likely their visible choices were
(`bot/sim/inference.py`). **Trust**: how well that model explained past showdowns, in [0, 1].

**Endgame lock**: check/fold everything once the lead covers the worst case of the remaining
hands (`lock_margin`, `Situation.locked`).

**Artifact**: precomputed data embedded in `bot/embedded.py` (`ARTIFACTS`), built for one variant
spec (`bot/artifacts.py`). Today: `"tables"`; later a CFR blueprint.

**Abstraction**: the CFR view of the game: abstract actions, raise labels, hand buckets, betting
history and infoset key (`bot/abstraction.py`), shared by the trainer and the runtime.

**Tier 0 / 1 / 2 / 3 / 4**: brains: safe fallback / equity vs pot odds / + opponent adaptation and
lock (shipped) / the "Ivey" style (planned) / CFR hybrid (planned, `docs/CFR_PLAN.md`).

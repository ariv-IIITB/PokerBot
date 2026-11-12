r"""Patches for the shadow-tier3x builds after the first shadisc (used by build_variant.py).

Infrastructure ("shadow", applied once by any sh_* arm): the shadow reads every engine line before the final bot
handles it (so it is current at our decisions) and hears our actual reply right after it is sent. Features
(CONFIG "shadow", comma list), one arm each:
  sh_disc   tier3x chooses the discard
  sh_range  the river solver gets tier3x's opponent range (Opponent.range_weights) in place of the blueprint-tracked
            one; dead cards follow the final bot's own range support; the exploit hook still adjusts it after
  sh_types  each exploit trait's strength is max(its own SPRT strength, tier3x's X2 type-family confidence):
            station -> "station", prefold -> "nit", overfolder -> "overfolder", aggressor -> "aggressor"
            (only moves that are on in CONFIG "exploit" act on it)
Raw strings: every pattern is the module's source text exactly."""

INFRA = {
    "botsrc.main": [
        (r'''        self.hs = None
        self.startup_ms = now_ms() - t0
''',
         r'''        self.hs = None
        self.line = None
        self.shadow = None
        feats = [f for f in str(self.config.get("shadow") or "").split(",") if f]
        if feats:
            try:
                from . import shadow as SHM
                self.shadow = SHM.Shadow(feats)
                SHM.CURRENT = self.shadow
                log(f"shadow tier3x loaded in {self.shadow.startup_ms:.0f} ms, features {feats}")
            except Exception as e:
                log(f"shadow tier3x NOT LOADED ({type(e).__name__}: {e}): the final bot plays alone")
        self.startup_ms = now_ms() - t0
'''),
        (r'''    def handle(self, msg):
        t = msg.get("type")
        reply = None
''',
         r'''    def shadow_acted(self, msg, reply):
        """After our reply is out: the shadow records what we did."""
        sh = self.shadow
        if sh is not None and isinstance(reply, dict) and msg.get("type") in ("action_request", "discard_request"):
            sh.acted(reply)

    def handle(self, msg):
        t = msg.get("type")
        reply = None
        if self.shadow is not None and self.line is not None:
            self.shadow.pre(self.line)              # never raises; turns itself off on an error
'''),
        (r'''    def on_discard(self, req):
        t0 = now_ms()
        self.tm.observe(req)
        counted = self.stats.decisions["discard"]
        reply = None
        try:
            hs = self.hs
            if hs is None or req.get("hand_id") != hs.hand_id:
                raise ValueError("discard_request for an unknown hand")
            rep = replay(hs, hs.history_after)
            fagg = rep.fagg if rep.error is None else 0
            card, k = self.policy.decide_discard(hs, req, fagg, self.guard, self.stats)
''',
         r'''    def shadow_slot(self, hs, req, card):
        """The keep slot (the blueprint's later streets need it) for the shadow's discard card."""
        fi = self.policy.flop_info(hs, C.parse_cards(req["board"]))
        for k, pair in enumerate(fi["slots"]):
            if C.format_card(next(c for c in hs.hole3 if c not in pair)) == card:
                return card, k
        raise ValueError(f"no keep slot discards {card!r}")

    def on_discard(self, req):
        t0 = now_ms()
        self.tm.observe(req)
        counted = self.stats.decisions["discard"]
        reply = None
        sh_card = None
        if self.shadow is not None and "discard" in self.shadow.features:
            sh_card = self.shadow.discard_pending(req.get("hole_cards") or [])
        try:
            hs = self.hs
            if hs is None or req.get("hand_id") != hs.hand_id:
                raise ValueError("discard_request for an unknown hand")
            rep = replay(hs, hs.history_after)
            fagg = rep.fagg if rep.error is None else 0
            k = None
            if sh_card is not None:
                try:
                    card, k = self.shadow_slot(hs, req, sh_card)
                    self.stats.level("discard", "shadow")
                except Exception as e:
                    self.stats.error("shadow_slot", e)
            if k is None:
                card, k = self.policy.decide_discard(hs, req, fagg, self.guard, self.stats)
'''),
        (r'''        log(self.match_end_line())
''',
         r'''        if getattr(self, "shadow", None) is not None:
            try:
                log(self.shadow.summary())
            except Exception as e:
                log(f"shadow: summary failed ({type(e).__name__})")
        log(self.match_end_line())
'''),
        (r'''        try:
            reply = bot.handle(msg)
        except Exception:
            reply = bot.emergency(msg)
        if reply is not None:
            try:
                out.write(json.dumps(reply) + "\n")
                out.flush()
            except Exception:
                pass
''',
         r'''        bot.line = line
        try:
            reply = bot.handle(msg)
        except Exception:
            reply = bot.emergency(msg)
        if reply is not None:
            try:
                out.write(json.dumps(reply) + "\n")
                out.flush()
            except Exception:
                pass
        try:
            after = getattr(bot, "shadow_acted", None)
            if after is not None:
                after(msg, reply)
        except Exception:
            pass
'''),
    ],
}

FEATURES = {
    "sh_disc": ("discard", {}),
    "sh_range": ("range", {
        "botsrc.policy": [
            (r'''            ctx.my_range_now = self.our_range_now(hs, req, rep, board, rr, tm).copy()
''',
             r'''            ctx.my_range_now = self.our_range_now(hs, req, rep, board, rr, tm).copy()
            try:                                        # shadow tier3x: its opponent range model
                from . import shadow as SHM
                sh = SHM.CURRENT
                if sh is not None and "range" in sh.features:
                    t_sh = now_ms()
                    w = sh.river_range()
                    tm.note_range(now_ms() - t_sh)
                    if w is not None:
                        base = ctx.opp_range_now
                        w = np.asarray(w, dtype=np.float64) * (base > 0)
                        if w.shape == (1326,) and np.isfinite(w).all() and w.sum() > 0:
                            ctx.opp_range_now = w * (float(base.sum()) / float(w.sum()))
                            stats.river["shadow_range"] = stats.river.get("shadow_range", 0) + 1
                        else:
                            stats.river["shadow_range_empty"] = stats.river.get("shadow_range_empty", 0) + 1
            except Exception:
                stats.river["shadow_range_errors"] = stats.river.get("shadow_range_errors", 0) + 1
'''),
        ],
    }),
    "sh_types": ("types", {
        "botsrc.exploit": [
            (r'''    def strength(self, trait):
        return self.traits[trait].strength
''',
             r'''    def strength(self, trait):
        s = self.traits[trait].strength
        fam = X2_FAMILY.get(trait)
        if fam is not None:
            try:                                        # shadow tier3x: its X2 type posterior
                from . import shadow as SHM
                sh = SHM.CURRENT
                if sh is not None and "types" in sh.features:
                    x = float(sh.family_lambda(fam))
                    if x > s:
                        self.x2_used[trait] = self.x2_used.get(trait, 0) + 1
                        s = x
            except Exception:
                pass
        return s
'''),
            (r'''        self.on_hands = {k: 0 for k in TRAITS}   # hands that ended with the trait at "yes"
''',
             r'''        self.on_hands = {k: 0 for k in TRAITS}   # hands that ended with the trait at "yes"
        self.x2_used = {}               # trait -> calls where the shadow's type posterior set its strength
'''),
            (r'''BIG_RIVER = 0.7 ''',
             r'''X2_FAMILY = {"station": "station", "prefold": "nit", "overfolder": "overfolder", "aggressor": "aggressor"}
BIG_RIVER = 0.7 '''),
        ],
    }),
}

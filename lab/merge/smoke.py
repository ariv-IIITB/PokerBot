"""One leg of BOT vs OPP with BOT's stderr saved: python smoke.py BOT_DIR OPP_NAME SEED HANDS LOG"""
import sys
from lab.harness import load_variant, play_match
from lab.players import PlayerSpec, SubprocessPlayer
bot_dir, opp, seed, hands, logp = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
cfg = load_variant("discard_holdem")
spec = cfg.spec if hasattr(cfg, "spec") else None
me = SubprocessPlayer([sys.executable, "bot.py"], bot_dir, "me", stderr_to=logp, protocol="pokerbots",
                      variant_json=spec.to_json() if spec is not None else None)
other = PlayerSpec.brain(opp).build(cfg)
m = play_match([me, other], cfg, seed, hands, "fold", time_bank_s=30.0 * hands / 200)
print("chips", m.chips, "forfeit", m.forfeit, "errors", m.errors)

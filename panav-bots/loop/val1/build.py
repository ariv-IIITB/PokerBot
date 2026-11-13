"""Build a seeded final variant: build.py OUT.py [key=value ...]  (keys go into config.json; exploit+=valuebet via exploit=...)
Sources come from $VAL1_SRC (edited botsrc.exploit.py); template = evalbuilds/final_seeded.py."""
import json, os, subprocess, sys, tempfile, shutil
src = os.environ["VAL1_SRC"]            # directory holding the edited src/ (and config.json)
tpl = "panav-bots/loop/evalbuilds/final_seeded.py"
tool = "panav-bots/loop/tools/bundle_tool.py"
out = sys.argv[1]
w = tempfile.mkdtemp()
subprocess.run([sys.executable, tool, "unpack", tpl, w], check=True, capture_output=True)
for f in [x for x in os.listdir(src + "/src") if x.endswith(".py")]:
    shutil.copy(f"{src}/src/{f}", f"{w}/src/{f}")
cfg = json.load(open(w + "/config.json"))
for kv in sys.argv[2:]:
    k, v = kv.split("=", 1)
    if k == "exploit+":
        cfg["exploit"] = cfg["exploit"] + "," + v
    else:
        try: v = json.loads(v)
        except Exception: pass
        cfg[k] = v
json.dump(cfg, open(w + "/config.json", "w"), indent=1)
subprocess.run([sys.executable, tool, "pack", tpl, w, out], check=True, capture_output=True)
print("built", out, cfg)

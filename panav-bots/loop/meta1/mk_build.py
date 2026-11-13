"""Make a seeded build from the merged multi-switch source.  usage: mk_build.py WORKDIR OUT.py [switch ...]
switch in probe|foldall|valuebet|potfold|ctl ; each is forced (raw, ungated) except ctl (controller)."""
import json, subprocess, sys, shutil
work, out, *sw = sys.argv[1:]
c = json.load(open(f"{work}/config.json"))
mv = [s for s in sw if s in ("probe", "foldall", "valuebet")]
if mv:
    c["exploit"] = c["exploit"] + "," + ",".join(mv)
    c["force"] = ",".join(mv)
if "potfold" in sw:
    c.update({"potfold": "on", "pf_gate": "off", "pf_ledger": "off"})
if "ctl" in sw:
    c["exploit"] = c["exploit"] + ",probe,foldall,valuebet"; c["ctl"] = "on"
json.dump(c, open(f"{work}/config.json", "w"), indent=1)
subprocess.check_call([sys.executable, "panav-bots/loop/tools/bundle_tool.py", "pack", "panav-bots/final/bot.py", work, out])

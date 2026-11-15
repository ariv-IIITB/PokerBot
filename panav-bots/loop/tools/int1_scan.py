"""Static scan of every embedded module of a bundled bot: imports (stdlib/numpy only?), file/socket/process calls. Compares two bundles."""
import ast, sys, re
from pathlib import Path
sys.path.insert(0, "tools")
def mods(path):
    t = Path(path).read_text(); i = t.index("_SOURCES = {"); j = t.index("\n}\n", i) + 3
    return ast.literal_eval(t[i + 11:j]), t
BAD_CALLS = {"open","load","fromfile","read_text","read_bytes","listdir","scandir","glob","rglob","iterdir","system","fork","popen","Popen","spawn","posix_spawn","Thread","Timer","start_new_thread","ThreadPoolExecutor","socket","create_connection","urlopen","run","call","check_output","eval","exec","__import__"}
BAD_MODS = {"socket","subprocess","multiprocessing","urllib","http","requests","ftplib","smtplib","ssl","asyncio","threading","ctypes","shutil","pathlib","tempfile","scipy"}
def scan(path):
    d, text = mods(path); std = set(sys.stdlib_module_names) | {"numpy"}
    local = {k.split(".")[0] for k in d}
    imps, calls, bad = set(), {}, []
    for name, (_, src) in d.items():
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Import):
                for a in n.names: imps.add(a.name.split(".")[0])
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module: imps.add(n.module.split(".")[0])
            elif isinstance(n, ast.Call):
                f = n.func; nm = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if nm in BAD_CALLS: calls.setdefault((name, nm), 0); calls[(name, nm)] += 1
    nonstd = {m for m in imps if m not in std and m not in local and m not in ("shared","botsrc")}
    bad = sorted(m for m in imps if m in BAD_MODS)
    return imps, nonstd, bad, calls, text
for p in sys.argv[1:]:
    imps, nonstd, bad, calls, text = scan(p)
    print(f"== {p}\n imports: {sorted(imps)}\n non-stdlib/numpy/local imports: {sorted(nonstd)}\n forbidden-module imports: {bad}\n flagged calls (module,name):count = {dict(sorted(calls.items()))}")
    print(" outside _SOURCES (loader) flagged:", sorted(set(re.findall(r"\b(open|socket|Popen|subprocess|urlopen)\b", text.split("_SOURCES = {")[0] + text.split("\n}\n",1)[1]))))

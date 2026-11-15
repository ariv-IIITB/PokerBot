import subprocess, sys
bot, log = sys.argv[1], sys.argv[2]
p = subprocess.Popen([sys.executable, bot], stdin=subprocess.PIPE, stdout=sys.stdout, text=True, bufsize=1)
with open(log, "w") as f:
    for line in sys.stdin:
        f.write(line); f.flush(); p.stdin.write(line); p.stdin.flush()
p.stdin.close(); p.wait()

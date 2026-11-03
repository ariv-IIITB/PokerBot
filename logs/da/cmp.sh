#!/bin/bash
# usage: cmp.sh BEFORE.txt AFTER.txt  -> lab.eval --compare on copies with the brain label shortened
d=$(mktemp -d); for i in 1 2; do sed -E 's/^tier3.*-nolock vs/tier3-nolock vs/; s/^tier3[^ ]* vs/tier3 vs/' "${!i}" > $d/$i.txt; done
.venv/bin/python -m lab.eval --compare $d/1.txt $d/2.txt

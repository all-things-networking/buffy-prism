#!/bin/zsh
# TCP outcast (buffy/examples/jani/outcast.buffy): compile one model per configuration and evaluate it
# with the native simulator (RUNS runs). Each argument is a list of -D settings, e.g. "NA=4 ARB=2".
cd "$(dirname "$0")/../.." || exit 1
RUNS=${RUNS:-10000}
mkdir -p experiments/buffy_outcast/models
for c in "$@"; do
  defs=(); tag=oc
  for kv in ${=c}; do defs+=(-D $kv); tag=${tag}_${kv/=/}; done
  f=experiments/buffy_outcast/models/$tag.jani
  timeout 300 buffy/build/buffyc-mc buffy/examples/jani/outcast.buffy $defs --stop-at-horizon -o $f || continue
  PYTHONPATH=. timeout ${CAP:-1200} /Users/jkai/buffy-prism/.venv/bin/python experiments/buffy_outcast/oc_eval.py $f $RUNS "$c"
done

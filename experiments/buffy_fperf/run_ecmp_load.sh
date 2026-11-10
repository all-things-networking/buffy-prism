#!/bin/zsh
# Leaf-spine: flow 0's starvation probability and throughput (packets delivered and sent by T) over
# the offered load, for the three ECMP modes; native simulator, RUNS runs each. Capped by `timeout`.
cd "$(dirname "$0")/../.." || exit 1
RUNS=${RUNS:-50000}
mkdir -p experiments/buffy_fperf/models
for l in 0.25 0.5 0.75 1; do for e in 0 1 2; do
  f=experiments/buffy_fperf/models/ls_e${e}_l$l.jani
  buffy/build/buffyc-mc buffy/examples/fperf/leaf_spine.buffy -D ECMP=$e -D LAMBDA=$l --stop-at-horizon -o $f
  PYTHONPATH=. timeout ${CAP:-900} /Users/jkai/buffy-prism/.venv/bin/python experiments/buffy_fperf/native_eval.py $f $RUNS "ECMP=$e LAMBDA=$l"
done; done

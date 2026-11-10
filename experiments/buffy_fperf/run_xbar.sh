#!/bin/zsh
# Leaf-spine: how much the crossbar's choice of stable matching matters. Input-proposing (XBAR=0)
# against output-proposing (XBAR=2) Gale-Shapley, the two extreme stable matchings; native
# simulator, RUNS runs each. Capped by `timeout`.
cd "$(dirname "$0")/../.." || exit 1
RUNS=${RUNS:-50000}
mkdir -p experiments/buffy_fperf/models
for e in 1 2; do for l in 0.75 1; do for x in 0 2; do
  f=experiments/buffy_fperf/models/ls_x${x}_e${e}_l$l.jani
  buffy/build/buffyc-mc buffy/examples/fperf/leaf_spine.buffy -D XBAR=$x -D ECMP=$e -D LAMBDA=$l --stop-at-horizon -o $f
  PYTHONPATH=. timeout ${CAP:-900} /Users/jkai/buffy-prism/.venv/bin/python experiments/buffy_fperf/native_eval.py $f $RUNS "XBAR=$x ECMP=$e LAMBDA=$l"
done; done; done

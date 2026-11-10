#!/bin/zsh
# Loom: P[tenant 2 leads tenant 1 by more than 3 packets at every step 6..9] and the tenants'
# expected deliveries, over tenant 1's load, tenant 2's load and memcached's; native simulator,
# RUNS runs each. Capped by `timeout`.
cd "$(dirname "$0")/../.." || exit 1
RUNS=${RUNS:-50000}
mkdir -p experiments/buffy_fperf/models
for lm in 0 0.1 0.25; do for l2 in 0.5 1; do for l1 in 0.1 0.25 0.5; do
  f=experiments/buffy_fperf/models/loom_${l1}_${l2}_$lm.jani
  buffy/build/buffyc-mc buffy/examples/fperf/loom.buffy -D L1=$l1 -D L2=$l2 -D LM=$lm --stop-at-horizon -o $f
  PYTHONPATH=. timeout ${CAP:-900} /Users/jkai/buffy-prism/.venv/bin/python experiments/buffy_fperf/native_eval.py $f $RUNS "L1=$l1 L2=$l2 LM=$lm"
done; done; done

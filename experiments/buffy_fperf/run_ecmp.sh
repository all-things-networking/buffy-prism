#!/bin/zsh
# Probabilistic leaf-spine (buffy/examples/fperf/leaf_spine.buffy): P[flow 0 gets at most 4 packets in
# 10 steps] for the three ECMP modes and two loads, with the native JANI simulator (src/netmdp/sim),
# 100,000 runs each. Statistical only (647 state variables); capped by `timeout`.
cd "$(dirname "$0")" || exit 1
C=../../buffy/build/buffyc-mc
RUNS=${RUNS:-100000}
mkdir -p models results
for e in 0 1 2; do for l in 1 0.5; do
  $C ../../buffy/examples/fperf/leaf_spine.buffy -D ECMP=$e -D LAMBDA=$l --stop-at-horizon -o models/ls_e${e}_l$l.jani
done; done
cd ../.. && PYTHONPATH=. timeout ${CAP:-3000} /Users/jkai/buffy-prism/.venv/bin/python -c "
import sys; sys.path.insert(0, 'tests')
from pathlib import Path
from buffy_jani_check import check
for e in (0, 1, 2):
    for l in ('1', '0.5'):
        r = check(Path('experiments/buffy_fperf/models/ls_e%d_l%s.jani' % (e, l)), $RUNS)
        p = r['properties']['starved']
        print(f'ECMP={e} LAMBDA={l}: P[starved]={p[\"estimate\"]:.4f} +- {p[\"ci95_half\"]:.4f}  ({p[\"us_per_run\"]:.0f} us/run, compile {r[\"compile_s\"]:.0f} s)', flush=True)
" | tee experiments/buffy_fperf/results/ecmp_native.log

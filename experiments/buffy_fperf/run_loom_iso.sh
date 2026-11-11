#!/bin/zsh
# Loom tenant isolation (buffy/examples/jani/loom_isolation.buffy): P[tenant 1 waiting throughout the
# last W steps yet at most SHARE% of the deliveries], under MQPrio (POLICY 0) and the hierarchical
# policy (POLICY 1), over the offered loads. Native simulator, RUNS runs each; capped by `timeout`.
# Usage: run_loom_iso.sh "RHO1 RHO2 RHOM" ...   (extra -D settings in $DEFS)
cd "$(dirname "$0")/../.." || exit 1
RUNS=${RUNS:-20000}
mkdir -p experiments/buffy_fperf/models
for c in "$@"; do
  set -- ${=c}
  for p in 0 1; do
    f=experiments/buffy_fperf/models/li_p${p}_$1_$2_$3.jani
    buffy/build/buffyc-mc buffy/examples/jani/loom_isolation.buffy -D POLICY=$p -D RHO1=$1 -D RHO2=$2 -D RHOM=$3 ${=DEFS} --stop-at-horizon -o $f
    PYTHONPATH=. timeout ${CAP:-1200} /Users/jkai/buffy-prism/.venv/bin/python experiments/buffy_fperf/loom_eval.py $f $RUNS "POLICY=$p rho=($1,$2,$3) $DEFS"
  done
done

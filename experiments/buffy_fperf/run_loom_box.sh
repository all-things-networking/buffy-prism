#!/bin/zsh
# Loom case study, after the sweep: the mild box A = rho1 in [0.5,0.6], rho2 in [0.6,0.7], rhom in
# [0.1,0.2] (best corner and centre; its worst corner (0.6,0.6,0.1) is in the sweep), an obvious
# point (rhom 0.5), 8 cores at the worst corner, and oracle cross-checks.
cd "$(dirname "$0")/../.." || exit 1
S=experiments/buffy_fperf/run_loom_iso.sh
$S "0.5 0.7 0.2" "0.55 0.65 0.15" "0.6 0.6 0.5"
RUNS=10000 DEFS="-D NC=8" $S "0.6 0.6 0.1"
for a in "0.6 0.6 0.1 0 20000 8" "0.6 0.6 0.1 1 20000 8" "0.5 0.7 0.15 0 20000" "0.55 0.65 0.15 0 20000"; do
  timeout 1200 python3 experiments/buffy_fperf/loom_oracle.py ${=a}
done

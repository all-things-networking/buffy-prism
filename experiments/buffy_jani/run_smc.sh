#!/bin/zsh
# Full-size SMC comparison (N=5, SZ=8, T=14). Statistical only; every run is capped by `timeout`.
# MODEST / PRISM override the tool paths; RUNS the number of runs (default 100000).
cd "$(dirname "$0")/models" || exit 1
M=${MODEST:-/Users/jkai/buffy-prism/Modest/modest}
P=${PRISM:-/Users/jkai/prism-4.10.1-mac64-arm/bin/prism}
N=${RUNS:-100000}
CAP=${CAP:-900}
mkdir -p ../results
: > ../results/timings.txt
run() { local name=$1; shift; local t0=$(date +%s.%N); timeout $CAP "$@" > ../results/$name.log 2>&1; local rc=$?; local t1=$(date +%s.%N); echo "$name rc=$rc wall_s=$(( t1 - t0 ))" >> ../results/timings.txt; }
for p in 0.2 0.6; do
  run modes_sync_p$p   $M modes bfy_p$p.jani          -N $N -J 1 --seed 1
  run modes_staged_p$p $M modes bfy_p${p}_staged.jani -N $N -J 1 --seed 1
  run prism_bfy_p$p    $P bfy_p$p.pm bfy_p$p.props -sim -simmethod ci -simsamples $N -simpathlen 1000
  run prism_hand_p$p   $P hand_p$p.pm hand.props   -sim -simmethod ci -simsamples $N -simpathlen 400
  timeout $CAP python3 ../fig2_mc.py $N $p > ../results/fig2_mc_p$p.txt
done

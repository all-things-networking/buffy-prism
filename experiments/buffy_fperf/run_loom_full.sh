#!/bin/zsh
# Loom tenant isolation at the full NIC size (default NC=8 cores, queue capacity CAP=32), compiled
# with Buffy's --target native (C model core embedded; no JANI expressions). Same measurements as
# run_loom_iso.sh: the memcached row at rho1 = rho2 = 0.6, the box's centre and best corner, the
# obvious point, under MQPrio (POLICY 0) and the hierarchical policy (POLICY 1). JOBS points (default 2) run in
# parallel; each is capped by `timeout`. Output: one line per point (unordered), plus build timings.
# Usage: run_loom_full.sh   (env: NC, CAP, RUNS, JOBS, CAP_S)
cd "$(dirname "$0")/../.." || exit 1
NC=${NC:-8}; CAP=${CAP:-32}; RUNS=${RUNS:-10000}; JOBS=${JOBS:-2}
M=experiments/buffy_fperf/models
mkdir -p $M
one() {
  local p=$1 r1=$2 r2=$3 rm=$4
  local f=$M/lf_nc${NC}_c${CAP}_p${p}_${r1}_${r2}_${rm}.jani
  local t0=$(date +%s)
  buffy/build/buffyc-mc buffy/examples/jani/loom_isolation.buffy --target native --stop-at-horizon \
    -D NC=$NC -D CAP=$CAP -D POLICY=$p -D RHO1=$r1 -D RHO2=$r2 -D RHOM=$rm -o $f || return
  local t1=$(date +%s)
  local out=$(PYTHONPATH=. timeout ${CAP_S:-3600} /Users/jkai/buffy-prism/.venv/bin/python experiments/buffy_fperf/loom_eval.py \
    $f $RUNS "NC=$NC CAP=$CAP POLICY=$p rho=($r1,$r2,$rm)" 2>&1)
  echo "${out:-NC=$NC CAP=$CAP POLICY=$p rho=($r1,$r2,$rm): no result}  [compile $((t1 - t0)) s, simulator build + $RUNS runs $(( $(date +%s) - t1 )) s]"
  rm -f $f
}
if [[ $1 == --one ]]; then shift; one "$@"; exit; fi
# Each simulator build of the full-size model peaks at about 1.4 GB (clang on 22 MB of C): keep JOBS low.
{
  for pt in "0.6 0.6 0" "0.6 0.6 0.05" "0.6 0.6 0.1" "0.6 0.6 0.15" "0.6 0.6 0.2" "0.6 0.6 0.3" \
            "0.55 0.65 0.15" "0.5 0.7 0.2" "0.6 0.6 0.5"; do
    for p in 0 1; do echo "$p $pt"; done
  done
} | xargs -P $JOBS -L 1 zsh "$0" --one

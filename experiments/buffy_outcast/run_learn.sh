#!/bin/zsh
# Learn temporal conditions for the outcast case study and certify them on fresh runs.
#   1. traces of the compiled model (20,000 runs, seed 3), stepped natively;
#   2. bounded-LTL conditions over the first half (intervals ending by step 80) that predict
#      Q = "B gets at most half its fair share in steps 80..159", scored on a training half and a
#      held-out half; the top 4 dangerous and 4 protective conditions go to results/conds_*.json;
#   3. certification on 20,000 fresh runs (seed 101) of the compiled model with the conditions as
#      monitors, and the first two also as Buffy LTL `given` queries (cross-check of the encodings).
# Usage: run_learn.sh "NA=2" [thr]   (thr: the starvation threshold, floor(W / (2 * NF)))
cd "$(dirname "$0")/../.." || exit 1
c=${1:-NA=2}; thr=${2:-13}
defs=(); tag=oc
for kv in ${=c}; do defs+=(-D $kv); tag=${tag}_${kv/=/}; done
M=experiments/buffy_outcast/models; R=experiments/buffy_outcast/results
mkdir -p $M $R
PY=/Users/jkai/buffy-prism/.venv/bin/python
buffy/build/buffyc-mc buffy/examples/jani/outcast.buffy $defs --stop-at-horizon -o $M/$tag.jani || exit 1
PYTHONPATH=. timeout 1200 $PY experiments/buffy_outcast/oc_traces.py $M/$tag.jani 20000 3 $M/${tag}_traces.npz
timeout 600 $PY experiments/buffy_outcast/learn_ltl.py $M/${tag}_traces.npz starveB:$thr 0.1 4 80 $R/conds_$tag.json \
  | tee $R/learn_$tag.log
{ PYTHONPATH=. timeout 1200 $PY experiments/buffy_outcast/certify.py $R/conds_$tag.json 20000 101 "$c" 0,1,2,3,4,5,6,7 mon
  PYTHONPATH=. timeout 1200 $PY experiments/buffy_outcast/certify.py $R/conds_$tag.json 20000 101 "$c" 0,1 ltl; } \
  | tee $R/certify_$tag.log

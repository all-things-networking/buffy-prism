#!/bin/zsh
# PFC congestion spreading (buffy/examples/jani/pfc.buffy), end to end. Results in results/.
#   1. base rates with and without PFC over the load on the congested port (sweep.log);
#   2. input histories (pfc_history.buffy records every step's incast burst and culprit arrival), 4M runs;
#   3. learned conditions (learn_pfc.py), mild and sharp;
#   4. certification: incast-only conditions with --condition-on, culprit ones by rejection.
cd "$(dirname "$0")/../.." || exit 1
D=experiments/buffy_pfc; M=$D/models; R=$D/results; mkdir -p $M $R
PY=/Users/jkai/buffy-prism/.venv/bin/python
for cfg in "PB=0.3 LC=0.4" "PB=0.3 LC=0.5" "PB=0.4 LC=0.5"; do for pfc in 0 1; do
  defs=(); for kv in ${=cfg}; do defs+=(-D $kv); done
  buffy/build/buffyc-mc buffy/examples/jani/pfc.buffy $defs -D PFC=$pfc --stop-at-horizon -o $M/x.jani || exit 1
  echo "$cfg PFC=$pfc: $(PYTHONPATH=. $PY experiments/buffy_conditioning/eval_props.py $M/x.jani 100000 1 blkV blkU starveV starveU spread | awk '{print $1, $2}' | tr '\n' ' ')"
done; done | tee $R/sweep.log
buffy/build/buffyc-mc $D/pfc_history.buffy -D PB=0.3 -D LC=0.5 --stop-at-horizon -o $M/hist.jani || exit 1
PYTHONPATH=. $PY $D/pfc_histories.py $M/hist.jani 4000000 1 0.01 10 $M/h.npz | tee $R/histories.log
{ for mp in 0.05 0.005 0.0005; do echo "#### P[c] >= $mp"; $PY $D/learn_pfc.py $M/h.npz $mp 6; done; } > $R/learn.log
PYTHONPATH=. $PY $D/certify_pfc.py $D/conds_blkU.txt blkU10 "PB=0.3 LC=0.5" 200000 31 --reject 4000000 3 | tee $R/certify_blkU.log

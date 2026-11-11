#!/bin/zsh
# LLM scheduler case study (draft §4) at realistic scale, end to end. Results in results/.
#   1. base rates of the tracked request's bad events under the policies;
#   2. arrival histories (llm_history.buffy), 1M runs;
#   3. learned conditions for "evicted" and "waits >= 20 iterations" (learn_llm.py);
#   4. certification with --condition-on (exact P(A)) and rejection cross-checks; FCFS and SJF;
#   5. Z3: is "a long output in each of iterations 0-4" sufficient, and "at least two long outputs in
#      iterations 0-2" necessary, for the long wait, for every workload?
cd "$(dirname "$0")/../.." || exit 1
D=experiments/buffy_llm; M=$D/models; R=$D/results; mkdir -p $M/smt $R
PY=/Users/jkai/buffy-prism/.venv/bin/python
BIG="R=8 T=40 LP=8 LO=16 NL=8 T_V=5 N_SLOTS=3 KV_CAP=32 CHUNK_BLK=8 P_ARR=0.9 P_LP=0.5 P_OL_SP=0.5 P_OL_LP=0.5"
DEFS=(); for kv in ${=BIG}; do DEFS+=(-D $kv); done
for pol in "0 0" "1 0" "0 1"; do set -- ${=pol}
  buffy/build/buffyc-mc buffy/examples/jani/llm_sched.buffy $DEFS -D POLICY=$1 -D ADM_POLICY=$2 --stop-at-horizon -o $M/big_$1$2.jani || exit 1
  echo "POLICY=$1 ADM_POLICY=$2:"; PYTHONPATH=. $PY experiments/buffy_conditioning/eval_props.py $M/big_$1$2.jani 200000 1 stall preempted cascade
done | tee $R/base_rates.log
buffy/build/buffyc-mc $D/llm_history.buffy $DEFS --stop-at-horizon -o $M/hist.jani || exit 1
PYTHONPATH=. $PY $D/llm_histories.py $M/hist.jani 1000000 2 0.05 20 $M/h20.npz | tee $R/histories.log
{ for mp in 0.05 0.005; do echo "#### evicted, P[c] >= $mp"; $PY $D/learn_llm.py $M/h20.npz evicted $mp 8; done
  for mp in 0.05 0.005; do echo "#### wait20, P[c] >= $mp"; $PY $D/learn_llm.py $M/h20.npz wait20 $mp 8; done; } > $R/learn.log
PYTHONPATH=. $PY $D/certify_llm.py $D/conds_evicted.txt evicted "$BIG" 100000 21 --reject 1000000 2 | tee $R/certify_evicted.log
{ PYTHONPATH=. $PY $D/certify_llm.py $D/conds_wait20.txt wait20 "$BIG" 100000 23 --reject 1000000 2
  PYTHONPATH=. $PY $D/certify_llm.py $D/conds_wait20.txt wait20 "$BIG ADM_POLICY=1" 100000 29; } | tee $R/certify_wait20.log
for name in suff nec; do cp $D/llm_conditions.buffy $M/smt/$name.buffy; done
echo 'query suff: P=? [ (G<=5 (time != 5 || worker.clo >= 5)) && !(F<=T worker.v_maxgap >= 20) ];' >> $M/smt/suff.buffy
echo 'query nec: P=? [ (G<=3 (time != 3 || worker.clo <= 1)) && (F<=T worker.v_maxgap >= 20) ];' >> $M/smt/nec.buffy
for name in suff nec; do
  buffy/build/buffyc-mc $M/smt/$name.buffy $DEFS --target smt -o $M/smt/$name.smt2 || exit 1
  ( s=$(date +%s); r=$(timeout 3000 z3 $M/smt/$name.smt2 | tr '\n' ' '); echo "$name: ${r:-timeout} ($(( $(date +%s) - s )) s)" ) &
done | tee $R/proofs.log
wait

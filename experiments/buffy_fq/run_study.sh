#!/bin/zsh
# FQ case study (draft §3), end to end. Results in results/.
#   1. base rates of Q with the paper's bug and with RFC 8290's fix, at P0 = 0.2 (uniform) and 0.6;
#   2. input histories (fq_history.buffy records each step's arrivals): 4M runs at P0 = 0.6, 20M at 0.2;
#   3. learned conditions on the thin flow's arrivals (learn_fq.py), mild and sharp;
#   4. certification with --condition-on (exact P(A), conditioned runs) and rejection cross-checks;
#      the dangerous conditions again under the fix;
#   5. which early-traffic levels make Q impossible for every workload: Z3 on the SMT-LIB unrolling.
cd "$(dirname "$0")/../.." || exit 1
D=experiments/buffy_fq; M=$D/models; R=$D/results; mkdir -p $M $R
PY=/Users/jkai/buffy-prism/.venv/bin/python
for p0 in 0.2 0.6; do for fix in 0 1; do
  buffy/build/buffyc-mc buffy/examples/jani/fq_buggy.buffy -D P0=$p0 -D FIX=$fix -o $M/fq_${p0}_$fix.jani || exit 1
  echo "P0=$p0 FIX=$fix: $(PYTHONPATH=. $PY experiments/buffy_conditioning/eval_props.py $M/fq_${p0}_$fix.jani 2000000 1 starve_violation)"
done; done | tee $R/base_rates.log
buffy/build/buffyc-mc $D/fq_history.buffy -D P0=0.6 --stop-at-horizon -o $M/fqh06.jani || exit 1
buffy/build/buffyc-mc $D/fq_history.buffy -D P0=0.2 --stop-at-horizon -o $M/fqh02.jani || exit 1
PYTHONPATH=. $PY $D/fq_histories.py $M/fqh06.jani 4000000 1 0.02 $M/h06.npz
PYTHONPATH=. $PY $D/fq_histories.py $M/fqh02.jani 20000000 2 0.004 $M/h02.npz
{ for mp in 0.05 0.01 0.001; do echo "#### P0 = 0.6, P[c] >= $mp"; $PY $D/learn_fq.py $M/h06.npz $mp 6; done
  for mp in 0.05 0.005; do echo "#### P0 = 0.2, P[c] >= $mp"; $PY $D/learn_fq.py $M/h02.npz $mp 6; done; } > $R/learn.log
PYTHONPATH=. $PY $D/certify_fq.py $D/conds_p06.txt "P0=0.6" 200000 11 --reject 4000000 3 | tee $R/certify_p06.log
PYTHONPATH=. $PY $D/certify_fq.py $D/conds_p02.txt "P0=0.2" 1000000 13 --reject 20000000 3 | tee $R/certify_p02.log
grep -E "^(m|u)" $D/conds_p06.txt > $M/c06.txt; grep -E "^u" $D/conds_p02.txt > $M/c02.txt
{ PYTHONPATH=. $PY $D/certify_fq.py $M/c06.txt "P0=0.6 FIX=1" 200000 17
  PYTHONPATH=. $PY $D/certify_fq.py $M/c02.txt "P0=0.2 FIX=1" 1000000 19; } | tee $R/certify_fixed.log
$D/run_necessary.sh

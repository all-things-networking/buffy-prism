#!/bin/zsh
# Conditioned simulation on the full-size buggy FQ model (results/fq.log): the conditioned models
# (--condition-on se / sg, 20,000 runs each) against the ratio _joint / _given estimated from
# 10,000,000 unconditioned runs (feasible for se, P(condition) = 0.00192; not for sg, 5.1e-7).
cd "$(dirname "$0")/../.." || exit 1
D=experiments/buffy_conditioning; M=$D/models; mkdir -p $M $D/results
PY=/Users/jkai/buffy-prism/.venv/bin/python
buffy/build/buffyc-mc $D/fq_conditions.buffy -o $M/fq.jani || exit 1
for q in se sg; do
  buffy/build/buffyc-mc $D/fq_conditions.buffy --condition-on $q -o $M/fq_$q.jani || exit 1
  echo "== conditioned on $q: $(grep -o 'P(condition) = [0-9.e-]*' $M/fq_$q.jani) (exact, from the compiler)"
  PYTHONPATH=. $PY $D/eval_props.py $M/fq_$q.jani 20000 7 $q
done
echo "== unconditioned, 10,000,000 runs"
PYTHONPATH=. timeout 3000 $PY $D/eval_props.py $M/fq.jani 10000000 3 se_joint se_given

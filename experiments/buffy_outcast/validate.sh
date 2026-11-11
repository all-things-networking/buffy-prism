#!/bin/zsh
# Validation of the outcast model (results/validation.log):
#   1. reduced instances (NA = 1, 2; tiny buffers, windows and timeouts): exact values from mcsta
#      against the native simulator (200,000 runs) on the same compiled JANI;
#   2. full size (NA = 2, 4): the compiled model on the native simulator against the independent Python
#      oracle oc_oracle.py, 100,000 runs each with unrelated seeds.
cd "$(dirname "$0")/../.." || exit 1
M=experiments/buffy_outcast/models; mkdir -p $M
PY=/Users/jkai/buffy-prism/.venv/bin/python
for na in 1 2; do
  f=$M/reduced_NA$na.jani
  buffy/build/buffyc-mc buffy/examples/jani/outcast.buffy -D NA=$na -D BUF=2 -D UPCAP=2 -D R=2 -D WMAX=2 -D W0=1 \
    -D RTO=2 -D T=10 -D W=6 -D TOMAX=1 --stop-at-horizon -o $f || exit 1
  echo "== reduced NA=$na: exact (mcsta)"
  timeout 900 /Users/jkai/buffy-prism/Modest/modest mcsta $f 2>&1 | grep -E "States|Property|Probability" | paste - - | grep -v "^ *States" ; \
    timeout 900 /Users/jkai/buffy-prism/Modest/modest mcsta $f 2>&1 | grep -E "^ *States" | head -1
  echo "== reduced NA=$na: native simulator"
  PYTHONPATH=. $PY experiments/buffy_outcast/oc_eval.py $f 200000 "reduced NA=$na" 3
done
for na in 2 4; do
  f=$M/oc_NA$na.jani
  buffy/build/buffyc-mc buffy/examples/jani/outcast.buffy -D NA=$na --stop-at-horizon -o $f || exit 1
  echo "== full size NA=$na: compiled model vs oracle"
  PYTHONPATH=. $PY experiments/buffy_outcast/oc_eval.py $f 100000 "model NA=$na" 5
  timeout 1800 $PY experiments/buffy_outcast/oc_oracle.py 100000 $na 8 8 8 8 2 24 2 160 80 11
done

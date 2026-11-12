#!/bin/sh
# The fabric scaling study (docs/notes/case-study-fabric-scaling.md), one measurement at a time (8 GB machine:
# never two large models at once). Results go to results/; every script skips points already in its output file.
# Run from anywhere; PY defaults to the main checkout's venv.
cd "$(dirname "$0")/../.." || exit 1
PY=${PY:-/Users/jkai/buffy-prism/.venv/bin/python}
R=experiments/buffy_fabric/results
mkdir -p $R
export PYTHONPATH=.

# 0. the model against the independent oracle (12 small configurations)
[ -s $R/oracle_check.log ] || $PY experiments/buffy_fabric/check_oracle.py 100000 > $R/oracle_check.log 2>&1

# 1. fabric size: around the incast's onset (16-48 hosts), then 64 to 2048 hosts (4:1 oversubscription)
$PY experiments/buffy_fabric/size_sweep.py $R/size_sweep.jsonl \
  2x8x2,3x8x2,4x8x2,6x8x2,8x8x2,8x16x4,16x16x4,16x32x8,32x32x8,64x32x8 RUNS=10000 BUDGET=120 \
  2>&1 | tee -a $R/size_sweep.log

# 2. horizon: 256 hosts, a query round every 60 steps, 1 to 167 rounds
$PY experiments/buffy_fabric/horizon_sweep.py $R/horizon_sweep.jsonl 16x16x4 60,180,600,1800,6000,10020 BUDGET=120 \
  2>&1 | tee -a $R/horizon_sweep.log

# 3. a rare event (P ~ 5e-6): Monte Carlo against RESTART and fixed effort, derived and refined importance
$PY experiments/buffy_fabric/rare_event.py $R/rare_event.jsonl 2x8x2 loss 900 1200 THRESH=6 2>&1 | tee -a $R/rare_event.log
# refined importance: fixed effort only. With RESTART its factors multiply to 5e13 (1/P ~ 2e5) and one batch did not
# finish in 2 h 50 min (see the note).
$PY experiments/buffy_fabric/rare_event.py $R/rare_event.jsonl 2x8x2 loss 900 60 THRESH=6 IMP=hand PILOT=256 PILOTS=16 \
  RESTART=0 2>&1 | tee -a $R/rare_event.log

# 4. one size further (4,096 hosts), alone: compile under a memory watchdog, then build and run
experiments/buffy_fabric/try_largest.sh 64 64 16 | tee $R/largest_compile.out
PYTHONPATH=.:experiments/buffy_fabric $PY experiments/buffy_fabric/largest_run.py ${TMPDIR:-/tmp}/fabric_64x64x16.jani \
  | tee -a $R/largest.out

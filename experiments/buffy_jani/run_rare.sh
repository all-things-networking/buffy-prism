#!/bin/sh
# Rare-event benchmark on the FQ starve property (P0 = 0.2, violation probability ~3.3e-4):
# time for modes to reach a 95% confidence interval of +-10% relative half-width, with plain
# Monte Carlo and with importance splitting (RESTART and fixed effort) driven by the compiled
# importance hint `imp` (= fq.deqs_bl; the violation is deqs_bl >= 4), by the importance function
# the compiler derives from the query (--auto-importance: starve_imp = min(deqs_bl, 4)), or by modes'
# automatic importance function. Every run is capped with timeout.
cd "$(dirname "$0")" || exit 1
M=${MODEST:-/Users/jkai/buffy-prism/Modest/modest}
C=../../buffy/build/buffyc-mc
CAP=${CAP:-900}
mkdir -p models results/rare
$C ../../buffy/examples/jani/fq_buggy.buffy -D P0=0.2 --importance-props -o models/rare_p0.2_imp.jani
$C ../../buffy/examples/jani/fq_buggy.buffy -D P0=0.2 --auto-importance -o models/rare_p0.2_autoimp.jani
: > results/rare/timings.txt
run() {
  name=$1; shift
  model=${MODEL:-models/rare_p0.2_imp.jani}
  t0=$(date +%s)
  timeout $CAP $M modes $model --props starve_violation -C 0.95 -W 0.1 --relative-width \
    -J 1 --seed 1 "$@" > results/rare/$name.log 2>&1
  echo "$name rc=$? wall_s=$(( $(date +%s) - t0 ))" >> results/rare/timings.txt
}
run plain
run restart_imp --rare Restart --ifun-prop imp 0 4
run fixedeffort_imp --rare FixedEffort --ifun-prop imp 0 4
run restart_auto --rare Restart
run restart_imp_manual --rare Restart --ifun-prop imp 0 4 --levels Manual "1:4, 2:4, 3:4"
MODEL=models/rare_p0.2_autoimp.jani run restart_autoimp --rare Restart --ifun-prop starve_imp 0 4

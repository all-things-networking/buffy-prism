#!/bin/zsh
# Is a quiet start *necessary* for Q? For each (b, c), Z3 checks on Buffy's SMT-LIB unrolling (14 steps,
# every workload in the distributions' support) whether Q can happen although the thin flow sent at least c
# packets by step b. `sat` = some workload does it (results/necessary.log).
cd "$(dirname "$0")/../.." || exit 1
D=experiments/buffy_fq; M=$D/models/smt; mkdir -p $M
for bc in 3_4 4_4 5_3 5_4 6_4; do
  b=${bc%_*}; c=${bc#*_}
  cp $D/fq_conditions.buffy $M/n_$bc.buffy
  echo "query n_$bc: P=? [ (F<=T fq.deqs_bl >= 4) && F<=$b (time == $b && fq.cenq >= $c) ];" >> $M/n_$bc.buffy
  buffy/build/buffyc-mc $M/n_$bc.buffy --target smt -o $M/n_$bc.smt2 || exit 1
  ( s=$(date +%s); r=$(timeout 1500 z3 $M/n_$bc.smt2 | tr '\n' ' '); echo "Q with >= $c thin packets by step $b: ${r:-timeout} ($(( $(date +%s) - s )) s)" ) &
done
wait

#!/bin/sh
# Build buffyc-mc (buffy submodule, Buffy main) and generate all models into ./models.
set -e
cd "$(dirname "$0")"
make -C ../../buffy mc >/dev/null
C=../../buffy/build/buffyc-mc
SRC=../../buffy/examples/jani/fq_buggy.buffy
mkdir -p models
for p in 0.2 0.6; do
  $C $SRC -D P0=$p --stats -o models/bfy_p$p.jani 2> models/bfy_p$p.stats
  $C $SRC -D P0=$p --staged -o models/bfy_p${p}_staged.jani
  $C $SRC -D P0=$p --importance-props -o models/bfy_p${p}_imp.jani
  $C $SRC -D P0=$p --staged --importance-props -o models/bfy_p${p}_staged_imp.jani
  $C $SRC -D P0=$p --target prism -o models/bfy_p$p.pm
  $C $SRC -D P0=$p --target prism --prism-temps stages -o models/bfy_p${p}_stages.pm
  $C ../../buffy/examples/jani/fq_buggy_mdp_mixed.buffy -D P0=$p --layout choose -o models/bfy_mdp_mixed_p${p}_choose.jani
  $C ../../buffy/examples/jani/fq_buggy_mdp_mixed.buffy -D P0=$p --staged -o models/bfy_mdp_mixed_p${p}_staged.jani
done
# MDP: nondeterministic arrivals (sync layout: one sync vector per joint choice, 3125).
MDP=../../buffy/examples/jani/fq_buggy_mdp.buffy
$C $MDP --importance-props -o models/bfy_mdp_imp.jani
$C $MDP --layout choose -o models/bfy_mdp_choose.jani
$C $MDP --staged --importance-props -o models/bfy_mdp_staged_imp.jani
$C $MDP --target prism -o models/bfy_mdp.pm
python3 patch_hand_model.py ../../tests/models/fqcodel_5i_dtmc_unif.pm models

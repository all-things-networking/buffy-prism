#!/bin/bash
# Reproduce the "Q5 starves the others" case study.
# Requires the persistent PRISM toolchain (set PRISM, or source the env.sh that defines it).
#   PRISM=/path/to/prism ./run_q5_case_study.sh
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
: "${PRISM:?set PRISM to the prism launcher (or source your env.sh first)}"
LEVELS="$HERE/q5_starvation_levels.props"
SIM=(-sim -simmethod ci -simwidth 2e-3 -simconf 0.01 -simpathlen 224)

python3 "$HERE/gen_q5_variants.py"

run() { "$PRISM" "$1" "$LEVELS" "${SIM[@]}" 2>/dev/null | grep -oP 'Result: \K[0-9.E+-]+'; }
row() { # $1=label $2=model
  local v; v=$(run "$2")
  python3 -c "
v=[float(x) for x in '''$v'''.split()]
print(f'{\"$1\":28s} ' + '  '.join(f'{1-x:5.3f}' for x in v))"
}

echo "P(Q5 starves others at level n) = P(iq5_deqs_bl >= n)"
echo "input shape                   >=2     >=3     >=4     >=5"
row "baseline (student model)"   "$HERE/fqcodel_5i_dtmc_unif.pm"
row "dense: 1 pkt every step"    "$HERE/q5var_dense.pm"
row "bursty: 4-pkt bursts"       "$HERE/q5var_bursty25.pm"
row "trickle: 1 pkt w.p. 0.30"   "$HERE/q5var_trk30.pm"
row "periodic: 1 pkt / 5 steps"  "$HERE/q5var_per5.pm"
row "periodic: 1 pkt / 4 steps"  "$HERE/q5var_per4.pm"

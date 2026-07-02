#!/usr/bin/env bash
# ============================================================================
#  v2 queue-based chunked scheduler — conditional-probability table (one regime).
#  Requires:  source ~/buffy-prism-tools/env.sh
#  Usage:  ./run_queue_study.sh          (defaults below)
#          TV=3 PA=0.5 PLP=0.4 POL=0.4 POLICY=0 SLO=3 ./run_queue_study.sh
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"
PRISM="${PRISM:-$HOME/buffy-prism-tools/prism-4.10.1-linux64-x86/bin/prism}"

TV=${TV:-3}; PA=${PA:-0.5}; PLP=${PLP:-0.4}; POL=${POL:-0.4}; POLICY=${POLICY:-0}
CONST="T_V=$TV,POLICY=$POLICY,p_arr=$PA,p_lp=$PLP,p_ol=$POL"

ratio(){ python3 -c "print('n/a' if $2==0 else f'{$1/$2:.4f}')"; }

echo "############################################################"
echo "# v2 queue scheduler — victim TBT stall (queueing)"
echo "# T_V=$TV p_arr=$PA p_lp=$PLP p_ol=$POL POLICY=$POLICY"
echo "############################################################"

mapfile -t R < <($PRISM scheduler_queue.pm scheduler_queue.props -const "$CONST" 2>/dev/null \
                 | grep -E "Result:" | sed 's/.*Result: //; s/ (exact.*//')

names=("A: stall | EARLY long-prompt (before, none after)" \
       "B: stall | LATE  long-prompt (after, none before)" \
       "C: stall | VOLUME (>=2 long-prompt)" \
       "D: stall | CORRELATION vol (>=2 lp & >=2 lo)" \
       "E: stall | FULLY-long before victim (timing+corr)" \
       "F: stall | fully-long AFTER victim (contrast)")

printf '\n%-50s %8s %8s %8s %8s\n' "group" "P(BE)" "P(BE&C)" "P(C)" "P(BE|C)"
printf -- '-------------------------------------------------------------------------------------\n'
for g in 0 1 2 3 4 5; do
  base=${R[$((g*3))]}; joint=${R[$((g*3+1))]}; pc=${R[$((g*3+2))]}
  printf '%-50s %8.4f %8.4f %8.4f %8s\n' "${names[$g]}" "$base" "$joint" "$pc" "$(ratio "$joint" "$pc")"
done

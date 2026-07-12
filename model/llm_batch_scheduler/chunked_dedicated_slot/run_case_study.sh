#!/usr/bin/env bash
# ============================================================================
#  Reproduce the CHUNKED-prefill batch-scheduler case study (exact PRISM MC).
#  Requires the persistent toolchain:  source ~/buffy-prism-tools/env.sh
#  Usage:  ./run_case_study.sh          (defaults PA=0.5 PL=0.4)
#          PA=0.7 PL=0.4 ./run_case_study.sh
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

PRISM="${PRISM:-$HOME/buffy-prism-tools/prism-4.10.1-linux64-x86/bin/prism}"
MODEL=scheduler.pm
PROPS=scheduler.props

PA=${PA:-0.5}; PL=${PL:-0.4}; POLICY=${POLICY:-0}
CONST="POLICY=$POLICY,p_arr=$PA,p_long=$PL"

ratio(){ python3 -c "print('n/a' if $2==0 else f'{$1/$2:.4f}')"; }

echo "############################################################"
echo "# LLM batch scheduler (CHUNKED prefill) — conditional study"
echo "# regime: p_arr=$PA p_long=$PL   POLICY=$POLICY (0=fcfs,1=priority)"
echo "############################################################"

mapfile -t R < <($PRISM "$MODEL" "$PROPS" -const "$CONST" 2>/dev/null \
                 | grep -E "Result:" | sed 's/.*Result: //; s/ (exact.*//')

names=("A: BE1 victim-preempt | EARLY long (before, none after)" \
       "B: BE1 victim-preempt | LATE  long (after, none before)" \
       "C: BE1 victim-preempt | VOLUME (n_long>=2)" \
       "D: BE2 victim-stall    | EARLY long" \
       "E: BE3 cascade         | EARLY long")

printf '\n%-52s %8s %8s %8s %8s\n' "group" "P(BE)" "P(BE&C)" "P(C)" "P(BE|C)"
printf -- '---------------------------------------------------------------------------------------\n'
for g in 0 1 2 3 4; do
  base=${R[$((g*3))]}; joint=${R[$((g*3+1))]}; pc=${R[$((g*3+2))]}
  printf '%-52s %8.4f %8.4f %8.4f %8s\n' "${names[$g]}" "$base" "$joint" "$pc" "$(ratio "$joint" "$pc")"
done

# ---- policy comparison (both chunked; eager variant is in ../no_chunking) ---
echo ""
echo "=== policy comparison (chunked, same input) ==="
printf '%-20s %10s %10s %10s\n' "policy" "P(preempt)" "P(stall)" "P(cascade)"
for pol in "fcfs:0" "priority:1"; do
  label=${pol%%:*}; pv=${pol#*:}
  ov="p_arr=$PA,p_long=$PL,POLICY=$pv"
  p=$($PRISM "$MODEL" -const "$ov" -pf 'P=? [ F ("done" & v_preempts>=1) ]'   2>/dev/null | grep Result: | sed 's/.*: //;s/ (ex.*//')
  s=$($PRISM "$MODEL" -const "$ov" -pf 'P=? [ F ("done" & v_maxgap>=SLO_TBT) ]' 2>/dev/null | grep Result: | sed 's/.*: //;s/ (ex.*//')
  c=$($PRISM "$MODEL" -const "$ov" -pf 'P=? [ F ("done" & preempts>=K_CASC) ]'  2>/dev/null | grep Result: | sed 's/.*: //;s/ (ex.*//')
  printf '%-20s %10.4f %10.4f %10.4f\n' "$label" "$p" "$s" "$c"
done

#!/usr/bin/env bash
# ============================================================================
#  Reproduce the LLM batch-scheduler case study (exact probabilistic model
#  checking with PRISM). Requires the persistent toolchain:
#      source ~/buffy-prism-tools/env.sh
#  Usage:  ./run_case_study.sh
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"

PRISM="${PRISM:-$HOME/buffy-prism-tools/prism-4.10.1-linux64-x86/bin/prism}"
MODEL=scheduler.pm
PROPS=scheduler.props

# baseline input regime + realistic scheduler defaults (fcfs + chunked prefill)
PA=${PA:-0.5}; PL=${PL:-0.4}; POLICY=${POLICY:-0}; CHUNKED=${CHUNKED:-1}
CONST="POLICY=$POLICY,CHUNKED=$CHUNKED,p_arr=$PA,p_long=$PL"

pf(){ # pf "<property>" [extra-const]  -> prints the numeric result
  $PRISM "$MODEL" -const "$CONST${2:+,$2}" -pf "$1" 2>/dev/null \
    | grep -E "Result:" | sed 's/.*Result: //; s/ (exact.*//'; }

ratio(){ python3 -c "print('n/a' if $2==0 else f'{$1/$2:.4f}')"; }

echo "############################################################"
echo "# LLM batch scheduler — conditional-probability case study"
echo "# regime: p_arr=$PA p_long=$PL  scheduler: POLICY=$POLICY CHUNKED=$CHUNKED"
echo "############################################################"

# ---- run the grouped query suite and fold triples into conditionals --------
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

# ---- knob comparison (baseline P(bad) under each scheduler variant) --------
echo ""
echo "=== scheduler-knob comparison (baseline probabilities, same input) ==="
printf '%-34s %10s %10s %10s\n' "variant" "P(preempt)" "P(stall)" "P(cascade)"
for cfg in "fcfs+chunked:POLICY=0,CHUNKED=1" "priority+chunked:POLICY=1,CHUNKED=1" "fcfs+eager:POLICY=0,CHUNKED=0"; do
  label=${cfg%%:*}; kc=${cfg#*:}
  ov="p_arr=$PA,p_long=$PL,$kc"
  p=$($PRISM "$MODEL" -const "$ov" -pf 'P=? [ F ("done" & v_preempts>=1) ]'   2>/dev/null | grep Result: | sed 's/.*: //;s/ (ex.*//')
  s=$($PRISM "$MODEL" -const "$ov" -pf 'P=? [ F ("done" & v_maxgap>=SLO_TBT) ]' 2>/dev/null | grep Result: | sed 's/.*: //;s/ (ex.*//')
  c=$($PRISM "$MODEL" -const "$ov" -pf 'P=? [ F ("done" & preempts>=K_CASC) ]'  2>/dev/null | grep Result: | sed 's/.*: //;s/ (ex.*//')
  printf '%-34s %10.4f %10.4f %10.4f\n' "$label" "$p" "$s" "$c"
done

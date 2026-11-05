#!/bin/zsh
# Exact comparison on small configurations: hand-written PRISM models (PRISM explicit engine)
# against the Buffy programs buffy/examples/jani/{incast,llm_sched}.buffy (incast: compiled PRISM,
# PRISM explicit; LLM: compiled JANI, mcsta). Every run is capped by `timeout`.
# Usage: ./cmp_exact.sh incast "M WIN SLEN BUF THRESH" ...
#        ./cmp_exact.sh llm "T_V N_SLOTS KV_CAP CHUNK_BLK POLICY ADM_POLICY p_arr p_lp p_ol_sp p_ol_lp" ...
cd "$(dirname "$0")" || exit 1
PR=${PRISM:-/Users/jkai/prism-4.10.1-mac64-arm/bin/prism}
MO=${MODEST:-/Users/jkai/buffy-prism/Modest/modest}
C=../../buffy/build/buffyc-mc
EX=../../buffy/examples/jani
CAP=${CAP:-900}
mkdir -p models
row() { sed 's/ (exact floating point)//; s/ (1 initial)//; s/Result: //; s/States satisfying filter true: [0-9]*//' | tr '\n' ' '; echo; }
what=$1; shift
for c in "$@"; do
  set -- ${=c}
  if [ $what = incast ]; then
    echo "== M=$1 WIN=$2 SLEN=$3 BUF=$4 THRESH=$5"
    printf 'P=? [ F ("done" & odrops>=THRESH) ];\nP=? [ F ("done" & idrops>=THRESH) ];\nfilter(count, stage=1);\n' > models/hand_incast.props
    $C $EX/incast.buffy -D M=$1 -D WIN=$2 -D SLEN=$3 -D BUF=$4 -D THRESH=$5 --target prism -o models/incast.pm
    echo 'filter(count, stage=0);' >> models/incast.props
    printf 'hand  '; timeout $CAP $PR hand/incast.pm models/hand_incast.props -const M=$1,WIN=$2,SLEN=$3,BUF=$4,THRESH=$5 \
      -ex -javamaxmem 12g 2>&1 | grep -E '^States|^Result|rror' | row
    printf 'buffy '; timeout $CAP $PR models/incast.pm models/incast.props -ex -javamaxmem 12g 2>&1 | grep -E '^States|^Result|rror' | row
  else
    echo "== T_V=$1 N_SLOTS=$2 KV_CAP=$3 CHUNK_BLK=$4 POLICY=$5 ADM_POLICY=$6 p_arr=$7 p_lp=$8 p_ol_sp=$9 p_ol_lp=${10}"
    K="T_V=$1,N_SLOTS=$2,KV_CAP=$3,CHUNK_BLK=$4,POLICY=$5,ADM_POLICY=$6,p_arr=$7,p_lp=$8,p_ol_sp=$9,p_ol_lp=${10}"
    grep -v '^//' hand/llm_scheduler.props | grep . > models/hand_llm.props
    printf 'P=? [ F ("done" & v_preempts>=1) ];\nP=? [ F ("done" & preempts>=K_CASC) ];\nfilter(count, stage=1);\n' >> models/hand_llm.props
    $C $EX/llm_sched.buffy -D T_V=$1 -D N_SLOTS=$2 -D KV_CAP=$3 -D CHUNK_BLK=$4 -D POLICY=$5 -D ADM_POLICY=$6 \
      -D P_ARR=$7 -D P_LP=$8 -D P_OL_SP=$9 -D P_OL_LP=${10} -o models/llm_sched.jani
    printf 'hand  '; timeout $CAP $PR hand/llm_scheduler.pm models/hand_llm.props -const $K -ex -javamaxmem 12g 2>&1 \
      | grep -E '^States|^Result|rror' | row
    printf 'buffy '; timeout $CAP $MO mcsta models/llm_sched.jani 2>&1 | grep -E 'States:|Probability:|error' \
      | sed 's/ *States: */States: /; s/ *Probability: //' | tr '\n' ' '; echo
  fi
done

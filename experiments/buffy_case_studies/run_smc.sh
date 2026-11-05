#!/bin/zsh
# Full-size statistical comparison (20k runs each, capped): modes on the compiled Buffy JANI against
# `prism -sim` on the hand-written models, at the incast headline corner (example 2) and the LLM
# scheduler's SMC-validation configuration (8 records, chunked/VALIDATION.md).
cd "$(dirname "$0")" || exit 1
MO=${MODEST:-/Users/jkai/buffy-prism/Modest/modest}
PR=${PRISM:-/Users/jkai/prism-4.10.1-mac64-arm/bin/prism}
C=../../buffy/build/buffyc-mc
EX=../../buffy/examples/jani
N=${RUNS:-20000}
CAP=${CAP:-2400}
mkdir -p models results
$C $EX/incast.buffy -o models/incast_big.jani
$C $EX/llm_sched.buffy -D R=8 -D T=40 -D LP=8 -D LO=16 -D NL=8 -D T_V=5 -D N_SLOTS=3 -D KV_CAP=32 -D CHUNK_BLK=8 \
   -D P_ARR=0.9 -D P_LP=0.5 -D P_OL_SP=0.5 -D P_OL_LP=0.5 -o models/llm_sched_big.jani
printf 'P=? [ F ("done" & odrops>=THRESH) ];\n' > models/hand_incast_loss.props
tm() { local n=$1; shift; local t0=$(date +%s); timeout $CAP "$@" > results/$n.log 2>&1; echo "rc=$? wall_s=$(( $(date +%s) - t0 ))" >> results/$n.log; }
tm smc_modes_incast $MO modes models/incast_big.jani -N $N -J 1 --seed 1 &
tm smc_prism_hand_incast $PR hand/incast.pm models/hand_incast_loss.props -const M=16,WIN=96,SLEN=8,BUF=32,THRESH=8 \
   -sim -simmethod ci -simsamples $N -simpathlen 8000 &
tm smc_modes_llm $MO modes models/llm_sched_big.jani -N $N -J 1 --seed 1 &
tm smc_prism_hand_llm $PR hand/llm_scheduler_big.pm \
   -const T_V=5,POLICY=0,ADM_POLICY=0,N_SLOTS=3,KV_CAP=32,CHUNK_BLK=8,p_arr=0.9,p_lp=0.5,p_ol_sp=0.5,p_ol_lp=0.5 \
   -pf 'P=? [ F ("done" & v_maxgap>=SLO_TBT) ]' -sim -simmethod ci -simsamples $N -simpathlen 3000 &
wait

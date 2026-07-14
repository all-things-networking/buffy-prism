#!/usr/bin/env bash
# ============================================================================
#  Reproduce the mild/obvious regions (REGIONS.md) on the realistic multi-chunk
#  model via SMC.  Requires:  source ~/buffy-prism-tools/env.sh
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"
PRISM="${PRISM:-$HOME/buffy-prism-tools/prism-4.10.1-linux64-x86/bin/prism}"
BIG=scheduler_mc.pm
SAMPLES=${SAMPLES:-15000}

# realistic multi-chunk: long prompt spans LP=4 prefill chunks; long output LO=32 iters
python3 gen_scheduler.py --M 8 --SP 1 --LP 4 --SO 1 --LO 32 --VP 1 --VO 2 --T 64 --out "$BIG" >/dev/null

smc(){ $PRISM "$BIG" -const "$1" -pf 'P=? [ F ("done" & v_maxgap>=SLO_TBT) ]' \
        -sim -simsamples "$SAMPLES" -simpathlen 4000 2>&1 | grep -E "^Result:" | sed 's/Result: //; s/ with.*//'; }
B='T_V=5,POLICY=0,ADM_POLICY=0,CHUNK_BLK=1,KV_CAP=64,p_arr=0.9'

echo "### SHARP AXIS: provisioning N_SLOTS (p_lp=p_ol=0.3) ###"
for n in 2 3 4 5 6; do printf '  N_SLOTS=%s : %s\n' "$n" "$(smc "$B,N_SLOTS=$n,p_lp=0.3,p_ol_sp=0.3,p_ol_lp=0.3")"; done

echo "### MILD box @ knee N_SLOTS=3 : P(stall) over (p_lp x p_ol) ###"
printf '          %9s %9s %9s\n' "p_ol=0.2" "p_ol=0.3" "p_ol=0.4"
for pl in 0.2 0.3 0.4; do
  printf 'p_lp=%s ' "$pl"
  for po in 0.2 0.3 0.4; do printf ' %9s' "$(smc "$B,N_SLOTS=3,p_lp=$pl,p_ol_sp=$po,p_ol_lp=$po")"; done
  echo
done

echo "### CONFIG-uncertainty region: N_SLOTS in {2,3,4}, realistic mix p_lp=0.4,p_ol=0.4 ###"
for n in 2 3 4; do printf '  N_SLOTS=%s : %s\n' "$n" "$(smc "$B,N_SLOTS=$n,p_lp=0.4,p_ol_sp=0.4,p_ol_lp=0.4")"; done

echo "### OBVIOUS corner: N_SLOTS=2, heavy realistic mix p_lp=0.7,p_ol=0.6 (expect ~1) ###"
printf '  %s\n' "$(smc "$B,N_SLOTS=2,p_lp=0.7,p_ol_sp=0.6,p_ol_lp=0.6")"

#!/usr/bin/env bash
# ============================================================================
#  SMC validation of the headline finding at realistic scale.
#  Generates a large model (M records, wide size ratios) that is far too big for
#  exact checking, and validates via statistical model checking that
#  P(interactive stall) is ~flat in the long-PROMPT fraction and dominated by the
#  long-OUTPUT fraction.  Requires:  source ~/buffy-prism-tools/env.sh
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"
PRISM="${PRISM:-$HOME/buffy-prism-tools/prism-4.10.1-linux64-x86/bin/prism}"
BIG=scheduler_big.pm
SAMPLES=${SAMPLES:-20000}

# realistic-ish: 8 records / 3 slots (oversubscribed), prompt 1 vs 8 blocks,
# output 1 vs 16 blocks, horizon 40. CHUNK_BLK>=LP => prompt prefills in ~1 iter.
python3 gen_scheduler.py --M 8 --SP 1 --LP 8 --SO 1 --LO 16 --VP 1 --VO 2 --T 40 --out "$BIG" >/dev/null

smc(){ $PRISM "$BIG" -const "$1" -pf 'P=? [ F ("done" & v_maxgap>=SLO_TBT) ]' \
        -sim -simsamples "$SAMPLES" -simpathlen 3000 2>&1 | grep -E "^Result:" | sed 's/Result: //'; }
B='T_V=5,POLICY=0,ADM_POLICY=0,N_SLOTS=3,KV_CAP=32,p_arr=0.9'

echo "### SMC (samples=$SAMPLES): P(victim stall) at realistic scale, chunk=8 (prompt~1 iter) ###"
echo "-- vary long-PROMPT fraction p_lp (long-output fixed 0.5): expect FLAT --"
for x in 0.1 0.5 0.9; do printf '   p_lp=%s : %s\n' "$x" "$(smc "$B,CHUNK_BLK=8,p_lp=$x,p_ol_sp=0.5,p_ol_lp=0.5")"; done
echo "-- vary long-OUTPUT fraction p_ol (long-prompt fixed 0.5): expect STRONG --"
for x in 0.1 0.5 0.9; do printf '   p_ol=%s : %s\n' "$x" "$(smc "$B,CHUNK_BLK=8,p_lp=0.5,p_ol_sp=$x,p_ol_lp=$x")"; done

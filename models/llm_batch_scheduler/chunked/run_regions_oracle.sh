#!/usr/bin/env bash
# ============================================================================
#  Realistic-magnitude regions via the independent oracle (sched_sim.py).
#  Token units: chunk=512; prompt short 16 / long 2048 (=4 prefill chunks);
#  output short 8 / long 256 (=256 decode iters, 64:1 vs a long prompt);
#  batch width N_SLOTS (the knee is realistic ~20-24 for this load); Poisson
#  load lam=0.3/iter; M=64 pool; horizon T=400, victim arrives T_V=200.
#  No PRISM needed. (The oracle is cross-checked vs PRISM at the small config;
#  see the top of sched_sim.py / REGIONS.md.)
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"
S=${SAMPLES:-8000}
COMMON="--lam 0.3 --M 64 --KV_CAP 1000000000 --CHUNK 512 --SP 16 --LP 2048 --SO 8 --LO 256 --VP 16 --VO 32 --T 400 --T_V 200 --GAPMAX 400"
sim(){ python3 sched_sim.py --samples "$S" $COMMON "$@" | sed 's/P(stall) = //; s/ (.*//'; }

echo "### SHARP-ish axis: provisioning N_SLOTS (p_lp=0.3, p_ol=0.3) ###"
for n in 12 16 20 22 24 28 32; do printf '  N_SLOTS=%-3s %s\n' "$n" "$(sim --N_SLOTS $n --p_lp 0.3 --p_ol_sp 0.3 --p_ol_lp 0.3)"; done
echo "### GRADUAL axis: long-output fraction p_ol (N_SLOTS=22) ###"
for po in 0.22 0.26 0.30 0.34 0.38; do printf '  p_ol=%s %s\n' "$po" "$(sim --N_SLOTS 22 --p_lp 0.3 --p_ol_sp $po --p_ol_lp $po)"; done
echo "### FLAT axis: prompt fraction p_lp (N_SLOTS=22, p_ol=0.3) ###"
for pl in 0.1 0.5 0.9; do printf '  p_lp=%s %s\n' "$pl" "$(sim --N_SLOTS 22 --p_lp $pl --p_ol_sp 0.3 --p_ol_lp 0.3)"; done
echo "### PER-REQUEST (64:1): W_prompt (long 2048-tok prompt) vs W_output (long 256-tok output) ###"
for f in 0.3 0.5; do
  echo "  f=$f : W_prompt=$(sim --N_SLOTS 22 --p_lp $f --p_ol_sp 0 --p_ol_lp 0)   W_output=$(sim --N_SLOTS 22 --p_lp 0 --p_ol_sp $f --p_ol_lp 0)"
done
echo "### CONFIG mild box corners: N_SLOTS in [20,24], p_ol=0.3, p_lp free ###"
for n in 20 24; do for pl in 0.1 0.9; do printf '  N=%s p_lp=%s : %s\n' "$n" "$pl" "$(sim --N_SLOTS $n --p_lp $pl --p_ol_sp 0.3 --p_ol_lp 0.3)"; done; done

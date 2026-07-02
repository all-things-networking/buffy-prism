#!/usr/bin/env bash
# ============================================================================
#  Sweep input regimes for the v2 queue scheduler and rank candidate
#  assumptions by "mild P(C) x large lift" (the FQ-CoDel/incast sweet spot).
#  Requires:  source ~/buffy-prism-tools/env.sh
#  Usage:  ./sweep_queue.sh   (writes rows to /tmp, prints ranked tables)
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")"
PRISM="${PRISM:-$HOME/buffy-prism-tools/prism-4.10.1-linux64-x86/bin/prism}"
OUT="$(mktemp)"

for TV in 2 3 4; do
 for PA in 0.4 0.6 0.8; do
  for PLP in 0.3 0.5; do
   for POL in 0.3 0.5; do
     res=$($PRISM scheduler_queue.pm scheduler_queue.props \
             -const "T_V=$TV,POLICY=0,ADM_POLICY=0,N_SLOTS=2,KV_CAP=8,CHUNK_BLK=3,p_arr=$PA,p_lp=$PLP,p_ol_sp=$POL,p_ol_lp=$POL" 2>/dev/null \
           | grep -E "Result:" | sed 's/.*Result: //; s/ (exact.*//' | tr '\n' ' ')
     echo "$TV $PA $PLP $POL $res" >> "$OUT"
   done
  done
 done
done

python3 - "$OUT" <<'PY'
import sys
rows=[]
for ln in open(sys.argv[1]):
    p=ln.split()
    if len(p)<22: continue
    tv,pa,plp,pol=p[:4]
    r=list(map(float,p[4:22]))
    base=r[0]
    def cond(j,c): return (r[c]/r[c] if False else (r[j]/r[c] if r[c]>0 else 0.0)), r[c]
    condA,pcA=(r[1]/r[2] if r[2]>0 else 0),r[2]           # early long-prompt
    condB,pcB=(r[4]/r[5] if r[5]>0 else 0),r[5]           # late long-prompt (contrast)
    condC,pcC=(r[7]/r[8] if r[8]>0 else 0),r[8]           # volume
    condE,pcE=(r[13]/r[14] if r[14]>0 else 0),r[14]       # fully-long before (timing+corr)
    condF,pcF=(r[16]/r[17] if r[17]>0 else 0),r[17]       # fully-long after (contrast)
    rows.append(dict(tv=tv,pa=pa,plp=plp,pol=pol,base=base,
                     condA=condA,pcA=pcA,liftA=condA/base if base>0 else 0,condB=condB,
                     condC=condC,pcC=pcC,liftC=condC/base if base>0 else 0,
                     condE=condE,pcE=pcE,liftE=condE/base if base>0 else 0,condF=condF))

def show(title,key,pckey,condkey,contrastkey,contrastlabel):
    print(f"\n=== {title} — ranked by lift (mild P(C) in [0.08,0.5], base in [0.03,0.5]) ===")
    print(f"{'TV':>2} {'p_arr':>5} {'p_lp':>4} {'p_ol':>4} | {'base':>6} {'P(BE|C)':>8} {'P(C)':>6} {'lift':>5} | {contrastlabel:>9}")
    good=[x for x in rows if 0.08<=x[pckey]<=0.5 and 0.03<=x['base']<=0.5]
    for x in sorted(good,key=lambda z:z[key],reverse=True)[:8]:
        print(f"{x['tv']:>2} {x['pa']:>5} {x['plp']:>4} {x['pol']:>4} | {x['base']:6.3f} {x[condkey]:8.3f} {x[pckey]:6.3f} {x[key]:5.2f} | {x[contrastkey]:9.3f}")

show("A: EARLY long-prompt before victim","liftA","pcA","condA","condB","after(B)")
show("E: FULLY-long before victim","liftE","pcE","condE","condF","after(F)")
show("C: VOLUME (>=2 long-prompt)","liftC","pcC","condC","condA","early(A)")
PY
echo ""
echo "(rows: $OUT)"

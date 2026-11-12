#!/bin/sh
# Try one fabric size beyond the sweep's largest, alone on the machine, with a memory watchdog: buffyc-mc is killed
# if its resident memory passes LIMIT_MB (default 6000 of the machine's 8 GB). Prints the compile's wall time and
# peak memory, or how far it got.
# Usage: experiments/buffy_fabric/try_largest.sh NL H NS [B]
cd "$(dirname "$0")/../.." || exit 1
NL=$1; H=$2; NS=$3; B=${4:-16}; LIMIT_MB=${LIMIT_MB:-6000}
OUT=${TMPDIR:-/tmp}/fabric_${NL}x${H}x${NS}.jani
/usr/bin/time -l ./buffy/build/buffyc-mc buffy/examples/jani/fabric.buffy --target native --stats \
  -D NL=$NL -D H=$H -D NS=$NS -D B=$B -D NCAP=8 -D SLEN=4 -D WIN=10 -D T=60 -o $OUT 2> ${OUT}.log &
sleep 1
P=$(pgrep -n buffyc-mc); peak=0; t0=$(date +%s)
while kill -0 $P 2>/dev/null; do
  rss=$(( $(ps -o rss= -p $P 2>/dev/null || echo 0) / 1024 ))
  [ "$rss" -gt "$peak" ] && peak=$rss
  if [ "$rss" -gt "$LIMIT_MB" ]; then kill $P; echo "killed at ${rss} MB after $(( $(date +%s) - t0 )) s"; break; fi
  sleep 1
done
wait
echo "${NL}x${H}x${NS} B=$B: peak ${peak} MB (watchdog)"; grep -E "state variables|real|maximum resident|error" ${OUT}.log
ls -la $OUT 2>/dev/null | awk '{print "output", $5, "bytes"}'

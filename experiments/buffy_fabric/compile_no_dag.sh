#!/bin/zsh
# Compile time and peak memory footprint of one fabric size with a given buffyc-mc (one run at a time on an
# 8 GB machine). Used for results/compile_no_dag.jsonl: Buffy 3c36ba3 (builds the step DAG) against e2ade47
# (no step DAG for --target native, compiler decision 57). Footprints there are MiB.
# Usage: experiments/buffy_fabric/compile_no_dag.sh BUFFYC NL H NS
cd "$(dirname "$0")/../.." || exit 1
B=$1; NL=$2; H=$3; NS=$4; OUT=${TMPDIR:-/tmp}/fabric_${NL}x${H}x${NS}
/usr/bin/time -l $B buffy/examples/jani/fabric.buffy --target native -D NL=$NL -D H=$H -D NS=$NS -D B=16 -D NCAP=8 \
  -D SLEN=4 -D WIN=10 -D T=60 -D THRESH=2 -D VTH=1 -o $OUT.jani 2> $OUT.log
echo "${NL}x${H}x${NS}: rc=$? $(grep ' real' $OUT.log) peak footprint $(( $(grep 'peak memory footprint' $OUT.log | awk '{print $1}') / 1048576 )) MiB"
rm -f $OUT.jani

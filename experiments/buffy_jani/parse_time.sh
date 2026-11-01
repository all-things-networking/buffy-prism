#!/bin/zsh
# How PRISM / stormpy parsing scales with formula sharing: FQ for N = 2..5, PRISM output with
# formulas vs staged temporaries. Parse only (PRISM -nobuild), 60 s cap per run.
cd "$(dirname "$0")" || exit 1
C=../../buffy/build/buffyc-mc
P=${PRISM:-/Users/jkai/prism-4.10.1-mac64-arm/bin/prism}
PY=${PYTHON_STORM:-/Users/jkai/buffy-prism/.venv/bin/python}
mkdir -p parse results
python3 - ../../buffy/examples/jani/fq_buggy.buffy <<'PYEOF'
import re, sys
src = open(sys.argv[1]).read()
for n in (2, 3, 4, 5):
    s = src.replace("const N = 5;", f"const N = {n};")
    others = " & ".join(f"backlog-p(ibs[{j}]) > 0" for j in range(n - 1))
    s = re.sub(r"//@ if \(head == N-1 & .*?\) deqs_bl", f"//@ if (head == N-1 & {others}) deqs_bl", s)
    lines = "\n".join(f"    traffic fq.ibs[{j}] ~ uniform(0, K);" for j in range(n - 1))
    s = re.sub(r"(    traffic fq\.ibs\[0\].*\n)(    traffic fq\.ibs\[[1-3]\].*\n)*", lines + "\n", s)
    s = s.replace("traffic fq.ibs[4]", f"traffic fq.ibs[{n-1}]")
    open(f"parse/fq_n{n}.buffy", "w").write(s)
PYEOF
: > results/parse_time.txt
for n in 2 3 4 5; do
  $C parse/fq_n$n.buffy --target prism --prism-temps formulas --stats -o parse/f_n$n.pm 2> parse/st_n$n.txt
  $C parse/fq_n$n.buffy --target prism --prism-temps stages -o parse/s_n$n.pm
  dag=$(grep "DAG nodes" parse/st_n$n.txt | awk '{print $NF}'); tree=$(grep "tree size" parse/st_n$n.txt | awk '{print $NF}')
  t0=$(date +%s.%N); timeout 60 $P parse/f_n$n.pm -nobuild > /dev/null 2>&1; rc1=$?; t1=$(date +%s.%N)
  timeout 60 $PY -c "import stormpy; stormpy.parse_prism_program('parse/f_n$n.pm')" >/dev/null 2>&1; rc2=$?; t2=$(date +%s.%N)
  timeout 60 $P parse/s_n$n.pm -nobuild > /dev/null 2>&1; rc3=$?; t3=$(date +%s.%N)
  printf "N=%s dag=%s tree=%s | PRISM formulas %.1fs rc=%s | stormpy formulas %.1fs rc=%s | PRISM stages %.1fs rc=%s\n" \
    $n $dag $tree $((t1-t0)) $rc1 $((t2-t1)) $rc2 $((t3-t2)) $rc3 >> results/parse_time.txt
done
cat results/parse_time.txt

"""
Factored against joint conditioning on demand, for the conditions in a file (learn_joint.py notation): P(A) to
full precision, the memo's size when h is computed from the initial state (all the input states a run can
reach), and the time that takes. Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_pfc/factored_memo.py conds.txt "PB=0.3 LC=0.5"
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from learn_joint import to_buffy  # noqa: E402
from src.netmdp.sim.jani_native import JaniModel  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BUFFYC = str(ROOT / "buffy/build/buffyc-mc")

conds = [tuple(x.strip() for x in l.split("|", 1)) for l in open(sys.argv[1]) if "|" in l and not l.startswith("#")]
dflags = [x for kv in sys.argv[2].split() for x in ("-D", kv)]
Q = "F<=T (time == T && pfc.uBlk >= 10)"
prog = (Path(__file__).parent / "pfc_conditions.buffy").read_text() + "".join(
    f"query {n}: P=? [ {Q} ] given {to_buffy(f)};\n" for n, f in conds)
with tempfile.TemporaryDirectory() as d:
    src = Path(d) / "pfc.buffy"
    src.write_text(prog)
    for n, f in conds:
        for mode in (["--joint-condition"], []):
            out = Path(d) / f"{n}.jani"
            subprocess.run([BUFFYC, str(src), *dflags, "--target", "native", "--stop-at-horizon", "--condition-on", n,
                            *mode, "-o", str(out)], check=True, timeout=600, capture_output=True)
            jm = JaniModel(json.loads(out.read_text()))
            t0 = time.time()
            pa = jm.condition_probability()
            dt = time.time() - t0
            parts = jm.condition_factor_states()
            print(f"{n} {'joint   ' if mode else 'factored'}: P(A) = {pa:.15g}  memo {sum(parts)} input states"
                  f" {'(' + ' + '.join(map(str, parts)) + ')' if len(parts) > 1 else ''}  h from the initial state in"
                  f" {dt:.2f} s", flush=True)

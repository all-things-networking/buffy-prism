"""
The batch simulator must draw every source of a step from its distribution, however many sources the step has.

A step samples its sources from one uniform, rescaled into each chosen interval; a double has 53 bits, so before
jm_step_g refreshed the residual, the later sources of a step with many draws collapsed onto their first outcomes
(a leaf-spine model's ECMP choices mostly picked spine 0). Here a step draws K values uniform in 0..3 (2 bits each,
2K bits in all) and K rare Bernoulli arrivals (about 6.6 bits per arrival); every one of them must keep its
marginal: P(v = j) = 1/4 for the last draws, and the mean arrival count per source equals P_ARR.

Run from the repository root: PYTHONPATH=. python tests/test_native_precision.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel

ROOT = Path(__file__).resolve().parents[1]
BUFFYC = ROOT / "buffy" / "build" / "buffyc-mc"
K, P_ARR, RUNS = 64, 0.01, 40_000

PROGRAM = f"""
const K = {K};
many(buffer[K] ib, buffer[K] ob) {{
    global int<0..3>[K] v;
    //@ monitor int<0..1>[K] got;
    for (i in 0..K) do {{
        v[i] ~ uniform(0, 3);
        //@ got[i] = backlog-p(ib[i]) > 0 ? 1 : 0;
        move-p(ib[i], ob[i], 1);
    }}
}}
network {{
    capacity many.ib = 1;
    traffic many.ib ~ bernoulli({P_ARR});
    horizon 1;
}}
query any: P=? [ F<=1 many.v[0] == 3 ];
"""


def main():
    with tempfile.TemporaryDirectory() as d:
        src, out = Path(d) / "many.buffy", Path(d) / "many.jani"
        src.write_text(PROGRAM)
        subprocess.run([str(BUFFYC), str(src), "--target", "native", "-o", str(out)], check=True, capture_output=True)
        model = json.loads(out.read_text())
    last = range(K - 8, K)
    obs = {f"v{i}_{j}": {"op": "ite", "if": {"op": "=", "left": f"many_v_{i}", "right": j}, "then": 1, "else": 0}
           for i in last for j in range(4)}
    obs.update({f"got{i}": f"many_got_{i}" for i in range(K)})
    jm = JaniModel(model, observables=obs)
    # the arrivals of step 0 are read by the monitor in step 0 (state at time 1); the draws likewise
    r = jm.simulate_rewards(RUNS, 1, None, seed=11)
    worst = 0.0
    for i in last:
        for j in range(4):
            f = r.final[f"v{i}_{j}"].mean()
            worst = max(worst, abs(f - 0.25) / np.sqrt(0.25 * 0.75 / RUNS))
    arr = np.array([r.final[f"got{i}"].mean() for i in range(K)])
    z_arr = np.abs(arr[K // 2:].mean() - P_ARR) / np.sqrt(P_ARR * (1 - P_ARR) / (RUNS * (K - K // 2)))
    ok = worst < 4.5 and z_arr < 4.5
    print(f"{'ok  ' if ok else 'FAIL'} {K} uniform(0,3) and {K} Bernoulli({P_ARR}) sources per step: largest |z| of the "
          f"last draws' frequencies {worst:.2f}; arrivals of the later half {arr[K // 2:].mean():.5f} (z {z_arr:.2f})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

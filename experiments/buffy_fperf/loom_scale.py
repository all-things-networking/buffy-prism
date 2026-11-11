"""
Scaling of Loom tenant isolation (buffy/examples/jani/loom_isolation.buffy, MQPrio at the box corner
rho = (0.6, 0.6, 0.1)) with Buffy's structured native step: per core count (queue capacity CAP), the Buffy
compile (time, peak memory), the C model core's size, the simulator build, and the cost of a run, with
P[starved] from `runs` runs.

Usage (from the repository root): PYTHONPATH=. python experiments/buffy_fperf/loom_scale.py CAP runs NC...
"""
import json
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel

ROOT = Path(__file__).resolve().parents[2]


def main():
    cap, runs, ncs = int(sys.argv[1]), int(sys.argv[2]), [int(x) for x in sys.argv[3:]]
    print(f"{'cores':>5} {'vars':>6} {'buffy s':>8} {'buffy GB':>8} {'C kB':>6} {'build s':>7} {'ms/run':>7}  P[starved] ({runs} runs)")
    with tempfile.TemporaryDirectory() as d:
        for nc in ncs:
            out = Path(d) / f"l{nc}.jani"
            t0 = time.time()
            r = subprocess.run(["/usr/bin/time", "-l", str(ROOT / "buffy/build/buffyc-mc"),
                                str(ROOT / "buffy/examples/jani/loom_isolation.buffy"), "--target", "native",
                                "--stop-at-horizon", "-D", f"NC={nc}", "-D", f"CAP={cap}", "-o", str(out)],
                               capture_output=True, text=True, timeout=3600)
            tb = time.time() - t0
            if r.returncode:
                print(f"{nc:>5} buffyc failed: {r.stderr.strip()[-300:]}")
                break
            rss = next(int(l.split()[0]) for l in r.stderr.splitlines() if "maximum resident" in l) / 1e9
            model = json.loads(out.read_text())
            c_kb = len(model["x-buffy-native"]["c"]) / 1e3
            T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
            obs = {"w1": "loom_w1", "waiting": {"op": "ite", "if": "loom_waiting", "then": 1, "else": 0}}
            t1 = time.time()
            jm = JaniModel(model, observables=obs)
            t2 = time.time()
            res = jm.simulate_rewards(runs, T, None, seed=1)
            t3 = time.time()
            st = (res.final["waiting"] > 0.5) & (100 * res.final["w1"] <= 40 * 20)
            p = st.mean()
            half = 1.96 * np.sqrt(max(p * (1 - p), 1e-12) / runs)
            print(f"{nc:>5} {len(model['variables']):>6} {tb:>8.1f} {rss:>8.2f} {c_kb:>6.0f} {t2 - t1:>7.1f} "
                  f"{1000 * (t3 - t2) / runs:>7.2f}  {p:.4f} ± {half:.4f}", flush=True)


if __name__ == "__main__":
    main()

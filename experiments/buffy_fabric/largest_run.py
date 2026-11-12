"""
Build and simulate the largest fabric (64x64x16, 4,096 hosts) from a JANI file compiled by try_largest.sh: build
time, cost per run, P[victim] and the size sweep's SPRT. Results: results/largest.jsonl.
  PYTHONPATH=.:experiments/buffy_fabric python experiments/buffy_fabric/largest_run.py FABRIC.jani
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, "experiments/buffy_fabric")
from fabric_lib import build, runs, horizon, state_vars, COUNTERS
from size_sweep import BatchSampler, THETA, DELTA, ALPHA, MAX_RUNS, fixed_sample_n
from src.netmdp.hyptest.intervals import clopper_pearson
from src.netmdp.hyptest.wald_sprt import WaldSprt
from src.netmdp.hyptest.hyptest import ErrTols, HypResult
path = Path(sys.argv[1]); nl, h = 64, 64
t = time.time(); model = json.loads(path.read_text()); load_s = time.time() - t
T = horizon(model); nv = state_vars(model); c_mb = len(model["x-buffy-native"]["c"]) / 1e6
jm, build_s = build(model); del model
print(f"loaded {load_s:.1f} s, {nv} vars, C {c_mb:.1f} MB, build {build_s:.1f} s", flush=True)
t = time.time(); runs(jm, 5, T, seed=1); per = (time.time() - t) / 5
n = int(max(200, min(2000, 120 / per)))
t = time.time(); est, steps = runs(jm, n, T, seed=2); sim = time.time() - t
k = int(est["victim"].sum()); lo, hi = clopper_pearson(k, n, 0.95)
fan_in = (nl - 1) * h - 1
res = {"size": "64x64x16", "hosts": nl * h, "fan_in": fan_in, "state_vars": nv, "c_mb": round(c_mb, 1),
       "build_s": round(build_s, 1), "runs": n, "per_run_ms": round(1000 * sim / n, 2),
       "per_host_step_ns": round(1e9 * sim / n / T / (nl * h), 1), "victim": [k / n, lo, hi],
       "incast_lost_frac": round(float(est["oLost"].mean()) / (fan_in * 4), 4)}
sampler = BatchSampler(jm, T, seed=3); sprt = WaldSprt(THETA, ErrTols(ALPHA, ALPHA), DELTA, MAX_RUNS)
t = time.time(); r = sprt.run_test(sampler)
res["sprt"] = {"decision": {HypResult.ACCEPT_H_PLUS: "H+", HypResult.ACCEPT_H_MINUS: "H-"}.get(r.get_result(), "?"),
               "runs": r.get_n(), "test_s": round(time.time() - t, 2)}
print(json.dumps(res), flush=True)

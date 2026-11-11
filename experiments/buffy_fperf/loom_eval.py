"""
Loom tenant isolation: one native-simulator pass per configuration. From each run's final state it
takes the window deliveries w1, w2 and the flag `waiting`, and reports P[starved] (waiting and
100*w1 <= SHARE*W), P[waiting] and E[w1], E[w2].

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_fperf/loom_eval.py model.jani runs label [W SHARE]
"""
import json
import sys
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel


def main():
    path, runs, label = Path(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    W = int(sys.argv[4]) if len(sys.argv) > 4 else 20
    share = int(sys.argv[5]) if len(sys.argv) > 5 else 40
    model = json.loads(path.read_text())
    horizon = next(int(c["value"]) for c in model.get("constants", []) if c["name"] == "T") if any(
        c["name"] == "T" for c in model.get("constants", [])) else None
    if horizon is None:
        # Buffy inlines constants; the horizon is the upper bound of `time`.
        horizon = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    obs = {"w1": "loom_w1", "w2": "loom_w2", "waiting": {"op": "ite", "if": "loom_waiting", "then": 1, "else": 0}}
    native = JaniModel(model, observables=obs)
    r = native.simulate_rewards(runs, horizon, None, seed=1)
    w1, w2, wait = r.final["w1"], r.final["w2"], r.final["waiting"]
    starved = (wait > 0.5) & (100 * w1 <= share * W)
    p = starved.mean()
    half = 1.96 * np.sqrt(max(p * (1 - p), 1e-12) / runs)
    print(f"{label}: starved={p:.4f}±{half:.4f}  waiting={wait.mean():.4f}  e_w1={w1.mean():.3f}  e_w2={w2.mean():.3f}", flush=True)


if __name__ == "__main__":
    main()

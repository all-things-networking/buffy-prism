"""
Evaluate a Buffy-compiled JANI file with the native simulator (src/netmdp/sim): every bounded
reachability property (P, or Pmax/Pmin of a DTMC) and every C<=k / I=k expected value, from the same
number of runs. MDPs run under a uniform scheduler (one arbitrary resolution of the choices).

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_fperf/native_eval.py model.jani [runs] [label]
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "tests")
from buffy_jani_check import expected_value_properties, reachability_properties, reward_model, reward_samples  # noqa: E402


def main():
    path, runs = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 100000
    label = sys.argv[3] if len(sys.argv) > 3 else path.stem
    model = json.loads(path.read_text())
    reach, ev = reachability_properties(model), expected_value_properties(model)
    native = reward_model(model, ev, goals={n: g for n, (g, _) in reach.items()})
    sched = {a: 1.0 for a in native.edge_actions} if model["type"] == "mdp" else None
    out = []
    for name, (_, bound) in reach.items():
        hits, _ = native.simulate(runs, bound, name, sched, seed=1)
        p = hits / runs
        out.append(f"{name}={p:.4f}±{1.96 * np.sqrt(max(p * (1 - p), 1e-12) / runs):.4f}")
    by_k = {}
    for name, (_, _, k) in ev.items():
        if k not in by_k:
            by_k[k] = native.simulate_rewards(runs, k, sched, seed=2)
        x = reward_samples(native, ev, by_k, name)
        out.append(f"{name}={x.mean():.3f}±{1.96 * x.std(ddof=1) / np.sqrt(runs):.3f}")
    print(f"{label}: " + "  ".join(out), flush=True)


if __name__ == "__main__":
    main()

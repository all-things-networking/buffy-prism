"""
Estimate every reachability property (F, with or without a step bound) of a compiled Buffy JANI model with
the native simulator: per property the fraction of runs whose target holds at some time-step boundary up
to the horizon, with a 95% Clopper-Pearson interval. Runs are split into batches to bound memory.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_conditioning/eval_props.py model.jani runs seed [prop ...]
"""
import json
import sys
from pathlib import Path

import numpy as np

from src.netmdp.hyptest.intervals import clopper_pearson
from src.netmdp.sim.jani_native import JaniModel


def main():
    path, runs, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    want = set(sys.argv[4:])
    model = json.loads(Path(path).read_text())
    T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    obs = {}
    for p in model["properties"]:
        if want and p["name"] not in want:
            continue
        e = p["expression"]["values"]["exp"]
        if e.get("op") != "U":
            continue
        obs[p["name"]] = {"op": "ite", "if": e["right"], "then": 1, "else": 0}
    jm = JaniModel(model, observables=obs)
    hits = {n: 0 for n in obs}
    done, b = 0, 0
    while done < runs:
        n = min(1_000_000, runs - done)
        r = jm.simulate_rewards(n, T, None, seed=seed * 1000 + b)
        for k in obs:
            hits[k] += int(((r.state_cumulative[k] > 0) | (r.final[k] > 0)).sum())
        done += n
        b += 1
    for k in obs:
        lo, hi = clopper_pearson(hits[k], runs, 0.95)
        print(f"{k}: {hits[k] / runs:.6g} [{lo:.6g}, {hi:.6g}]  ({hits[k]} of {runs})", flush=True)


if __name__ == "__main__":
    main()

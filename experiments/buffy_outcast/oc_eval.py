"""
TCP outcast (buffy/examples/jani/outcast.buffy): one native-simulator pass per configuration. From each
run's final state it takes every flow's timeout count `to[i]` and window deliveries `got[i]`, and
reports P[starve] (at most half the fair share W/NF of the window) for B and port A's flows, P[to_B >= 1], the mean of P[to_i >= 1] over port A's flows, and E[got] for B and for an A flow.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_outcast/oc_eval.py model.jani runs label [seed]
"""
import json
import sys
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel


def load(path):
    model = json.loads(Path(path).read_text())
    horizon = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    nf = sum(1 for v in model["variables"] if v["name"].startswith("outcast_to_"))
    return model, horizon, nf


def main():
    path, runs, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 1
    model, horizon, nf = load(path)
    obs = {f"to{i}": f"outcast_to_{i}" for i in range(nf)} | {f"got{i}": f"outcast_got_{i}" for i in range(nf)}
    r = JaniModel(model, observables=obs).simulate_rewards(runs, horizon, None, seed=seed)
    na = nf - 1
    tob = (r.final[f"to{na}"] >= 1).mean()
    toa = np.mean([(r.final[f"to{i}"] >= 1).mean() for i in range(na)])
    half = lambda p: 1.96 * np.sqrt(max(p * (1 - p), 1e-12) / runs)
    gb = r.final[f"got{na}"].mean()
    ga = np.mean([r.final[f"got{i}"].mean() for i in range(na)])
    W = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == f"outcast_got_{na}")
    thr = W / (2 * nf)   # half the fair share of the window
    sb = (r.final[f"got{na}"] <= thr).mean()
    sa = np.mean([(r.final[f"got{i}"] <= thr).mean() for i in range(na)])
    print(f"{label}: P[starveB]={sb:.4f}±{half(sb):.4f} P[starveA]={sa:.4f}  P[toB]={tob:.4f}±{half(tob):.4f}  P[toA]={toa:.4f}  E[gotB]={gb:.2f}  E[gotA]={ga:.2f}  "
          f"E[toB]={r.final[f'to{na}'].mean():.2f} E[toA]={np.mean([r.final[f'to{i}'].mean() for i in range(na)]):.2f}",
          flush=True)


if __name__ == "__main__":
    main()

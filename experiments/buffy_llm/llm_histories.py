"""
Arrival histories of the LLM scheduler at scale (llm_history.buffy records each iteration's arrival draw),
with the tracked request's outcomes: evicted at least once, and its worst inter-token gap. Keeps every
run with an eviction or a gap >= keep_gap, and a fraction `keep` of the others, weighted 1 / keep.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_llm/llm_histories.py model.jani runs seed keep keep_gap out.npz
"""
import json
import sys
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel


def main():
    path, runs, seed, keep, kgap, out = (sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]),
                                         int(sys.argv[5]), sys.argv[6])
    model = json.loads(Path(path).read_text())
    T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    obs = {f"h_{t}": f"worker_hist_{t}" for t in range(T)}
    obs |= {"pre": "worker_v_preempts", "gap": "worker_v_maxgap"}
    jm = JaniModel(model, observables=obs)
    rng = np.random.default_rng(seed)
    H, P, G, Wt = [], [], [], []
    done, b = 0, 0
    while done < runs:
        n = min(500_000, runs - done)
        r = jm.simulate_rewards(n, T, None, seed=seed * 1000 + b)
        pre, gap = r.final["pre"], r.final["gap"]
        interesting = (pre >= 1) | (gap >= kgap)
        sel = interesting | (rng.random(n) < keep)
        H.append(np.stack([r.final[f"h_{t}"] for t in range(T)], axis=1)[sel].astype(np.int8))
        P.append(pre[sel].astype(np.int8))
        G.append(gap[sel].astype(np.int8))
        Wt.append(np.where(interesting[sel], 1.0, 1.0 / keep))
        done, b = done + n, b + 1
    P_, G_, W_ = np.concatenate(P), np.concatenate(G), np.concatenate(Wt)
    np.savez_compressed(out, h=np.concatenate(H), pre=P_, gap=G_, w=W_, runs=runs, T=T)
    print(f"{runs} runs; P[evicted] = {(W_ * (P_ >= 1)).sum() / runs:.4f}; gap distribution:",
          {g: round(float((W_ * (G_ == g)).sum() / runs), 4) for g in range(int(G_.max()) + 1)})


if __name__ == "__main__":
    main()

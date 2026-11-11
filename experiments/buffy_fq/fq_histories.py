"""
Input histories of the buggy FQ model at scale, from the native simulator (no per-step stepping): the
model records each step's arrivals in monitors (fq_history.buffy), so a run's final state holds its whole
input. Keeps every run where Q happens (the thin flow served >= 4 times while all bulk queues are
backlogged) and a random fraction `keep` of the others, with weights 1 / keep, so that probabilities
over all runs can be estimated from the sample.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_fq/fq_histories.py model.jani runs seed keep out.npz
"""
import json
import sys
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel


def main():
    path, runs, seed, keep, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    model = json.loads(Path(path).read_text())
    T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    obs = {f"h5_{t}": f"fq_h5_{t}" for t in range(T)} | {f"hb_{t}": f"fq_hb_{t}" for t in range(T)}
    obs["deqs_bl"] = "fq_deqs_bl"
    jm = JaniModel(model, observables=obs)
    rng = np.random.default_rng(seed)
    H5, HB, Q, Wt = [], [], [], []
    done, b, nq = 0, 0, 0
    while done < runs:
        n = min(1_000_000, runs - done)
        r = jm.simulate_rewards(n, T, None, seed=seed * 1000 + b)
        q = r.final["deqs_bl"] >= 4
        sel = q | (rng.random(n) < keep)
        h5 = np.stack([r.final[f"h5_{t}"] for t in range(T)], axis=1)[sel].astype(np.int8)
        hb = np.stack([r.final[f"hb_{t}"] for t in range(T)], axis=1)[sel].astype(np.int8)
        H5.append(h5)
        HB.append(hb)
        Q.append(q[sel])
        Wt.append(np.where(q[sel], 1.0, 1.0 / keep))
        nq += int(q.sum())
        done += n
        b += 1
    np.savez_compressed(out, h5=np.concatenate(H5), hb=np.concatenate(HB), q=np.concatenate(Q),
                        w=np.concatenate(Wt), runs=runs, T=T)
    print(f"{runs} runs, {nq} with Q (P[Q] = {nq / runs:.5g}); kept {sum(len(x) for x in Q)} -> {out}")


if __name__ == "__main__":
    main()

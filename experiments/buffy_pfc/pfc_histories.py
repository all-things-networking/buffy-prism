"""
Input histories of the PFC model at scale (pfc_history.buffy records every step's incast burst and culprit
arrival), with the outcomes: U's and V's blocked steps in the window, and the steps H / switch 1 were
paused. Keeps every run with uBlk >= blk and a fraction `keep` of the others, weighted 1 / keep.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_pfc/pfc_histories.py model.jani runs seed keep blk out.npz
"""
import json
import sys
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel


def main():
    path, runs, seed, keep, blk, out = (sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]),
                                        int(sys.argv[5]), sys.argv[6])
    model = json.loads(Path(path).read_text())
    T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    obs = {f"b_{t}": f"pfc_hb_{t}" for t in range(T)} | {f"c_{t}": f"pfc_hc_{t}" for t in range(T)}
    obs |= {"u": "pfc_uBlk", "v": "pfc_vBlk", "p1": "pfc_p1Steps", "p2": "pfc_p2Steps"}
    jm = JaniModel(model, observables=obs)
    rng = np.random.default_rng(seed)
    B, C, U, V, P1, P2, Wt = [], [], [], [], [], [], []
    done, k, nq = 0, 0, 0
    while done < runs:
        n = min(500_000, runs - done)
        r = jm.simulate_rewards(n, T, None, seed=seed * 1000 + k)
        q = r.final["u"] >= blk
        sel = q | (rng.random(n) < keep)
        B.append(np.stack([r.final[f"b_{t}"] for t in range(T)], axis=1)[sel].astype(np.int8))
        C.append(np.stack([r.final[f"c_{t}"] for t in range(T)], axis=1)[sel].astype(np.int8))
        for L, key in ((U, "u"), (V, "v"), (P1, "p1"), (P2, "p2")):
            L.append(r.final[key][sel].astype(np.int16))
        Wt.append(np.where(q[sel], 1.0, 1.0 / keep))
        nq += int(q.sum())
        done, k = done + n, k + 1
    np.savez_compressed(out, b=np.concatenate(B), c=np.concatenate(C), u=np.concatenate(U), v=np.concatenate(V),
                        p1=np.concatenate(P1), p2=np.concatenate(P2), w=np.concatenate(Wt), runs=runs, T=T)
    print(f"{runs} runs, {nq} with uBlk >= {blk} (P = {nq / runs:.5g}) -> {out}")


if __name__ == "__main__":
    main()

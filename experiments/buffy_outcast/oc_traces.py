"""
Per-step traces of the compiled outcast model (buffy/examples/jani/outcast.buffy), for learning temporal
conditions. Steps the native JANI model edge by edge and records, at every time-step boundary, the
values of the given state variables. Saves an .npz with an array (runs, T+1, vars) and the names.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_outcast/oc_traces.py model.jani runs seed out.npz [var ...]
"""
import json
import sys
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel

DEFAULT = ["aA", "aB", "dropB", "w_{B}", "rto_{B}", "got_{B}", "got_0", "to_{B}", "to_0", "oq_len", "up_len"]


def main():
    path, runs, seed, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    model = json.loads(Path(path).read_text())
    nf = sum(1 for v in model["variables"] if v["name"].startswith("outcast_to_"))
    names = [n.replace("{B}", str(nf - 1)) for n in (sys.argv[5:] or DEFAULT)]
    jm = JaniModel(model)
    idx = [jm.index["outcast_" + n] for n in names]
    t_i = jm.index["time"]
    T = jm.variables[t_i].upper
    rng = np.random.default_rng(seed)
    tr = np.zeros((runs, T + 1, len(names)), dtype=np.int16)
    for r in range(runs):
        s = jm.initial_state()
        tr[r, 0] = s[idx]
        t = 0
        while t < T:
            en = jm.enabled_edges(s)
            e = en[0] if len(en) == 1 else en[rng.integers(len(en))]
            jm.step(s, e, rng.random())
            if s[t_i] != t:
                t = int(s[t_i])
                tr[r, t] = s[idx]
    np.savez_compressed(out, traces=tr, names=np.array(names))
    print(f"{runs} runs, T={T}, vars={names} -> {out}")


if __name__ == "__main__":
    main()

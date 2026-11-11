"""
`buffyc-mc --target native` (Buffy's C model core) against the JANI path (the sync layout, translated by
jani_native): on the same seeds the two must simulate identically, i.e. the same hits of every reachability
property and the same per-run totals of every reward variable, for DTMCs and for MDPs under the uniform
scheduler. Both sample the probabilistic sources in traffic order with one uniform per step, so equality is
exact, not statistical.

Run from the repository root: PYTHONPATH=. python tests/test_native_target.py [example ...]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel

ROOT = Path(__file__).resolve().parents[1]
BUFFYC = ROOT / "buffy" / "build" / "buffyc-mc"
EXAMPLES = {
    # example: extra flags (DTMCs, then MDPs)
    "sp": [], "tandem": [], "rr": [], "classes_fifo": [], "classes_tandem": [], "ltl": [], "deck_rr": [],
    "arith": [], "bursty": [], "draws": [], "draws_loop": [], "tandem_immediate": [], "cond_input": [],
    "fq_buggy": [], "incast": ["-D", "M=4", "-D", "WIN=4", "-D", "SLEN=3", "-D", "BUF=3", "-D", "THRESH=2"],
    "llm_sched": [], "outcast": ["-D", "NA=2"], "pfc": [], "loom_isolation": [], "prio_load": [],
    "bursty_mdp": [], "draws_mdp": [], "fq_buggy_mdp_mixed": [],
}


def horizon(model: dict) -> int:
    t = [v for v in model["variables"] if v["name"] == "time"]
    return int(t[0]["type"]["upper-bound"]) if t else 30


def observables(model: dict) -> dict:
    obs = {}
    for p in model["properties"]:
        e = p["expression"]
        x = e["values"].get("exp") if isinstance(e, dict) and e.get("op") == "filter" else None
        if isinstance(x, dict) and x.get("op") == "U":
            obs[p["name"]] = {"op": "ite", "if": e["values"]["exp"]["right"], "then": 1, "else": 0}
    return obs


def run(model: dict, runs: int, T: int):
    m = JaniModel(model, observables=observables(model))
    r = m.simulate_rewards(runs, T, None, seed=7)
    hits = {k: int(((r.state_cumulative[k] > 0) | (r.final[k] > 0)).sum()) for k in r.final}
    return hits, r.cumulative


def main():
    names = sys.argv[1:] or list(EXAMPLES)
    fails = 0
    with tempfile.TemporaryDirectory() as d:
        for ex in names:
            src = ROOT / "buffy/examples/jani" / f"{ex}.buffy"
            flags = EXAMPLES.get(ex, [])
            pj, pn = Path(d) / f"{ex}.jani", Path(d) / f"{ex}_native.jani"
            subprocess.run([str(BUFFYC), str(src), *flags, "--layout", "sync", "-o", str(pj)], check=True, capture_output=True)
            subprocess.run([str(BUFFYC), str(src), *flags, "--target", "native", "-o", str(pn)], check=True, capture_output=True)
            mj, mn = json.loads(pj.read_text()), json.loads(pn.read_text())
            T = horizon(mj)
            hj, cj = run(mj, 20000, T)
            hn, cn = run(mn, 20000, T)
            same = hj == hn and set(cj) == set(cn) and all(np.array_equal(cj[k], cn[k]) for k in cj)
            fails += not same
            size = lambda p: p.stat().st_size / 1e3
            print(f"{'ok  ' if same else 'FAIL'} {ex}: {len(hj)} properties, {len(cj)} rewards; "
                  f"JANI {size(pj):.0f} kB, native {size(pn):.0f} kB" + ("" if same else f"\n   jani {hj}\n   native {hn}"),
                  flush=True)
    print(f"{len(names) - fails} of {len(names)} identical")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

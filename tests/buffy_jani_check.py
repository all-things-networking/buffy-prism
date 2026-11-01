"""
Runs the native JANI simulator on models emitted by the Buffy→JANI compiler (buffyc-mc, Buffy branch `features`) and
compares with modes reference estimates. MDPs are resolved uniformly over enabled edges. Properties of the form
filter(·, P(true U<=N goal), initial) are turned into native goals with horizon N.

The models are generated into experiments/buffy_jani/models/ by experiments/buffy_jani/make_models.sh (from the
buffy submodule; building it needs ANTLR: brew install antlr antlr4-cpp-runtime).

Usage: PYTHONPATH=. python tests/buffy_jani_check.py experiments/buffy_jani/models [runs] [file ...]
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel

# modes reference estimates (100k runs, -J 1) supplied by the Buffy-to-JANI session, 2026-11-01.
MODES_REF = {
    "bfy_p0.2": {"starve_violation": 0.00044, "cond_a_violation": 0.99813, "early_violation": 0.99775, "gap_violation": 1.0},
    "bfy_p0.2_staged": {"starve_violation": 0.00035, "cond_a_violation": 0.99828, "early_violation": 0.99803,
                        "gap_violation": 1.0},
    "bfy_p0.6": {"starve_violation": 0.01191, "cond_a_violation": 0.86697, "early_violation": 0.85722,
                 "gap_violation": 0.98953},
    "bfy_p0.6_staged": {"starve_violation": 0.01175, "cond_a_violation": 0.86894, "early_violation": 0.85917,
                        "gap_violation": 0.99009},
    # MDPs with queues 0-3 nondet(0,4) resolved uniformly (modes -R Uniform -N 100000 -J 1 --seed 1), 2026-11-01.
    "bfy_mdp_mixed_p0.2_choose": {"starve_violation": 0.00042, "cond_a_violation": 0.99818,
                                  "early_violation": 0.99781, "gap_violation": 1.0},
    "bfy_mdp_mixed_p0.6_choose": {"starve_violation": 0.01245, "cond_a_violation": 0.86641,
                                  "early_violation": 0.85595, "gap_violation": 0.98989},
    "bfy_mdp_mixed_p0.6_staged": {"starve_violation": 0.01245, "cond_a_violation": 0.86641,
                                  "early_violation": 0.85595, "gap_violation": 0.98989},
}


def reachability_properties(model: dict) -> dict[str, tuple[dict, int]]:
    """ name -> (goal expression, step bound) for properties filter(·, P(true U<=N goal), initial). """
    out = {}
    for p in model.get("properties", []):
        e = p["expression"]
        if not (isinstance(e, dict) and e.get("op") == "filter"):
            continue
        v = e["values"]
        if not (isinstance(v, dict) and v.get("op") in ("Pmin", "Pmax") and v["exp"].get("op") == "U"
                and v["exp"]["left"] is True and "step-bounds" in v["exp"]):
            continue
        out[p["name"]] = (v["exp"]["right"], int(v["exp"]["step-bounds"]["upper"]))
    return out


def check(path: Path, runs: int) -> dict:
    model = json.loads(path.read_text())
    props = reachability_properties(model)
    t = time.perf_counter()
    native = JaniModel(model, goals={n: g for n, (g, _) in props.items()})
    compile_s = time.perf_counter() - t
    result = {"file": path.name, "type": model["type"], "compile_s": compile_s, "edges": len(native.edges),
              "variables": len(native.variables), "transients": len(native.transients), "properties": {}}
    ref = MODES_REF.get(path.stem.replace("_imp", ""), {})
    weights = {a: 1.0 for a in native.edge_actions} if model["type"] == "mdp" else None
    for name, (_, bound) in props.items():
        t = time.perf_counter()
        hits, steps = native.simulate(runs, bound, name, weights, seed=1)
        dt = time.perf_counter() - t
        p = hits / runs
        half = 1.96 * np.sqrt(max(p * (1 - p), 1e-12) / runs)
        result["properties"][name] = {"estimate": p, "ci95_half": half, "us_per_run": dt / runs * 1e6,
                                      "ns_per_step": dt / max(steps, 1) * 1e9, "modes": ref.get(name)}
    return result


def main():
    directory = Path(sys.argv[1])
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 1_000_000
    files = sys.argv[3:] or ["bfy_p0.2.jani", "bfy_p0.2_staged.jani", "bfy_p0.6.jani", "bfy_p0.6_staged.jani"]
    for f in files:
        r = check(directory / f, runs)
        print(f"{r['file']} ({r['type']}): {r['edges']} edges, {r['variables']} state vars, {r['transients']} "
              f"transients, compiled in {r['compile_s']:.1f}s", flush=True)
        for name, s in r["properties"].items():
            ref = "" if s["modes"] is None else f"  modes {s['modes']:.5g}"
            print(f"   {name:18s} {s['estimate']:.5g} ± {s['ci95_half']:.2g}{ref}   {s['us_per_run']:.2f} µs/run "
                  f"({s['ns_per_step']:.0f} ns/step)", flush=True)


if __name__ == "__main__":
    main()

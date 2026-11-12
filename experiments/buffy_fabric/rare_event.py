"""
Axis 3 of the fabric scaling study: a rare bad event (P around 1e-5). Plain Monte Carlo against the native
simulator's RESTART splitting, with the importance function Buffy derives from the query (--auto-importance:
`<query>_imp`, here min(odrops, THRESH) or min(vdrops, VTH)) and levels and splitting factors chosen by expected
success (src/netmdp/sim/splitting.py) from pilot runs.

- RESTART: after the pilot, batches of RESTART runs until the 95% interval (normal, from the per-run estimates) has
  a relative half-width of at most REL, or the budget is spent.
- fixed effort: the same thresholds with a constant effort per level (EFFORT=n, default 1000), batches until the
  same precision or the same budget.
- Monte Carlo: batches of plain runs for `mc_budget` seconds; its estimate and 95% Clopper-Pearson interval, and the
  runs (and time, at the measured cost per run) it would need for the same relative half-width, taking P from the
  RESTART estimate.

With IMP=hand (query loss only), the importance is instead the derived one refined by the aggregator port's backlog,
min(odrops, THRESH) * (B + 1) + backlog(eg[0]). PILOT=n sets the pilot effort per level (default 1024), PILOTS=m the minimum number of pilots (default 64).

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_fabric/rare_event.py out.jsonl SIZE QUERY restart_budget mc_budget [NAME=value ...]
"""
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from fabric_lib import compile_fabric, horizon, query_pred, state_vars  # noqa: E402
from src.netmdp.hyptest.intervals import clopper_pearson  # noqa: E402
from src.netmdp.sim.jani_native import JaniModel  # noqa: E402
from src.netmdp.sim.splitting import NativeSplittingSampler, expected_success  # noqa: E402

BASE = dict(B=16, NCAP=8, SLEN=4, WIN=10, T=60, THRESH=10, VTH=1, LV=0.3, LB=0.05)
REL = 0.10


def main():
    out_path, size, q = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    restart_budget, mc_budget = float(sys.argv[4]), float(sys.argv[5])
    nl, h, ns = (int(x) for x in size.split("x"))
    d = dict(BASE, NL=nl, H=h, NS=ns)
    for kv in sys.argv[6:]:
        k, v = kv.split("=")
        d[k] = v
    hand = d.pop("IMP", "auto") == "hand"
    pilot = int(d.pop("PILOT", 1024))
    npilots = int(d.pop("PILOTS", 64))
    fe_effort = int(d.pop("EFFORT", 1000))
    run_restart = d.pop("RESTART", "1") != "0"   # RESTART=0: fixed effort only (RESTART's per-run effort is unbounded)
    with tempfile.TemporaryDirectory() as tmp:
        t = time.time()
        model, compile_s, _ = compile_fabric(d, Path(tmp) / "f.jani", flags=["--auto-importance"])
    T = horizon(model)
    imp = next(p["expression"] for p in model["properties"] if p["name"] == f"{q}_imp")
    top = int(d["THRESH"] if q == "loss" else d["VTH"])
    imp_name = f"min(odrops, {top})" if q == "loss" else f"min(vdrops, {top})"
    if hand and q == "loss":
        # the query's progress, refined by how full the aggregator's port is: odrops * (B + 1) + backlog(eg[0])
        b1 = int(d["B"]) + 1
        imp = {"op": "+", "left": {"op": "*", "left": {"op": "min", "left": "fabric_odrops", "right": top}, "right": b1},
               "right": "fabric_eg_0"}
        top, imp_name = top * b1, f"min(odrops, {top}) * {b1} + backlog(eg[0])"
    t = time.time()
    jm = JaniModel(model, goals={"goal": query_pred(model, q)}, importance={"imp": imp})
    build_s = time.time() - t
    res = {"size": size, "query": q, "defines": d, "state_vars": state_vars(model), "compile_s": round(compile_s, 2),
           "build_s": round(build_s, 2), "importance": imp_name, "pilot_effort": pilot, "min_pilots": npilots}
    print(f"{size} {q}: {res['state_vars']} vars, compile {compile_s:.1f} s, build {build_s:.1f} s", flush=True)

    # RESTART
    t0 = time.time()
    design = expected_success(jm, "goal", "imp", top, T, pilot_effort=pilot, seed=7, min_pilots=npilots)
    pilot_s = time.time() - t0
    res["restart_design"] = {"thresholds": design.thresholds, "factors": design.factors,
                             "p_up": [round(p, 5) for p in design.p_up], "pilot_s": round(pilot_s, 2)}
    print(f"  expected success: thresholds {design.thresholds}, factors {design.factors}, pilot {pilot_s:.1f} s",
          flush=True)
    sampler = NativeSplittingSampler(jm, "restart", design, "goal", "imp", T, seed=11)
    ests, t1, batch = [], time.time(), 2000
    while run_restart:
        ests.append(sampler.runs(batch))
        x = np.concatenate(ests)
        m, se = x.mean(), x.std(ddof=1) / np.sqrt(len(x))
        if (m > 0 and 1.96 * se <= REL * m) or time.time() - t1 > restart_budget:
            break
    rs_s = time.time() - t1
    if not run_restart:
        res["restart"] = {"skipped": "RESTART=0", "factor_product": float(np.prod(design.factors, dtype=float))}
        print(f"  RESTART skipped (factor product {res['restart']['factor_product']:.2e})", flush=True)
    else:
        res["restart"] = {"estimate": float(m), "ci95": [float(m - 1.96 * se), float(m + 1.96 * se)],
                          "rel_half_width": float(1.96 * se / m) if m > 0 else None, "runs": len(x),
                          "steps": int(sampler.steps), "seconds": round(rs_s, 1),
                          "seconds_with_pilot": round(rs_s + pilot_s, 1), "hits_nonzero": int((x > 0).sum())}
        print(f"  RESTART: {m:.3e} [{m - 1.96 * se:.3e}, {m + 1.96 * se:.3e}] (+-{100 * 1.96 * se / max(m, 1e-300):.1f}%) "
              f"from {len(x)} runs, {sampler.steps} steps, {rs_s:.0f} s (+ pilot {pilot_s:.0f} s)", flush=True)

    # fixed effort: the same thresholds, a constant effort per level (no factors to tune)
    eff = [fe_effort] * (len(design.thresholds) + 1)
    ests, t3, b = [], time.time(), 0
    fe_steps = 0
    while True:
        out, st = jm.fixed_effort(50, T, "goal", "imp", design.thresholds, eff, None, seed=5000 + b)
        ests.append(out)
        fe_steps, b = fe_steps + st, b + 1
        x = np.concatenate(ests)
        m, se = x.mean(), x.std(ddof=1) / np.sqrt(len(x))
        if (m > 0 and 1.96 * se <= REL * m) or time.time() - t3 > restart_budget:
            break
    fe_s = time.time() - t3
    res["fixed_effort"] = {"effort": fe_effort, "estimate": float(m), "ci95": [float(m - 1.96 * se), float(m + 1.96 * se)],
                           "rel_half_width": float(1.96 * se / m) if m > 0 else None, "runs": len(x),
                           "steps": int(fe_steps), "seconds": round(fe_s, 1)}
    print(f"  fixed effort ({fe_effort}/level): {m:.3e} [{m - 1.96 * se:.3e}, {m + 1.96 * se:.3e}] "
          f"(+-{100 * 1.96 * se / max(m, 1e-300):.1f}%) from {len(x)} runs, {fe_steps} steps, {fe_s:.0f} s", flush=True)

    # plain Monte Carlo
    hits = n = steps = 0
    t2, b = time.time(), 0
    while time.time() - t2 < mc_budget:
        k, st = jm.simulate(200_000, T, "goal", None, seed=1000 + b)
        hits, n, steps, b = hits + k, n + 200_000, steps + st, b + 1
    mc_s = time.time() - t2
    lo, hi = clopper_pearson(hits, n, 0.95)
    p_ref = res["restart"].get("estimate") or res["fixed_effort"]["estimate"]
    n_req = int(np.ceil(1.96 ** 2 * (1 - p_ref) / (REL ** 2 * p_ref))) if p_ref > 0 else None
    res["mc"] = {"hits": hits, "runs": n, "steps": int(steps), "seconds": round(mc_s, 1), "estimate": hits / n,
                 "ci95": [lo, hi], "per_run_us": round(1e6 * mc_s / n, 2),
                 "runs_for_rel": n_req, "seconds_for_rel": round(n_req * mc_s / n, 0) if n_req else None}
    print(f"  MC: {hits}/{n} = {hits / n:.3e} [{lo:.3e}, {hi:.3e}] in {mc_s:.0f} s; +-{100 * REL:.0f}% would need "
          f"{n_req} runs, about {res['mc']['seconds_for_rel']} s", flush=True)
    if res["mc"]["seconds_for_rel"]:
        if run_restart:
            res["speedup_time"] = round(res["mc"]["seconds_for_rel"] / res["restart"]["seconds_with_pilot"], 1)
            res["speedup_steps"] = round(n_req * (steps / n) / max(res["restart"]["steps"], 1), 1)
        fe = res["fixed_effort"]
        if fe["rel_half_width"]:
            # time for +-REL at the observed variance: seconds * (observed half-width / REL)^2
            fe_need = fe["seconds"] * (fe["rel_half_width"] / REL) ** 2
            rs = res["restart"]
            rs_need = rs["seconds"] * (rs["rel_half_width"] / REL) ** 2 + pilot_s if rs.get("rel_half_width") else None
            res["seconds_for_rel"] = {"mc": res["mc"]["seconds_for_rel"], "restart": round(rs_need, 1) if rs_need else None,
                                      "fixed_effort": round(fe_need, 1)}
    with out_path.open("a") as f:
        f.write(json.dumps(res) + "\n")


if __name__ == "__main__":
    main()

"""
The rare-event axis, replicated: Monte Carlo against RESTART and fixed effort, with the derived importance
(--auto-importance) and the refined one (odrops * (B+1) + backlog of the aggregator's port), over several seeds.
Levels and factors come from expected_success with pilot weighting (splitting.py); the design and the pilot's
estimate of P are recorded per importance.

Each (importance, method, seed) runs for BUDGET seconds in batches sized to take about 20 s, so the budget holds
within one batch. Per-run estimates are saved (sparse: indices and values of the non-zero runs) in
results/rare_event_runs/*.npz. Per cell: estimate, normal 95% half-width, time for a +-10% half-width at the
observed variance (seconds * (half-width / 10%)^2, plus the whole pilot), and the share of the sum carried by the top 5
runs (heavy tails). Monte Carlo is measured for its cost per run; its time for +-10% uses the equal-weight mean of
the splitting cells' estimates of P.

  PYTHONPATH=. python experiments/buffy_fabric/rare_event_seeds.py OUT.jsonl SIZE [NAME=value ...]
  NAME: SEEDS (3), BUDGET (300 s), MC (120 s), EFFORT (fixed effort per level, 1000),
        PILOTS_AUTO / EFFORT_AUTO (256 / 1024), PILOTS_HAND / EFFORT_HAND (256 / 256), and Buffy -D values.
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

BASE = dict(B=16, NCAP=8, SLEN=4, WIN=10, T=60, THRESH=6, VTH=1, LV=0.3, LB=0.05)
REL = 0.10
OPTS = dict(SEEDS=3, BUDGET=300.0, MC=120.0, EFFORT=1000, PILOTS_AUTO=256, EFFORT_AUTO=1024, PILOTS_HAND=256,
            EFFORT_HAND=256)


def summarise(x: np.ndarray, seconds: float, extra_s: float = 0.0) -> dict:
    m, se = float(x.mean()), float(x.std(ddof=1) / np.sqrt(len(x)))
    hw = 1.96 * se / m if m > 0 else None
    top = np.sort(x)[::-1]
    return {"estimate": m, "ci95": [m - 1.96 * se, m + 1.96 * se], "rel_half_width": hw, "runs": int(len(x)),
            "nonzero": int((x > 0).sum()), "top5_share": float(top[:5].sum() / x.sum()) if x.sum() > 0 else None,
            "seconds": round(seconds, 1),
            "seconds_for_rel": round(seconds * (hw / REL) ** 2 + extra_s, 1) if hw else None}


def timed_batches(run_batch, budget: float, first: int):
    """ run_batch(n) -> (per-run estimates, steps); batches grow to about 20 s each until the budget is spent. """
    xs, steps, n, t0 = [], 0, first, time.time()
    while time.time() - t0 < budget:
        t = time.time()
        x, st = run_batch(n)
        xs.append(x)
        steps += st
        dt = max(time.time() - t, 1e-3)
        left = budget - (time.time() - t0)
        n = int(max(1, min(n * 20.0 / dt, n * left / dt, 4 * n)))
    return np.concatenate(xs), steps, time.time() - t0


def main():
    out_path, size = Path(sys.argv[1]), sys.argv[2]
    nl, h, ns = (int(x) for x in size.split("x"))
    d, o = dict(BASE, NL=nl, H=h, NS=ns), dict(OPTS)
    for kv in sys.argv[3:]:
        k, v = kv.split("=")
        (o if k in o else d)[k] = type(o[k])(v) if k in o else v
    runs_dir = out_path.parent / "rare_event_runs"
    runs_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        model, compile_s, _ = compile_fabric(d, Path(tmp) / "f.jani", flags=["--auto-importance"])
    T, top, b1 = horizon(model), int(d["THRESH"]), int(d["B"]) + 1
    imps = {
        "derived": (next(p["expression"] for p in model["properties"] if p["name"] == "loss_imp"), top,
                    f"min(odrops, {top})", o["PILOTS_AUTO"], o["EFFORT_AUTO"]),
        "refined": ({"op": "+", "left": {"op": "*", "left": {"op": "min", "left": "fabric_odrops", "right": top},
                                          "right": b1}, "right": "fabric_eg_0"}, top * b1,
                    f"min(odrops, {top}) * {b1} + backlog(eg[0])", o["PILOTS_HAND"], o["EFFORT_HAND"]),
    }
    t = time.time()
    jm = JaniModel(model, goals={"goal": query_pred(model, "loss")}, importance={k: v[0] for k, v in imps.items()})
    head = {"size": size, "defines": d, "options": o, "state_vars": state_vars(model), "compile_s": round(compile_s, 2),
            "build_s": round(time.time() - t, 2)}
    print(f"{size}: {head['state_vars']} vars, build {head['build_s']} s", flush=True)
    rows = []

    # Monte Carlo: cost per run and hits
    hits = n = 0
    t0, b = time.time(), 0
    while time.time() - t0 < o["MC"]:
        k, _ = jm.simulate(100_000, T, "goal", None, seed=7000 + b)
        hits, n, b = hits + k, n + 100_000, b + 1
    mc_s = time.time() - t0
    lo, hi = clopper_pearson(hits, n, 0.95)
    mc = {"kind": "mc", "hits": hits, "runs": n, "seconds": round(mc_s, 1), "estimate": hits / n, "ci95": [lo, hi],
          "per_run_us": round(1e6 * mc_s / n, 2)}
    print(f"  MC: {hits}/{n} in {mc_s:.0f} s ({mc['per_run_us']} us/run)", flush=True)

    for name, (_, top_imp, desc, pilots, peff) in imps.items():
        t0 = time.time()
        design = expected_success(jm, "goal", name, top_imp, T, pilot_effort=peff, seed=11, min_pilots=pilots)
        pilot_s = time.time() - t0
        p_hat, fprod = float(np.prod(design.p_up[:-1])), float(np.prod(design.factors, dtype=float))
        des = {"kind": "design", "importance": name, "expression": desc, "pilots": pilots, "pilot_effort": peff,
               "pilot_s": round(pilot_s, 1), "thresholds": design.thresholds, "factors": design.factors,
               "p_up": [round(p, 5) for p in design.p_up], "p_hat": p_hat, "factor_product": fprod}
        rows.append(des)
        print(f"  {name}: pilot {pilot_s:.0f} s, P^ {p_hat:.3e}, {len(design.thresholds)} thresholds, factor product "
              f"{fprod:.3e} (x P^ = {fprod * p_hat:.2f})\n    thresholds {design.thresholds}\n    factors {design.factors}",
              flush=True)
        eff = [o["EFFORT"]] * (len(design.thresholds) + 1)
        for seed in range(1, o["SEEDS"] + 1):
            for method in ("restart", "fixed_effort"):
                if method == "restart":
                    smp = NativeSplittingSampler(jm, "restart", design, "goal", name, T, seed=100 * seed)
                    def batch(k, smp=smp):
                        s0 = smp.steps
                        x = smp.runs(k)
                        return x, smp.steps - s0
                    first = 200
                else:
                    cnt = [0]
                    def batch(k, cnt=cnt, seed=seed):
                        cnt[0] += 1
                        return jm.fixed_effort(k, T, "goal", name, design.thresholds, eff, None,
                                               seed=1_000_000 * seed + cnt[0])
                    first = 5
                x, steps, secs = timed_batches(batch, o["BUDGET"], first)
                nz = np.flatnonzero(x)
                np.savez_compressed(runs_dir / f"{size}_{name}_{method}_seed{seed}.npz", n=len(x), idx=nz, val=x[nz])
                r = dict(kind="run", importance=name, method=method, seed=seed, steps=int(steps),
                         **summarise(x, secs, pilot_s))
                rows.append(r)
                print(f"  {name} {method} seed {seed}: {r['estimate']:.3e} +-{100 * (r['rel_half_width'] or 0):.0f}% "
                      f"({r['runs']} runs, {r['nonzero']} non-zero, top-5 share {r['top5_share']}), "
                      f"for +-10%: {r['seconds_for_rel']} s", flush=True)

    # pooled P: the equal-weight mean of the splitting cells (each unbiased; weights estimated from heavy-tailed
    # data would favour the cells that came out low), and Monte Carlo's time for +-10% at that P
    cells = [r for r in rows if r["kind"] == "run" and r["rel_half_width"]]
    est = np.array([r["estimate"] for r in cells])
    p_pool = float(est.mean())
    n_req = int(np.ceil(1.96 ** 2 * (1 - p_pool) / (REL ** 2 * p_pool)))
    mc.update(p_pooled=p_pool, p_pooled_se=float(est.std(ddof=1) / np.sqrt(len(est))), runs_for_rel=n_req,
              seconds_for_rel=round(n_req * mc["per_run_us"] * 1e-6, 0))
    rows.insert(0, mc)
    print(f"  pooled P {p_pool:.3e}; MC needs {n_req} runs, {mc['seconds_for_rel']} s for +-10%", flush=True)
    for name in imps:
        for method in ("restart", "fixed_effort"):
            t = [r["seconds_for_rel"] for r in cells if r["importance"] == name and r["method"] == method]
            if t:
                sp = sorted(mc["seconds_for_rel"] / x for x in t)
                print(f"  {name} {method}: speed-up over MC per seed {[round(s, 2) for s in sp]}", flush=True)
    with out_path.open("a") as f:
        f.write(json.dumps({**head, "rows": rows}) + "\n")


if __name__ == "__main__":
    main()

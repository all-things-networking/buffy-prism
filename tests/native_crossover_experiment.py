"""
Where does importance splitting beat SPRT? For goals iq5_deqs_bl > k with k beyond the course experiments, set the
hypothesis at the same relative position as STAT 535C Experiment 3 (θ = p/2.73, ζ = 2θ/3, p estimated by native
RESTART first) and compare base SMC + SPRT with native RESTART + anytime Chow-Robbins (Weibull traffic).

Usage: PYTHONPATH=. python tests/native_crossover_experiment.py [reps] [k ...]
Writes tests/modes/results/native_crossover.json.
"""
import contextlib
import io
import json
import sys
import time
from pathlib import Path

import numpy as np

from src.netmdp.hyptest.chow_robbins import ChowRobbins
from src.netmdp.hyptest.hyptest import ErrTols
from src.netmdp.hyptest.wald_sprt import WaldSprt
from src.netmdp.sim.jani_native import JaniModel
from src.netmdp.sim.splitting import NativeSplittingSampler, expected_success
from tests.native_splitting_experiment import BASE, HORIZON, MDP, WEIGHTS, per_run_cost, run


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    ks = [int(a) for a in sys.argv[2:]] or [8, 9, 10, 11]
    results = {}
    for k in ks:
        model = JaniModel(MDP, goals={"goal": {"op": ">", "left": "iq5_deqs_bl", "right": k}},
                          importance={"imp": {"op": "min", "left": "iq5_deqs_bl", "right": k + 1}})
        design = expected_success(model, "goal", "imp", k + 1, HORIZON, WEIGHTS, pilot_effort=256, seed=k)
        ref, _ = model.restart(400_000, HORIZON, "goal", "imp", design.thresholds, design.factors, WEIGHTS, seed=k)
        p, p_se = ref.mean(), ref.std(ddof=1) / np.sqrt(len(ref))
        theta = p / 2.73
        zeta = 2 * theta / 3
        errs = ErrTols(0.05, 0.05)
        base = NativeSplittingSampler(model, "fixed_effort", BASE, "goal", "imp", HORIZON, WEIGHTS, 1, seed=10 * k)
        rs = NativeSplittingSampler(model, "restart", design, "goal", "imp", HORIZON, WEIGHTS, seed=20 * k)
        cost = {"base": per_run_cost(base), "RESTART": per_run_cost(rs)}
        out = {}
        for name, test, sampler in [("base/SPRT", WaldSprt(theta, errs, zeta, None), base),
                                    ("RESTART/CR-anytime", ChowRobbins(theta, errs, zeta, None), rs)]:
            with contextlib.redirect_stdout(io.StringIO()):   # WaldSprt prints progress every 10k samples
                rows = [run(test, sampler, cost["base" if sampler is base else "RESTART"]) for _ in range(reps)]
            out[name] = {"P(H+)": float(np.mean([r["decision"] == "+" for r in rows])),
                         "runs": float(np.mean([r["runs"] for r in rows])),
                         "wall_s": float(np.mean([r["wall_s"] for r in rows])),
                         "sim_s": float(np.mean([r["sim_s"] for r in rows]))}
        results[k] = {"p": p, "p_se": p_se, "theta": theta, "zeta": zeta, "design": design.__dict__,
                      "cost_per_run_us": {n: c * 1e6 for n, c in cost.items()}, "tests": out}
        print(f"k={k}: p≈{p:.3g}±{1.96 * p_se:.1g}, θ={theta:.3g}, ζ={zeta:.3g}, levels {design.thresholds} "
              f"factors {design.factors}", flush=True)
        for name, s in out.items():
            print(f"   {name:20s} H+ {s['P(H+)']:.2f} runs {s['runs']:11,.0f} wall {s['wall_s']:8.3f} s "
                  f"native sim {s['sim_s']:8.3f} s", flush=True)
        Path("tests/modes/results/native_crossover.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()

"""
STAT 535C hypothesis tests at native speed: SPRT and anytime Chow-Robbins on base SMC, and anytime Chow-Robbins on
native RESTART and weighted fixed effort (expected-success levels), Weibull traffic, all on the compiled JANI model.

Per test: decision frequencies, runs used, and time (wall time of the whole test, Python test loop included, and the
native simulation time alone = runs x measured cost per run). Usage:
    PYTHONPATH=. python tests/native_splitting_experiment.py [reps]
Writes tests/modes/results/native_splitting.json.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from src.netmdp.hyptest.chow_robbins import ChowRobbins
from src.netmdp.hyptest.hyptest import ErrTols, HypResult
from src.netmdp.hyptest.wald_sprt import WaldSprt
from src.netmdp.sim.jani_native import JaniModel
from src.netmdp.sim.scheduler import WEIBULL_TRAFFIC
from src.netmdp.sim.splitting import NativeSplittingSampler, SplittingDesign, expected_success

MDP = "tests/modes/fqcodel_5i_mdp_535c.jani"
HORIZON = 154
WEIGHTS = {f"REC_PKT_ARR_IQ{q}_K{k}": w for q in range(1, 6) for k, w in enumerate(WEIBULL_TRAFFIC)}
EXPERIMENTS = {1: (2, 0.70, 0.01), 2: (4, 0.011, 0.001), 3: (8, 0.00015, 0.0001)}
BASE = SplittingDesign([], [], [])   # fixed effort with no thresholds and effort 1 = one base Monte Carlo run


def run(test, sampler, cost_per_run: float) -> dict:
    t = time.perf_counter()
    r = test.run_test(sampler)
    return {"decision": {HypResult.ACCEPT_H_PLUS: "+", HypResult.ACCEPT_H_MINUS: "-"}.get(r.get_result(), "I"),
            "runs": r.get_n(), "wall_s": time.perf_counter() - t, "sim_s": r.get_n() * cost_per_run,
            "estimate": r.get_sample_mean()}


def per_run_cost(sampler: NativeSplittingSampler, n: int = 20000) -> float:
    t = time.perf_counter()
    sampler.runs(n)
    return (time.perf_counter() - t) / n


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    errs, results = ErrTols(0.05, 0.05), {}
    for e, (k, theta, zeta) in EXPERIMENTS.items():
        model = JaniModel(MDP, goals={"goal": {"op": ">", "left": "iq5_deqs_bl", "right": k}},
                          importance={"imp": {"op": "min", "left": "iq5_deqs_bl", "right": k + 1}})
        design = expected_success(model, "goal", "imp", k + 1, HORIZON, WEIGHTS, pilot_effort=256, seed=e)
        samplers = {
            "base": NativeSplittingSampler(model, "fixed_effort", BASE, "goal", "imp", HORIZON, WEIGHTS, 1, seed=100 * e),
            "RESTART": NativeSplittingSampler(model, "restart", design, "goal", "imp", HORIZON, WEIGHTS, seed=200 * e),
            "WFE(8)": NativeSplittingSampler(model, "fixed_effort", design, "goal", "imp", HORIZON, WEIGHTS, 8,
                                             seed=300 * e)}
        cost = {name: per_run_cost(s) for name, s in samplers.items()}
        configs = {"base/SPRT": (WaldSprt(theta, errs, zeta, None), "base"),
                   "base/CR-anytime": (ChowRobbins(theta, errs, zeta, None), "base"),
                   "RESTART/CR-anytime": (ChowRobbins(theta, errs, zeta, None), "RESTART"),
                   "WFE(8)/CR-anytime": (ChowRobbins(theta, errs, zeta, None), "WFE(8)")}
        rows = {name: [run(test, samplers[s], cost[s]) for _ in range(reps)] for name, (test, s) in configs.items()}
        summary = {name: {"P(H+)": float(np.mean([r["decision"] == "+" for r in rs])),
                          "P(H-)": float(np.mean([r["decision"] == "-" for r in rs])),
                          "runs": float(np.mean([r["runs"] for r in rs])),
                          "wall_s": float(np.mean([r["wall_s"] for r in rs])),
                          "sim_s": float(np.mean([r["sim_s"] for r in rs]))} for name, rs in rows.items()}
        results[e] = {"k": k, "theta": theta, "zeta": zeta, "design": design.__dict__,
                      "cost_per_run_us": {n: c * 1e6 for n, c in cost.items()}, "summary": summary}
        print(f"\nExperiment {e}: P(deqs>{k}) vs θ={theta}, ζ={zeta}; levels {design.thresholds} factors "
              f"{design.factors}; µs/run " + ", ".join(f"{n} {c * 1e6:.1f}" for n, c in cost.items()))
        for name, s in summary.items():
            print(f"  {name:20s} H+ {s['P(H+)']:.2f}  H- {s['P(H-)']:.2f}  runs {s['runs']:9,.0f}  "
                  f"wall {s['wall_s'] * 1e3:8.1f} ms  native sim {s['sim_s'] * 1e3:8.1f} ms")
    Path("tests/modes/results/native_splitting.json").write_text(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()

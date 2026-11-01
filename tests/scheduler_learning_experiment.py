"""
Scheduler learning on the STAT 535C FQ-CoDel MDP (tests/modes/fqcodel_5i_mdp_535c.jani), native JANI backend:

1. Witness search: step-aware tabular Q-learning (reverse-order episode updates) for "iq5_deqs_bl > k within 154
   steps". The MDP has no probabilistic branching, so a successful greedy policy is a witness trace.
2. Distribution learning: cross-entropy method for an adversarial i.i.d. per-queue arrival distribution.
3. The learned distribution is exported as the induced DTMC (JANI) and evaluated with modes (RESTART + Chow-Robbins),
   next to a native Monte Carlo estimate.

Usage: PYTHONPATH=. python tests/scheduler_learning_experiment.py
Writes tests/modes/results/scheduler_learning.json and tests/modes/results/fqcodel_5i_ce_dtmc_535c.jani.
"""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from src.netmdp.learn.cross_entropy import cross_entropy_scheduler
from src.netmdp.learn.shaped_qlearning import ShapedQLearning
from src.netmdp.sim.export import induced_dtmc_jani
from src.netmdp.sim.jani_native import JaniModel
from src.netmdp.sim.scheduler import Rollout, arrival_count_scheduler, WEIBULL_TRAFFIC
from src.netmdp.sim.simulator import NativeJaniSimulator

MODES = os.environ.get("MODES", "/Users/jkai/buffy-prism/Modest/modest")
MDP = Path("tests/modes/fqcodel_5i_mdp_535c.jani")
RESULTS = Path("tests/modes/results")
HORIZON, K = 154, 8   # goal: iq5_deqs_bl > K (four times the fair share)


def witness_search(episodes: int = 20000) -> dict:
    sim = NativeJaniSimulator(MDP)
    goal = lambda s: s.get("iq5_deqs_bl") > K
    ql = ShapedQLearning(sim, goal, HORIZON, arrival_count_scheduler(WEIBULL_TRAFFIC), alpha=0.5, epsilon=0.1)
    t = time.perf_counter()
    log = ql.train(episodes, np.random.default_rng(1), log_every=1000, stop_after_success_rate=0.85)
    ro = Rollout(sim, ql.greedy_scheduler(), np.random.default_rng(2))
    ro.reset()
    arrivals, ok = [], False
    while not (ok := goal(sim)) and sim.t < HORIZON:
        a = ro.step()
        if a is None:
            break
        if "_K" in a:
            arrivals.append(a)
    return {"episodes": log.episodes, "seconds": time.perf_counter() - t, "first_success": log.first_success,
            "greedy_reaches_goal": ok, "steps": sim.t, "witness_arrivals": arrivals}


def learn_distribution() -> dict:
    model = JaniModel(MDP)
    groups = {f"IQ{q}": [f"REC_PKT_ARR_IQ{q}_K{k}" for k in range(5)] for q in range(1, 6)}
    nominal = {f"REC_PKT_ARR_IQ{q}_K{k}": w for q in range(1, 6) for k, w in enumerate(WEIBULL_TRAFFIC)}
    t = time.perf_counter()
    res = cross_entropy_scheduler(model, groups, nominal, "iq5_deqs_bl", target=K + 1, horizon=HORIZON,
                                  n_runs=20000, rho=0.05, iterations=25, seed=1)
    return {"seconds": time.perf_counter() - t, "weights": res.weights, "history": res.history,
            "per_queue": {g: [round(res.weights[a], 4) for a in acts] for g, acts in groups.items()},
            "scheduler": res.scheduler()}


def evaluate(scheduler, name: str) -> dict:
    dtmc = induced_dtmc_jani(json.loads(MDP.read_text()), scheduler, name_suffix=f"_{name}")
    path = RESULTS / f"fqcodel_5i_{name}_dtmc_535c.jani"
    path.write_text(json.dumps(dtmc, indent=1))
    native = JaniModel(dtmc, {"goal": {"op": ">", "left": "iq5_deqs_bl", "right": K}})
    n = 2_000_000
    hits, _ = native.simulate(n, HORIZON, "goal", seed=11)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    subprocess.run([MODES, "modes", str(path), "--props", f"p_gt{K}", "--rare", "Restart", "--levels", "ExpectedSuccess",
                    "--ifun-prop", "imp", "0", str(K + 1), "--statistics", "ChowRobbins", "-W", "0.02",
                    "--relative-width", "-C", "0.95", "-J", "4", "--seed", "5", "-O", out, "Json", "-Y"],
                   check=True, capture_output=True)
    prop = json.loads(Path(out).read_text())["data"][0]["data"][0]
    os.unlink(out)
    values = {v["name"]: v["value"] for v in prop["values"]}
    return {"jani": str(path), "native_mc": {"runs": n, "estimate": hits / n},
            "modes_restart": {"estimate": prop["value"], "ci95": values.get("Confidence interval"),
                              "runs": values.get("Runs used")}}


def main():
    RESULTS.mkdir(exist_ok=True)
    out = {"goal": f"iq5_deqs_bl > {K} within {HORIZON} steps"}
    out["witness"] = witness_search()
    print("witness search:", {k: v for k, v in out["witness"].items() if k != "witness_arrivals"})
    ce = learn_distribution()
    out["cross_entropy"] = {k: v for k, v in ce.items() if k != "scheduler"}
    print("CE per-queue P(k arrivals):", ce["per_queue"])
    out["evaluation"] = {"weibull": evaluate(arrival_count_scheduler(WEIBULL_TRAFFIC), "weibull"),
                         "cross_entropy": evaluate(ce["scheduler"], "ce")}
    print("evaluation:", json.dumps(out["evaluation"], indent=1))
    (RESULTS / "scheduler_learning.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()

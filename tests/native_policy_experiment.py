"""
Rare-event evaluation of a learned, state- and step-dependent scheduler with the native simulator, on the Buffy
emitter's mixed fq_buggy MDP (choose layout, P0 = 0.2: queues 0-3 adversarial, queue 4 random):

1. Step-aware tabular Q-learning of an adversary for starve_violation (uniform behaviour scheduler).
2. Its greedy policy evaluated four ways: the Python Rollout path, the native callback (greedy_scheduler() called
   from C), the native table (greedy_native_policy()), and native RESTART under the table with expected-success levels
   on fq_deqs_bl. Uniform resolution is the baseline.

Usage: PYTHONPATH=. python tests/native_policy_experiment.py experiments/buffy_jani/models [episodes]
Writes tests/modes/results/native_policy.json.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from src.netmdp.learn.shaped_qlearning import ShapedQLearning
from src.netmdp.sim.jani_native import JaniModel
from src.netmdp.sim.scheduler import Rollout, UniformScheduler, native_policy
from src.netmdp.sim.simulator import NativeJaniSimulator
from src.netmdp.sim.splitting import expected_success
from tests.buffy_jani_check import reachability_properties

MODEL, PROPERTY = "bfy_mdp_mixed_p0.2_choose.jani", "starve_violation"


def mc(hits: int, n: int) -> dict:
    p = hits / n
    return {"estimate": p, "ci95_half": 1.96 * np.sqrt(max(p * (1 - p), 1e-12) / n), "runs": n}


def timed(f):
    t = time.perf_counter()
    out = f()
    return out, time.perf_counter() - t


def main():
    directory = Path(sys.argv[1])
    episodes = int(sys.argv[2]) if len(sys.argv) > 2 else 20000
    jani = json.loads((directory / MODEL).read_text())
    goal, horizon = reachability_properties(jani)[PROPERTY]
    model = JaniModel(jani, goals={"goal": goal}, importance={"imp": {"op": "min", "left": "fq_deqs_bl", "right": 4}})
    sim = NativeJaniSimulator(model)
    ql = ShapedQLearning(sim, lambda s: model.goal(s.state, "goal"), horizon, UniformScheduler(), alpha=0.3,
                         epsilon=0.2)
    log, train_s = timed(lambda: ql.train(episodes, np.random.default_rng(1), log_every=episodes // 10))
    table, table_s = timed(ql.greedy_native_policy)
    greedy = ql.greedy_scheduler()
    callback = native_policy(model, greedy)
    out = {"model": MODEL, "property": PROPERTY, "horizon": horizon,
           "training": {"episodes": log.episodes, "seconds": train_s, "q_states": len(ql.q),
                        "success_curve": log.success_curve},
           "table": {"rows": table.rows, "build_seconds": table_s}, "estimates": {}, "cost_ns_per_step": {}}
    print(f"Q-learning: {log.episodes} episodes in {train_s:.0f} s, {len(ql.q)} states; table {table.rows} rows "
          f"built in {table_s:.1f} s", flush=True)

    # Python Rollout path (the reference semantics of greedy_scheduler)
    n_py, rng, hits, steps = 20_000, np.random.default_rng(3), 0, 0
    ro = Rollout(sim, greedy, rng)
    t = time.perf_counter()
    for _ in range(n_py):
        ro.reset()
        hits += ro.run(horizon, lambda s: model.goal(s.state, "goal"))
        steps += sim.t
    out["estimates"]["python_rollout"] = mc(hits, n_py)
    out["cost_ns_per_step"]["python_rollout"] = (time.perf_counter() - t) / steps * 1e9

    for name, pol, n in [("uniform", None, 2_000_000), ("native_table", table, 2_000_000),
                         ("native_callback", callback, 100_000)]:
        (h, st), dt = timed(lambda: model.simulate(n, horizon, "goal", pol, seed=4))
        out["estimates"][name] = mc(h, n)
        out["cost_ns_per_step"][name] = dt / st * 1e9

    design, design_s = timed(lambda: expected_success(model, "goal", "imp", 4, horizon, table, pilot_effort=256,
                                                      seed=5))
    (est, st), dt = timed(lambda: model.restart(200_000, horizon, "goal", "imp", design.thresholds, design.factors,
                                                table, seed=6))
    se = est.std(ddof=1) / np.sqrt(len(est))
    out["estimates"]["native_table_restart"] = {"estimate": est.mean(), "ci95_half": 1.96 * se, "runs": len(est),
                                                "thresholds": design.thresholds, "factors": design.factors,
                                                "design_seconds": design_s, "seconds": dt}
    out["cost_ns_per_step"]["native_table_restart"] = dt / st * 1e9
    # work-normalised variance ratio of RESTART to plain Monte Carlo under the same policy (lower is better)
    p = out["estimates"]["native_table"]["estimate"]
    mc_s_per_run = out["cost_ns_per_step"]["native_table"] * 1e-9 * horizon
    out["restart_vs_mc_work_variance_ratio"] = (est.var(ddof=1) * dt / len(est)) / (p * (1 - p) * mc_s_per_run)

    for name, e in out["estimates"].items():
        print(f"   {name:22s} {e['estimate']:.3e} ± {e['ci95_half']:.1e}  ({e['runs']:,} runs, "
              f"{out['cost_ns_per_step'][name]:,.0f} ns/step)", flush=True)
    print(f"   RESTART levels {design.thresholds} factors {design.factors}; work-normalised variance vs MC: "
          f"{out['restart_vs_mc_work_variance_ratio']:.3f}")
    Path("tests/modes/results/native_policy.json").write_text(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()

"""
Tests of state- and step-dependent schedulers in the native batch simulators (NativePolicy in
src/netmdp/sim/jani_native.py), on the toy MDP tests/models/sync_toy.pm (640 states), where the exact probability of a
step-bounded goal under a policy can be computed by backward induction over (state, t). Only for toy models: exact
computation is out of the question for the network models.

- test_table_policy_exact: a random stochastic table policy over (state, t), with table misses and all-zero rows
  that fall back to default action weights (and to uniform where those are zero too). Plain Monte Carlo, RESTART and
  fixed effort under it must agree with the exact value (|error| < 4.5 standard errors).
- test_callback_equals_table: the same policy as a Python callback gives bit-identical results (same seed), and so
  does a projected table (key on some variables, no step count) against an equivalent callback.
- test_callback_errors: an exception in a callback is re-raised by the batch call.
- test_qlearning_policy: a step-aware Q-learner's greedy policy, as a native table and as a callback built from
  greedy_scheduler(), gives identical results, and agrees with the exact value of that policy.

Usage: PYTHONPATH=. python tests/test_native_policy.py
"""
import json

import numpy as np
import stormpy

from src.netmdp.learn.shaped_qlearning import ShapedQLearning
from src.netmdp.sim.jani_native import JaniModel, NativePolicy
from src.netmdp.sim.scheduler import ActionWeightScheduler, native_policy
from src.netmdp.sim.simulator import NativeJaniSimulator

TOY = "tests/models/sync_toy.pm"
HORIZON = 25
GOAL = {"op": "≥", "left": {"op": "+", "left": "c", "right": "c2"}, "right": 5}
IMPORTANCE = {"op": "min", "left": {"op": "+", "left": "c", "right": "c2"}, "right": 5}
DEFAULT = {"produce": 3.0, "handoff": 1.0, "consume": 0.5, "consume2": 0.5}   # silent edges weigh 0


def toy_model() -> JaniModel:
    jani, _ = stormpy.parse_prism_program(TOY).to_jani([])
    return JaniModel(json.loads(str(jani)), goals={"goal": GOAL}, importance={"imp": IMPORTANCE})


def reachable(model: JaniModel) -> dict[bytes, np.ndarray]:
    s0 = model.initial_state()
    seen, todo = {s0.tobytes(): s0}, [s0]
    while todo:
        s = todo.pop()
        for e in model.enabled_edges(s):
            for p, t in model.successors(s, int(e)):
                if p > 0 and t.tobytes() not in seen:
                    seen[t.tobytes()] = t
                    todo.append(t)
    return seen


def effective(model: JaniModel, row_weights, enabled: np.ndarray) -> np.ndarray:
    """ The C fallback rule: row weights if they sum > 0, else default weights if > 0, else uniform. """
    w = np.zeros(len(enabled)) if row_weights is None else np.asarray(row_weights, dtype=float)
    if w.sum() <= 0:
        w = np.array([DEFAULT.get(model.edge_actions[e], 0.0) for e in enabled])
    if w.sum() <= 0:
        w = np.ones(len(enabled))
    return w / w.sum()


def exact(model: JaniModel, states: dict[bytes, np.ndarray], dist) -> float:
    """ P(goal within HORIZON) under the policy dist(state, t, enabled) -> probabilities, by backward induction. """
    goal = {k: model.goal(s, "goal") for k, s in states.items()}
    enabled = {k: model.enabled_edges(s) for k, s in states.items()}
    succ = {(k, int(e)): [(p, t.tobytes()) for p, t in model.successors(s, int(e)) if p > 0]
            for k, s in states.items() for e in enabled[k]}
    v = {k: float(goal[k]) for k in states}                     # V_H
    for t in range(HORIZON - 1, -1, -1):
        nv = {}
        for k, s in states.items():
            en = enabled[k]
            if goal[k] or len(en) == 0:
                nv[k] = float(goal[k])
                continue
            pi = dist(s, t, en) if len(en) > 1 else [1.0]
            nv[k] = sum(pe * sum(p * v[n] for p, n in succ[(k, int(e))]) for pe, e in zip(pi, en))
        v = nv
    return v[model.initial_state().tobytes()]


def random_table(model: JaniModel, states, rng) -> dict[tuple, dict[int, float]]:
    rows = {}
    for s in states.values():
        en = model.enabled_edges(s)
        if len(en) < 2:
            continue
        for t in range(HORIZON):
            u = rng.random()
            if u < 0.3:
                continue                                         # miss: default weights
            w = np.zeros(len(en)) if u < 0.4 else rng.random(len(en)) ** 3
            rows[tuple(int(x) for x in s) + (t,)] = {int(e): float(x) for e, x in zip(en, w)}
    return rows


def row_weights(rows, s, t, en):
    row = rows.get(tuple(int(x) for x in s) + (t,))
    return None if row is None else [row.get(int(e), 0.0) for e in en]


def within(est: np.ndarray, p: float, what: str) -> None:
    se = est.std(ddof=1) / np.sqrt(len(est))
    print(f"   {what:14s} {est.mean():.5f} ± {1.96 * se:.5f} (exact {p:.5f}, {abs(est.mean() - p) / se:.1f} SE)")
    assert abs(est.mean() - p) < 4.5 * se, what


def test_table_policy_exact():
    model, rng = toy_model(), np.random.default_rng(7)
    states = reachable(model)
    rows = random_table(model, states, rng)
    pol = NativePolicy.table(model, rows, default=DEFAULT)
    p = exact(model, states, lambda s, t, en: effective(model, row_weights(rows, s, t, en), en))
    print(f"table policy: {pol.rows} rows over {len(states)} states x {HORIZON} steps; exact P = {p:.6f}")
    n = 400_000
    hits, _ = model.simulate(n, HORIZON, "goal", pol, seed=3)
    within(np.repeat([1.0, 0.0], [hits, n - hits]), p, "Monte Carlo")
    out, _ = model.restart(100_000, HORIZON, "goal", "imp", [2, 3, 4, 5], [2, 2, 3, 3], pol, seed=4)
    within(out, p, "RESTART")
    out, _ = model.fixed_effort(50_000, HORIZON, "goal", "imp", [2, 3, 4, 5], [8, 8, 8, 8, 8], pol, seed=5)
    within(out, p, "fixed effort")


def test_callback_equals_table():
    model, rng = toy_model(), np.random.default_rng(8)
    states = reachable(model)
    rows = random_table(model, states, rng)
    table = NativePolicy.table(model, rows, default=DEFAULT)
    cb = NativePolicy.callback(model, lambda s, t, en: row_weights(rows, s, t, en) or np.zeros(len(en)),
                               default=DEFAULT)
    for name, run in [("simulate", lambda pol: model.simulate(50_000, HORIZON, "goal", pol, seed=9)[0]),
                      ("restart", lambda pol: model.restart(5_000, HORIZON, "goal", "imp", [3, 5], [3, 4], pol,
                                                            seed=9)[0]),
                      ("fixed effort", lambda pol: model.fixed_effort(2_000, HORIZON, "goal", "imp", [3, 5],
                                                                      [8, 8, 8], pol, seed=9)[0])]:
        assert np.array_equal(run(table), run(cb)), name
    # projected key: (p, c) only, no step count
    proj = {(p_, c): {int(e): float(rng.random()) for e in range(len(model.edges))} for p_ in range(4) for c in range(4)}
    ip, ic = model.index["p"], model.index["c"]
    table = NativePolicy.table(model, proj, key_vars=["p", "c"], step=False, default=DEFAULT)
    cb = NativePolicy.callback(model, lambda s, t, en: [proj[(int(s[ip]), int(s[ic]))][int(e)] for e in en],
                               default=DEFAULT)
    assert model.simulate(50_000, HORIZON, "goal", table, seed=10) == model.simulate(50_000, HORIZON, "goal", cb,
                                                                                    seed=10)
    print("callback == table (full and projected keys), bit-identical")


def test_callback_errors():
    model = toy_model()

    def bad(s, t, en):
        raise KeyError("boom")
    try:
        model.simulate(10, HORIZON, "goal", NativePolicy.callback(model, bad))
    except KeyError:
        print("callback exception re-raised")
        return
    raise AssertionError("callback exception was swallowed")


def test_qlearning_policy():
    model = toy_model()
    states = reachable(model)
    sim = NativeJaniSimulator(model)
    behaviour = ActionWeightScheduler(DEFAULT)
    ql = ShapedQLearning(sim, lambda s: model.goal(s.state, "goal"), HORIZON, behaviour, alpha=0.3, epsilon=0.2)
    ql.train(3000, np.random.default_rng(11))
    greedy = ql.greedy_scheduler()
    table = ql.greedy_native_policy()
    cb = native_policy(model, greedy)
    view = NativeJaniSimulator(model)

    def dist(s, t, en):
        view.place(s, t, en)
        return greedy.distribution(view, [model.edge_actions[e] for e in en], None)
    p = exact(model, states, dist)
    n = 400_000
    hits, _ = model.simulate(n, HORIZON, "goal", table, seed=12)
    print(f"Q-learning greedy policy ({table.rows} table rows): exact P = {p:.6f}")
    within(np.repeat([1.0, 0.0], [hits, n - hits]), p, "Monte Carlo")
    assert hits == model.simulate(n, HORIZON, "goal", cb, seed=12)[0], "greedy callback != greedy table"
    out, _ = model.restart(100_000, HORIZON, "goal", "imp", [2, 3, 4, 5], [2, 2, 3, 3], table, seed=13)
    within(out, p, "RESTART")


if __name__ == "__main__":
    test_callback_errors()
    test_callback_equals_table()
    test_table_policy_exact()
    test_qlearning_policy()

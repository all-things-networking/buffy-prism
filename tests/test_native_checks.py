"""
Regression tests for the native simulator's input and soundness checks (src/netmdp/sim/jani_native.py), on toy
models only:

- test_restart_start_level: RESTART with thresholds at or below the initial state's importance (they count with
  factor 1) agrees with the exact value on tests/models/sync_toy.pm.
- test_probability_sums: constant destination probabilities that do not sum to 1 are rejected when compiling; a
  state-dependent shortfall is an error when a draw falls into the missing mass, and any mismatch is an error with
  check_probabilities=True.
- test_scheduler_weights: negative, NaN and infinite weights (callback, table, default) and repeated key variables
  are rejected.
- test_assignment_range: a value that would wrap around int32 is a bounds error, not a silent wrap.
- test_start_state: start states of the wrong shape, type or outside the bounds are rejected.
- test_derive_seed: phase seeds differ from each other and from the user seed.

Usage: PYTHONPATH=. python tests/test_native_checks.py
"""
import numpy as np

from src.netmdp.sim.jani_native import JaniModel, NativePolicy, derive_seed
from tests.test_native_policy import HORIZON, exact, reachable, toy_model


def counter_model(probabilities: list, value=None) -> dict:
    """ x in 0..3 starts at 0; one edge from x = 0 with the given destination probabilities to x = 1, 2, ... """
    dests = [{"location": "l", "probability": {"exp": p}, "assignments": [{"ref": "x", "value": i + 1}]}
             for i, p in enumerate(probabilities)]
    if value is not None:
        dests = [{"location": "l", "assignments": [{"ref": "x", "value": value}]}]
    return {"jani-version": 1, "name": "c", "type": "dtmc",
            "variables": [{"name": "x", "type": {"kind": "bounded", "base": "int", "lower-bound": 0, "upper-bound": 3},
                           "initial-value": 0},
                          {"name": "y", "type": {"kind": "bounded", "base": "int", "lower-bound": 0, "upper-bound": 1},
                           "initial-value": 0}],
            "automata": [{"name": "a", "locations": [{"name": "l"}], "initial-locations": ["l"],
                          "edges": [{"location": "l", "guard": {"exp": {"op": "=", "left": "x", "right": 0}},
                                     "destinations": dests}]}],
            "system": {"elements": [{"automaton": "a"}]}}


def raises(exc, f, what: str) -> None:
    try:
        f()
    except exc:
        return
    raise AssertionError(f"{what}: {exc.__name__} not raised")


def test_restart_start_level():
    model = toy_model()
    p = exact(model, reachable(model), lambda s, t, en: np.full(len(en), 1.0 / len(en)))
    for thr, fac in [([0], [4]), ([0, 2], [4, 2]), ([0, 1, 3], [3, 2, 2])]:
        out, _ = model.restart(60_000, HORIZON, "goal", "imp", thr, fac, None, seed=21)
        se = out.std(ddof=1) / np.sqrt(len(out))
        print(f"   RESTART thr={thr}: {out.mean():.5f} ± {1.96 * se:.5f} (exact {p:.5f})")
        assert abs(out.mean() - p) < 4.5 * se, thr


def test_probability_sums():
    raises(ValueError, lambda: JaniModel(counter_model([0.3, 0.3])), "constant sum 0.6")
    JaniModel(counter_model([0.5, 0.25, 0.25]))
    # state-dependent: y = 0 here, so the probabilities are 0.3 / 0.3 (or 0.6 / 0.6) without being constants
    short = counter_model([{"op": "+", "left": 0.3, "right": "y"}] * 2)
    m = JaniModel(short, goals={"g": False})
    raises(ValueError, lambda: m.simulate(10_000, 1, "g", seed=1), "state-dependent shortfall")
    over = counter_model([{"op": "+", "left": 0.6, "right": "y"}] * 2)
    JaniModel(over, goals={"g": False}).simulate(100, 1, "g", seed=1)          # unchecked: goes unnoticed
    m = JaniModel(over, goals={"g": False}, check_probabilities=True)
    raises(ValueError, lambda: m.simulate(100, 1, "g", seed=1), "state-dependent excess, checked")
    single = counter_model([{"op": "+", "left": 0.5, "right": "y"}])
    m = JaniModel(single, goals={"g": False}, check_probabilities=True)
    raises(ValueError, lambda: m.simulate(100, 1, "g", seed=1), "single destination with probability 0.5")
    print("probability sums OK")


def test_scheduler_weights():
    model = toy_model()
    for w in ([-1.0], [float("nan")], [float("inf")]):
        bad = NativePolicy.callback(model, lambda s, t, en, w=w: w * len(en))
        raises(ValueError, lambda: model.simulate(100, HORIZON, "goal", bad, seed=1), f"callback weights {w}")
    s0 = tuple(int(x) for x in model.initial_state())
    raises(ValueError, lambda: NativePolicy.table(model, {s0 + (0,): {0: -1.0}}), "negative table weight")
    raises(ValueError, lambda: NativePolicy(model, {model.edge_actions[0]: float("nan")}), "NaN default weight")
    raises(ValueError, lambda: NativePolicy.table(model, {(0, 0): 0}, key_vars=["p", "p"], step=False),
           "repeated key variables")
    print("scheduler weights OK")


def test_assignment_range():
    m = JaniModel(counter_model([], value=2 ** 32 + 1), goals={"g": False})
    raises(RuntimeError, lambda: m.simulate(1, 1, "g", seed=1), "int32 wrap-around")
    print("assignment range OK")


def test_start_state():
    m = JaniModel(counter_model([0.5, 0.5]), goals={"g": False})
    raises(ValueError, lambda: m.simulate(1, 1, "g", start=np.array([0])), "wrong length")
    raises(ValueError, lambda: m.simulate(1, 1, "g", start=np.array([0.0, 0.0])), "not integer")
    raises(ValueError, lambda: m.simulate(1, 1, "g", start=np.array([4, 0])), "out of bounds")
    m.simulate(1, 1, "g", start=np.array([3, 1]))
    print("start states OK")


def test_derive_seed():
    seeds = {derive_seed(1, "pilot", 1), derive_seed(1, "evaluation", 1), derive_seed(1, "pilot", 2),
             derive_seed(2, "pilot", 1), 1, 2}
    assert len(seeds) == 6 and all(0 <= x < 2 ** 64 for x in seeds)
    print("derive_seed OK")


if __name__ == "__main__":
    test_restart_start_level()
    test_probability_sums()
    test_scheduler_weights()
    test_assignment_range()
    test_start_state()
    test_derive_seed()

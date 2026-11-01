"""
Tests of the native JANI compiler (src/netmdp/sim/jani_native.py).

- test_equivalence_with_storm: for small PRISM models (multi-module ones exercise parallel composition), builds
  Storm's explicit MDP and checks that in EVERY reachable state the native model offers the same choices (by action
  name) with the same successor distributions. Only for toy models: exact state spaces are out of the question for
  the network models.
- test_indexed_assignments: JANI assignment levels on a hand-checked example.

Usage: PYTHONPATH=. python tests/test_jani_native.py
"""
import json
from collections import Counter

import numpy as np
import stormpy

from src.netmdp.sim.jani_native import JaniModel

TOY_MODELS = ["tests/models/sync_toy.pm", "tests/models/die_mdp.pm"]


def _storm_choices(model, state: int, program) -> Counter:
    """ Multiset of (action, sorted successor distribution) for a state of Storm's explicit model. """
    out = Counter()
    m = model.transition_matrix
    for row in range(m.get_row_group_start(state), m.get_row_group_end(state)):
        labels = model.choice_labeling.get_labels_of_choice(row) if model.has_choice_labeling() else set()
        action = next(iter(labels)) if labels else "τ"
        succ = Counter()
        for entry in m.get_row(row):
            val = json.loads(str(model.state_valuations.get_json(entry.column)))
            succ[tuple(sorted(val.items()))] += round(entry.value(), 12)
        out[(action, tuple(sorted(succ.items())))] += 1
    return out


def _native_choices(native: JaniModel, s: np.ndarray) -> Counter:
    out = Counter()
    for e in native.enabled_edges(s):
        succ = Counter()
        for prob, t in native.successors(s, int(e)):
            if prob > 0:
                val = {v.name: (bool(t[i]) if native._tr.var_types[v.name] == "bool" else int(t[i]))
                       for i, v in enumerate(native.variables) if not v.name.startswith("__location")}
                succ[tuple(sorted(val.items()))] += round(prob, 12)
        out[(native.edge_actions[e], tuple(sorted(succ.items())))] += 1
    return out


def check_equivalence(prism_path: str) -> int:
    program = stormpy.parse_prism_program(prism_path)
    options = stormpy.BuilderOptions()
    options.set_build_state_valuations()
    options.set_build_choice_labels()
    model = stormpy.build_sparse_model_with_options(program, options)
    jani, _ = program.to_jani([])
    native = JaniModel(json.loads(str(jani)))
    for state in range(model.nr_states):
        val = json.loads(str(model.state_valuations.get_json(state)))
        s = native.initial_state()
        for name, value in val.items():
            s[native.index[name]] = int(value)
        storm, ours = _storm_choices(model, state, program), _native_choices(native, s)
        assert storm == ours, f"{prism_path}, state {val}:\n storm {storm}\n native {ours}"
    return model.nr_states


def test_equivalence_with_storm():
    for path in TOY_MODELS:
        n = check_equivalence(path)
        print(f"{path}: native == Storm in all {n} reachable states")


def test_indexed_assignments():
    iv = lambda n, lo, hi, i: {"name": n, "type": {"kind": "bounded", "base": "int", "lower-bound": lo,
                                                   "upper-bound": hi}, "initial-value": i}
    model = {"jani-version": 1, "name": "seq", "type": "mdp", "actions": [{"name": "go"}],
             "variables": [iv("x", 0, 100, 1), iv("y", 0, 100, 2), iv("z", 0, 100, 0)],
             "automata": [{"name": "A", "locations": [{"name": "l0"}, {"name": "l1"}], "initial-locations": ["l0"],
                           "edges": [{"location": "l0", "action": "go", "guard": {"exp": True}, "destinations": [{
                               "location": "l1", "assignments": [
                                   {"ref": "x", "value": {"op": "+", "left": "y", "right": 1}},
                                   {"ref": "y", "value": {"op": "*", "left": "x", "right": 10}},
                                   {"ref": "z", "value": {"op": "+", "left": "x", "right": "y"}, "index": 1},
                                   {"ref": "x", "value": "z", "index": 2}]}]}]}],
             "system": {"elements": [{"automaton": "A"}], "syncs": [{"synchronise": ["go"], "result": "go"}]},
             "properties": []}
    m = JaniModel(model)
    s = m.initial_state()
    m.step(s, m.enabled_edges(s)[0], 0.5)
    got = {v.name: int(s[i]) for i, v in enumerate(m.variables)}
    assert got == {"x": 13, "y": 10, "z": 13, "__location": 1}, got
    print("indexed assignments OK")


if __name__ == "__main__":
    test_indexed_assignments()
    test_equivalence_with_storm()

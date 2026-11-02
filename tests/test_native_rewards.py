"""
Tests of native expected-reward estimation (JaniModel.simulate_rewards in src/netmdp/sim/jani_native.py) on the Buffy
compiler's bursty examples (tests/models/bursty.jani: 123 states; bursty_mdp.jani: 16 states), which are small
enough for exact values. Exact computation is for toy models only, never the network models.

- test_dtmc_against_storm: C<=k of the transition rewards rew_drops / rew_backlog / rew_steps and I=k of the state
  expression q_ib, for every k = 1..6 from one curve run, against Storm (|error| < 4.5 standard errors), and the
  per-run samples of the model's own properties e_drops / e_backlog.
- test_mdp_policy_exact: under a random (state, t) table policy, C<=5 of rew_backlog1, I=5 and the state-reward
  C<=5 of backlog 1 against backward induction; Storm's Emin <= estimate <= Emax.

Usage: PYTHONPATH=. python tests/test_native_rewards.py
"""
import json
import os
import tempfile

import numpy as np
import stormpy

from src.netmdp.sim.jani_native import JaniModel, NativePolicy
from tests.buffy_jani_check import expected_value_properties, reward_model, reward_samples

DTMC, MDP = "tests/models/bursty.jani", "tests/models/bursty_mdp.jani"


def storm_values(path: str, exprs: dict[str, dict]) -> dict[str, float]:
    """ Storm's exact values of the given JANI expected-value expressions (added to the model as properties). """
    model = json.load(open(path))
    model["properties"] = [{"name": n, "expression": {"op": "filter", "fun": "values", "values": e,
                                                      "states": {"op": "initial"}}} for n, e in exprs.items()]
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "model.jani")
        json.dump(model, open(tmp, "w"))
        jm, props = stormpy.parse_jani_model(tmp)
    sm = stormpy.build_model(jm, props)
    return {p.name: stormpy.model_checking(sm, p).at(sm.initial_states[0]) for p in props}


def within(mean: float, se: float, exact: float, what: str) -> None:
    print(f"   {what:24s} {mean:.5f} ± {1.96 * se:.5f} (exact {exact:.5f}, {abs(mean - exact) / se:.1f} SE)")
    assert abs(mean - exact) < 4.5 * se + 1e-12, what


def test_dtmc_against_storm():
    jani = json.load(open(DTMC))
    props = expected_value_properties(jani)
    assert props == {"e_drops": ("C", "rew_drops", 6), "e_backlog": ("I", "q_ib", 6)}, props
    native = reward_model(jani, props)     # observable e_backlog = q_ib
    H, n = 6, 400_000
    exprs = {f"C{r}_{k}": {"op": "Emax", "exp": r, "accumulate": ["steps"], "step-instant": k}
             for r in ("rew_drops", "rew_backlog", "rew_steps") for k in range(1, H + 1)}
    exprs.update({f"I_{k}": {"op": "Emax", "exp": "q_ib", "step-instant": k} for k in range(0, H + 1)})
    exact = storm_values(DTMC, exprs)
    runs = native.simulate_rewards(n, H, seed=1, curve=True)
    print(f"bursty DTMC: {n} runs of {H} steps")
    for r in ("rew_drops", "rew_backlog", "rew_steps"):
        for k in range(1, H + 1):
            m, v = runs.curve_mean[r][k], runs.curve_var[r][k]
            within(m, max(np.sqrt(v / n), 1e-9), exact[f"C{r}_{k}"], f"C<={k} {r}")
    for k in range(0, H + 1):
        m, v = runs.curve_mean["e_backlog"][k], runs.curve_var["e_backlog"][k]
        within(m, max(np.sqrt(v / n), 1e-9), exact[f"I_{k}"], f"I={k} q_ib")
    # the model's own properties, from per-run samples
    jm, jprops = stormpy.parse_jani_model(DTMC)
    sm = stormpy.build_model(jm, jprops)
    ref = {p.name: stormpy.model_checking(sm, p).at(sm.initial_states[0]) for p in jprops}
    for name in props:
        x = reward_samples(native, props, {H: runs}, name)
        within(x.mean(), x.std(ddof=1) / np.sqrt(n), ref[name], name)


def test_mdp_policy_exact():
    jani = json.load(open(MDP))
    native = JaniModel(jani, observables={"b1": "pq_ibs_1"})
    H, rng = 5, np.random.default_rng(3)
    s0 = native.initial_state()
    seen, todo = {s0.tobytes(): s0}, [s0]
    while todo:
        s = todo.pop()
        for e in native.enabled_edges(s):
            for _, t in native.successors(s, int(e)):
                if t.tobytes() not in seen:
                    seen[t.tobytes()] = t
                    todo.append(t)
    rows = {}
    for s in seen.values():
        en = native.enabled_edges(s)
        if len(en) > 1:
            for t in range(H):
                rows[tuple(int(x) for x in s) + (t,)] = {int(e): float(rng.random()) for e in en}
    pol = NativePolicy.table(native, rows)
    ri = native.reward_variables.index("rew_backlog1")

    def exact(kind: str) -> float:
        """ C: rew_backlog1 summed over H steps; I: b1 at step H; S: b1 summed over steps 0..H-1. """
        v = {k: (native.observable(s, "b1") if kind == "I" else 0.0) for k, s in seen.items()}
        for t in range(H - 1, -1, -1):
            nv = {}
            for k, s in seen.items():
                here = native.observable(s, "b1") if kind == "S" else 0.0
                en = native.enabled_edges(s)
                if len(en) == 0:
                    nv[k] = v[k] + here
                    continue
                w = np.array([rows.get(tuple(int(x) for x in s) + (t,), {}).get(int(e), 1.0) for e in en])
                w = w / w.sum()
                nv[k] = here + sum(we * sum(p * ((r[ri] if kind == "C" else 0.0) + v[u.tobytes()])
                                            for p, u, r in native.successors(s, int(e), rewards=True))
                                   for we, e in zip(w, en))
            v = nv
        return v[s0.tobytes()]
    n = 400_000
    runs = native.simulate_rewards(n, H, pol, seed=2)
    print(f"bursty MDP, random table policy ({pol.rows} rows): {n} runs")
    for kind, x in [("C", runs.cumulative["rew_backlog1"]), ("I", runs.final["b1"]), ("S", runs.state_cumulative["b1"])]:
        within(x.mean(), x.std(ddof=1) / np.sqrt(n), exact(kind), f"{kind} backlog 1 (policy)")
    ref = storm_values(MDP, {m: {"op": m, "exp": "rew_backlog1", "accumulate": ["steps"], "step-instant": H}
                             for m in ("Emin", "Emax")})
    x = runs.cumulative["rew_backlog1"].mean()
    print(f"   Storm Emin {ref['Emin']:.4f} <= policy {x:.4f} <= Emax {ref['Emax']:.4f}")
    assert ref["Emin"] <= x <= ref["Emax"]


if __name__ == "__main__":
    test_dtmc_against_storm()
    test_mdp_policy_exact()

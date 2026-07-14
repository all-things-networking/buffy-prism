#!/usr/bin/env python3
"""Reproduce the LCRL incast policy-synthesis experiments.

For a chosen parameter corner of ``incast_mdp.pm`` it (1) trains a dense-reward
LCRL policy on ``F ("done" & odrops>=THRESH)`` -- maximising drops (Pmax /
worst-case scheduler) or minimising them (Pmin / loss-avoiding scheduler) -- and
(2) Monte-Carlo-evaluates, on the same MDP, ``P[odrops>=THRESH]`` under the
learned policy, a uniform-hazard policy (which reproduces the DTMC case study),
and an always-start baseline. See METHODOLOGY.md.

Examples
--------
    # discriminating corner, worst-case scheduler (Pmax):
    python run_synthesis.py --M 16 --WIN 96 --SLEN 8 --direction max
    # loss-avoiding scheduler (Pmin), reporting how many senders it starts:
    python run_synthesis.py --M 16 --WIN 96 --SLEN 8 --direction min

Run from the repository root (so that ``import src...`` resolves) with the venv
that has stormpy + lcrl, e.g.  ``PYTHONPATH=. .venv/bin/python experiments/...``.
"""
import argparse
import os
import random
import statistics
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODEL_DIR = os.path.join(REPO, "models", "example2_desync_short_bursts")

from src.netmdp.lcrl import (
    ShapedLCRL,
    build_mdp_and_ldba,
    greedy_action,
    mc_evaluate,
    uniform_hazard_policy,
)

MMAX = 20  # sender slots in the incast models


def resolve_state_vars(tokens, consts):
    """Map --state-vars tokens to variable names or derived-feature callables.
    Known features (bucketed to keep the tabular state small): `qo_bucketed`
    (output-buffer occupancy // 4), `n_active_bucketed` (count of currently-active
    flows, capped at 8), `Ftot` (number of backlogged uplink ports)."""
    if not tokens:
        return None
    slen = consts["SLEN"]

    def qo_bucketed(fs):
        return fs["qo"] // 4

    def n_active_bucketed(fs):
        n = sum(1 for k in range(1, MMAX + 1)
                if fs[f"on{k}"] == 1 and fs["slot"] - fs[f"t{k}"] < slen)
        return min(n, 8)

    def Ftot(fs):
        return sum(1 for j in range(1, 11) if fs[f"q{j}"] > 0)

    features = {"qo_bucketed": qo_bucketed,
                "n_active_bucketed": n_active_bucketed,
                "Ftot": Ftot}
    return [features.get(t, t) for t in tokens]


def run(consts, direction, episodes, mc, seed, state_vars, model):
    pm = os.path.join(MODEL_DIR, f"{model}.pm")
    props = os.path.join(MODEL_DIR, f"{model}.props")
    horizon = consts["WIN"] + consts["M"] * consts["SLEN"] + consts["SLEN"]
    iter_max = 21 * (horizon + 4)  # (MMAX+1) substages per slot, + slack to reach "done"
    random.seed(seed)

    mdp, ldba, prop = build_mdp_and_ldba(
        pm, prop_index=0, constants=consts, props_path=props, state_variables=state_vars
    )
    print(f"model={model} | corner={consts} | HORIZON={horizon} | iter_max={iter_max}")
    print(f"state projection: {mdp.state_variables}")
    print(f"property: {prop.raw}  ->  LTL {prop.ltl}  | action_space {mdp.action_space}")
    print(f"LDBA: start {ldba.initial_automaton_state}, accepting {ldba.accepting_sets}, "
          f"epsilon {ldba.epsilon_transitions}")

    sign = 1 if direction == "max" else -1
    t0 = time.time()
    agent = ShapedLCRL(
        MDP=mdp, LDBA=ldba, scale=consts["THRESH"], sign=sign,
        discount_factor=0.999, learning_rate=0.8,
        decaying_learning_rate=True, epsilon=0.4,
    )
    agent.train_ql(episodes, iter_max, Q_initial_value=0)
    vals = [float(v) for v in agent.q_at_initial_state]
    print(f"\ntrained {direction} in {time.time()-t0:.0f}s | value@s0 final-200 mean "
          f"{statistics.mean(vals[-200:]):.3f} | product states {len(agent.Q)}")

    thr = consts["THRESH"]
    policies = {
        f"lcrl_greedy ({'Pmax' if sign>0 else 'Pmin'})":
            lambda m: greedy_action(agent, m, ldba),
        "uniform_hazard (=DTMC)": uniform_hazard_policy(consts["WIN"]),
        "always_start": lambda m: 0,
    }
    print(f"\n=== Monte-Carlo on the MDP (N={mc}): P[odrops>=THRESH] | mean_odrops ===")
    for name, pol in policies.items():
        random.seed(seed)
        p, mean = mc_evaluate(mdp, ldba, pol, mc, iter_max, var="odrops", threshold=thr)
        print(f"  {name:26s}: P[Q]={p:.3f}  mean_odrops={mean:.2f}")

    # For the Pmin scheduler, also report how many senders it actually starts:
    # near-zero means the "avoidance" is the degenerate never-send schedule.
    if direction == "min":
        random.seed(seed)
        started = 0.0
        for _ in range(mc):
            mdp.reset(); ldba.reset()
            for _ in range(iter_max):
                if mdp.is_done():
                    break
                mdp.step(greedy_action(agent, mdp, ldba))
            fs = mdp.full_state
            started += sum(fs[f"on{k}"] for k in range(1, consts["M"] + 1))
        print(f"\n  Pmin scheduler starts {started/mc:.1f}/{consts['M']} senders on average "
              f"(~0 => avoidance is the non-physical never-send schedule)")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--M", type=int, default=16)
    ap.add_argument("--WIN", type=int, default=96)
    ap.add_argument("--SLEN", type=int, default=8)
    ap.add_argument("--BUF", type=int, default=32)
    ap.add_argument("--THRESH", type=int, default=8)
    ap.add_argument("--direction", choices=["max", "min"], default="max",
                    help="max = worst-case (Pmax) scheduler; min = loss-avoiding (Pmin)")
    ap.add_argument("--model", default="incast_mdp",
                    help="model base name in models/example2_desync_short_bursts/ "
                         "(incast_mdp = per-slot start-vs-wait; incast_mdp_Pmin = "
                         "forced-start variant [wait only while slot<WIN] for a "
                         "physical Pmin)")
    ap.add_argument("--episodes", type=int, default=1200)
    ap.add_argument("--mc", type=int, default=300, help="Monte-Carlo rollouts per policy")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--state-vars", default="slot,stage,odrops",
                    help="comma-separated projected state coordinates (empty = full "
                         "state). Besides program variables, these derived congestion "
                         "features are available: qo_bucketed, n_active_bucketed, Ftot")
    a = ap.parse_args()
    consts = dict(BUF=a.BUF, THRESH=a.THRESH, M=a.M, WIN=a.WIN, SLEN=a.SLEN)
    state_vars = resolve_state_vars([v for v in a.state_vars.split(",") if v], consts)
    run(consts, a.direction, a.episodes, a.mc, a.seed, state_vars, a.model)


if __name__ == "__main__":
    main()

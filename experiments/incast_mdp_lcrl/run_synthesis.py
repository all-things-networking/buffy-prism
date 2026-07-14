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


def congestion_feature(name, consts):
    """A congestion measure in ~[0,1] for reward shaping, or None. `_sq` variants
    are convex (penalise *concentration*): the linear integral of concurrency
    over a run is schedule-invariant (M*SLEN), so only a convex penalty
    distinguishes a synchronised burst from a spread schedule."""
    slen, m, buf = consts["SLEN"], consts["M"], consts["BUF"]

    def n_active(fs):
        return min(sum(1 for k in range(1, MMAX + 1)
                       if fs[f"on{k}"] == 1 and fs["slot"] - fs[f"t{k}"] < slen), m) / m

    if name == "qo":
        return lambda fs: fs["qo"] / buf
    if name == "qo_sq":
        return lambda fs: (fs["qo"] / buf) ** 2
    if name == "n_active":
        return n_active
    if name == "n_active_sq":
        return lambda fs: n_active(fs) ** 2
    return None


def run(consts, direction, episodes, mc, seed, state_vars, model,
        congestion_var="none", congestion_weight=0.0, q_init=0.0,
        prop_index=0, ltl_reward=False, drop_weight=1.0):
    pm = os.path.join(MODEL_DIR, f"{model}.pm")
    props = os.path.join(MODEL_DIR, f"{model}.props")
    horizon = consts["WIN"] + consts["M"] * consts["SLEN"] + consts["SLEN"]
    iter_max = 21 * (horizon + 4)  # (MMAX+1) substages per slot, + slack to reach "done"
    random.seed(seed)

    mdp, ldba, prop = build_mdp_and_ldba(
        pm, prop_index=prop_index, constants=consts, props_path=props,
        state_variables=state_vars
    )
    print(f"model={model} | corner={consts} | HORIZON={horizon} | iter_max={iter_max}")
    print(f"state projection: {mdp.state_variables}")
    print(f"property: {prop.raw}  ->  LTL {prop.ltl}  | action_space {mdp.action_space}")
    print(f"LDBA: start {ldba.initial_automaton_state}, accepting {ldba.accepting_sets}, "
          f"epsilon {ldba.epsilon_transitions}")

    sign = 1 if direction == "max" else -1
    cong_fn = congestion_feature(congestion_var, consts)
    # qo only updates at the per-slot service step; n_active changes as each
    # sender starts, so penalise it every substage to steer intra-slot decisions.
    per_slot = congestion_var not in ("n_active", "n_active_sq")
    if cong_fn is not None:
        gran = "per slot" if per_slot else "per substage"
        print(f"reward shaping: -{congestion_weight} * {congestion_var} ({gran})")
    if ltl_reward:
        print(f"native LTL reward on: +1 at the accepting state of {prop.ltl} "
              f"(drop_weight={drop_weight}); returns in [0,1], Q_init=0 is pessimistic")
    t0 = time.time()
    agent = ShapedLCRL(
        MDP=mdp, LDBA=ldba, scale=consts["THRESH"], sign=sign,
        drop_weight=drop_weight, ltl_weight=1.0 if ltl_reward else 0.0,
        congestion_fn=cong_fn, congestion_weight=congestion_weight,
        congestion_per_slot=per_slot,
        discount_factor=0.999, learning_rate=0.8,
        decaying_learning_rate=True, epsilon=0.4,
    )
    if q_init != 0.0:
        print(f"pessimistic Q-init: {q_init} (unexplored looks bad -> greedy commits "
              f"to proven low-congestion paths instead of fleeing to unexplored)")
    agent.train_ql(episodes, iter_max, Q_initial_value=q_init)
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
    ap.add_argument("--congestion-var",
                    choices=["none", "qo", "qo_sq", "n_active", "n_active_sq"], default="none",
                    help="congestion penalty for the Pmin direction (teaches the policy "
                         "to avoid synchronising extremes). `_sq` = convex; n_active* is "
                         "penalised per substage, qo* per slot")
    ap.add_argument("--congestion-weight", type=float, default=0.0,
                    help="weight of the per-slot congestion penalty")
    ap.add_argument("--q-init", type=float, default=0.0,
                    help="Q-table initialisation; set <0 (pessimistic) for the Pmin "
                         "direction so unexplored states do not look optimal")
    ap.add_argument("--prop-index", type=int, default=0,
                    help="which .props line to synthesise for (0=bad event F(done & "
                         "odrops>=THRESH); on incast_mdp_Pmin, 3=safe complement "
                         "F(done & odrops<THRESH) -> Pmin via LTL-maximisation)")
    ap.add_argument("--ltl-reward", action="store_true",
                    help="use LCRL's native +1-at-accepting reward (the correct framing "
                         "for maximising a property, e.g. the safe complement for Pmin)")
    ap.add_argument("--drop-weight", type=float, default=1.0,
                    help="weight of the dense delta-odrops reward (0 = pure LTL reward)")
    a = ap.parse_args()
    consts = dict(BUF=a.BUF, THRESH=a.THRESH, M=a.M, WIN=a.WIN, SLEN=a.SLEN)
    state_vars = resolve_state_vars([v for v in a.state_vars.split(",") if v], consts)
    run(consts, a.direction, a.episodes, a.mc, a.seed, state_vars, a.model,
        congestion_var=a.congestion_var, congestion_weight=a.congestion_weight,
        q_init=a.q_init, prop_index=a.prop_index, ltl_reward=a.ltl_reward,
        drop_weight=a.drop_weight)


if __name__ == "__main__":
    main()

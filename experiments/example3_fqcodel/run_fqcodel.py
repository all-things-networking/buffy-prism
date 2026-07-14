#!/usr/bin/env python3
"""Synthesise the worst-case FQ-CoDel traffic with LCRL.

Trains LCRL to MAXIMISE the bad event Q = F(time=TIME_STEPS & iq5_deqs_bl>3)
-- flow 5 OVER-served (dequeued >3 times under contention), starving flows 1-4 --
on models/example3_fqcodel/fqcodel.pm, whose nondeterminism is the input traffic.
The learned policy is the worst-case traffic pattern. Uses the native LTL
+1-at-accepting reward (short ~224-step horizon, so it propagates), plus a dense
+Δiq5_deqs_bl shaping (over-serve flow 5). Reports P[iq5_deqs_bl>t] under the
learned greedy vs a random-traffic baseline (over-service is rare under random).

    PYTHONPATH=. .venv/bin/python experiments/example3_fqcodel/run_fqcodel.py
"""
import argparse
import os
import random
import statistics
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PM = os.path.join(REPO, "models", "example3_fqcodel", "fqcodel.pm")
PROPS = os.path.join(REPO, "models", "example3_fqcodel", "fqcodel.props")

from src.netmdp.lcrl.shaped import ShapedLCRL, greedy_action, mc_evaluate
from src.netmdp.lcrl.workflow import build_mdp_and_ldba

REWARD_SCALE = 4    # normaliser for the dense delta-iq5_deqs_bl reward
ITER = 500          # ~224 micro-steps to time=TIME_STEPS, + slack


OVER_T = (3, 4, 5, 6)  # bad event is iq5_deqs_bl > 3 (flow 5 over-served)


def overservice_profile(mdp, ldba, policy, n):
    """One MC pass -> P[iq5_deqs_bl > t] for t in OVER_T and the mean final count
    (how severely flow 5 hogs the output under `policy`; t=3 is the bad event)."""
    counts = []
    for _ in range(n):
        mdp.reset(); ldba.reset()
        for _ in range(ITER):
            if mdp.is_done():
                break
            mdp.step(policy(mdp))
        counts.append(mdp.full_state["iq5_deqs_bl"])
    m = float(len(counts))
    p_gt = {t: sum(c > t for c in counts) / m for t in OVER_T}
    return p_gt, sum(counts) / m


def run(episodes, mc, seed, drop_weight, state_vars):
    random.seed(seed)
    mdp, ldba, prop = build_mdp_and_ldba(PM, 0, props_path=PROPS,
                                         state_variables=state_vars)
    print(f"property: {prop.raw} -> {prop.ltl} | action_space {mdp.action_space}")
    print(f"state projection: {mdp.state_variables} | LDBA acc {ldba.accepting_sets}")

    t0 = time.time()
    # Maximise the bad event iq5_deqs_bl>3: native +1 at the accepting state, plus a
    # dense +Δiq5_deqs_bl (sign=+1) that rewards over-serving flow 5.
    agent = ShapedLCRL(
        MDP=mdp, LDBA=ldba, scale=REWARD_SCALE, reward_var="iq5_deqs_bl", sign=1,
        ltl_weight=1.0, drop_weight=drop_weight,
        discount_factor=0.999, learning_rate=0.8, decaying_learning_rate=True, epsilon=0.3,
    )
    agent.train_ql(episodes, ITER, Q_initial_value=0)
    vals = [float(v) for v in agent.q_at_initial_state]
    print(f"trained (drop_weight={drop_weight}) in {time.time()-t0:.0f}s | "
          f"value@s0 final-200 {statistics.mean(vals[-200:]):.3f} | product states {len(agent.Q)}")

    random.seed(seed)
    p_lcrl, m_lcrl = overservice_profile(mdp, ldba, lambda mm: greedy_action(agent, mm, ldba), mc)
    random.seed(seed)
    p_rand, m_rand = overservice_profile(mdp, ldba, lambda mm: random.choice(mm.action_space), mc)
    print("\n=== flow-5 over-service: P[iq5_deqs_bl > t] | mean  (Pmax objective; bad event t=3) ===")
    hdr = "  ".join(f"P[>{t}]" for t in OVER_T)
    print(f"  {'policy':24s}  {hdr}   mean")
    print(f"  {'LCRL worst-case traffic':24s}  " +
          "  ".join(f"{p_lcrl[t]:.3f}" for t in OVER_T) + f"   {m_lcrl:.2f}")
    print(f"  {'random traffic baseline':24s}  " +
          "  ".join(f"{p_rand[t]:.3f}" for t in OVER_T) + f"   {m_rand:.2f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--episodes", type=int, default=2000)
    ap.add_argument("--mc", type=int, default=300)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--drop-weight", type=float, default=1.0,
                    help="0 = pure native LTL reward; >0 adds dense +delta iq5_deqs_bl")
    ap.add_argument("--state-vars", default="time,stage,iq5_deqs_bl")
    a = ap.parse_args()
    run(a.episodes, a.mc, a.seed, a.drop_weight,
        [v for v in a.state_vars.split(",") if v] or None)


if __name__ == "__main__":
    main()

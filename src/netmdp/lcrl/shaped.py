"""Dense-reward LCRL and Monte-Carlo policy evaluation for the incast MDP study.

LCRL's stock reward is sparse: 1 only when the LDBA reaches an accepting state
(here, ``done & odrops>=THRESH``), 0 everywhere else. Over the incast MDP's long
per-episode horizon (``MMAX+1`` substages x ``HORIZON`` slots) that single
terminal signal propagates too slowly for tabular Q-learning to converge.

``ShapedLCRL`` replaces it with a *dense* reward proportional to the per-step
change in a chosen MDP variable (``odrops`` by default), which increases
monotonically as the bad event is approached:

    reward_t = sign * (var(s_t) - var(s_{t-1})) / scale

With ``sign=+1`` and ``scale=THRESH`` the undiscounted return over an episode
equals ``final_odrops / THRESH`` in ``[0, 1]``, so the learned policy MAXIMISES
expected output drops -- the worst-case / adversarial start scheduler whose
success probability estimates ``Pmax[odrops>=THRESH]``. With ``sign=-1`` it
MINIMISES drops -- the loss-avoiding scheduler, estimating ``Pmin``.

Because ``value@s0`` under-converges in magnitude on this horizon even when the
greedy policy is already optimal, the quantity to compare against the case study
is the **Monte-Carlo-evaluated policy** (``mc_evaluate``), not ``value@s0``.

Requires an MDP exposing ``full_state`` and ``prev_full_state`` (see
``PrismBlackBoxMDP``).
"""

import random

from lcrl.core.lcrl_core import LCRL


class ShapedLCRL(LCRL):
    def __init__(self, *args, scale=1.0, reward_var="odrops", sign=1,
                 drop_weight=1.0, ltl_weight=0.0,
                 congestion_fn=None, congestion_weight=0.0, congestion_per_slot=True,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self._scale = scale
        self._reward_var = reward_var
        self._sign = sign
        # ``drop_weight`` scales the dense delta-reward on ``reward_var``;
        # ``ltl_weight`` re-adds LCRL's native +1-at-the-accepting-state reward.
        # For the *maximise-a-property* framing (e.g. Pmin via the safe complement
        # F(done & odrops<THRESH)) set ltl_weight=1: returns then lie in [0,1], so
        # the default Q_init=0 is the WORST value and the greedy prefers proven
        # paths -- avoiding the optimistic-init pathology of reward-minimisation.
        self._drop_weight = drop_weight
        self._ltl_weight = ltl_weight
        # Optional congestion penalty (subtracted) to keep congestion low. Applied
        # once per slot (``congestion_per_slot=True``, at the service step -- for
        # output signals like ``qo`` that only update there) or every substage
        # (``False`` -- for ``n_active``, which changes as each sender starts).
        self._congestion_fn = congestion_fn
        self._congestion_weight = congestion_weight
        self._congestion_per_slot = congestion_per_slot

    def reward(self, reward_flag):
        r = self._ltl_weight * (1.0 if reward_flag > 0 else 0.0)
        cur, prev = self.MDP.full_state, self.MDP.prev_full_state
        if cur is None or prev is None:
            return r
        if self._drop_weight:
            r += self._drop_weight * self._sign * \
                (cur[self._reward_var] - prev[self._reward_var]) / self._scale
        if self._congestion_fn is not None:
            if not self._congestion_per_slot or cur["slot"] != prev["slot"]:
                r -= self._congestion_weight * self._congestion_fn(cur)
        return r


def greedy_action(agent, mdp, ldba):
    """The learned greedy action at the current product state (random fallback
    for a product state never visited during training)."""
    key = str(mdp.current_state + [ldba.automaton_state])
    q = agent.Q.get(key)
    if q:
        return max(q, key=q.get)
    return random.choice(mdp.action_space)


def mc_evaluate(mdp, ldba, policy, n, iter_max, var="odrops", threshold=None):
    """Monte-Carlo-estimate, under ``policy(mdp) -> action``, the probability that
    the run ends with ``var >= threshold`` and the mean final ``var``.

    Returns ``(prob, mean_var)``. Each rollout runs to an absorbing (``done``)
    state or ``iter_max`` steps.
    """
    hits, total = 0, 0.0
    for _ in range(n):
        mdp.reset()
        ldba.reset()
        for _ in range(iter_max):
            if mdp.is_done():
                break
            mdp.step(policy(mdp))
        value = mdp.full_state[var]
        if threshold is not None:
            hits += value >= threshold
        total += value
    return (hits / n if threshold is not None else None), total / n


def uniform_hazard_policy(win):
    """A stochastic policy reproducing the DTMC's per-slot uniform start on the
    MDP: a waiting sender (a 2-choice state) starts with probability
    ``1/(WIN+1-slot)`` (action 0) and otherwise waits (action 1). Evaluating it
    on the MDP recovers the DTMC's ``P[Q]`` (the case-study value)."""
    def policy(mdp):
        if len(mdp.action_space) < 2 or mdp.nr_available_actions() < 2:
            return 0
        slot = mdp.full_state["slot"]
        denom = win + 1 - slot
        hazard = 1.0 / denom if denom > 0 else 1.0
        return 0 if random.random() < hazard else 1
    return policy

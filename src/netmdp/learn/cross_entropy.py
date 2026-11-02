"""
Cross-entropy method (Rubinstein's multilevel rare-event version) for learning an adversarial memoryless,
state-independent traffic scheduler: one categorical distribution over the actions of each choice group (e.g. the
arrival counts K0..K4 of each input queue), chosen to make a rare goal "score >= target" likely.

Iteration: simulate n runs natively under the current distributions; the elite are the runs whose score is at least
the (1 - rho) quantile, capped at the target; refit each group's distribution to the elite's choice frequencies;
smooth with the previous parameters. The result is an ActionWeightScheduler, which can be exported to JANI as a
DTMC (sim.export.induced_dtmc_jani) and evaluated with modes.
"""
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from src.netmdp.sim.jani_native import JaniModel, derive_seed
from src.netmdp.sim.scheduler import ActionWeightScheduler


@dataclass
class CrossEntropyResult:
    weights: dict[str, float]
    history: list[dict] = field(default_factory=list)

    def scheduler(self) -> ActionWeightScheduler:
        return ActionWeightScheduler(dict(self.weights))


def cross_entropy_scheduler(model: JaniModel, groups: dict[str, list[str]], initial: dict[str, float],
                            score_var: str, target: int, horizon: int, n_runs: int = 20000, rho: float = 0.05,
                            smoothing: float = 0.7, iterations: int = 30, seed: int = 1,
                            log: Callable[[str], None] = print) -> CrossEntropyResult:
    """
    groups: name -> the action names of one choice group (each group's weights form a distribution).
    initial: action -> initial weight (e.g. the nominal traffic). Actions outside the groups keep weight 0 (their
    choices are resolved uniformly when they are the only ones enabled, as in jm_simulate).
    """
    actions = model.edge_actions
    edges_of = {a: [i for i, ea in enumerate(actions) if ea == a] for g in groups.values() for a in g}
    p = {a: float(initial.get(a, 0.0)) for g in groups.values() for a in g}
    for g in groups.values():
        tot = sum(p[a] for a in g)
        for a in g:
            p[a] /= tot
    result = CrossEntropyResult(dict(p))
    for it in range(iterations):
        w = np.zeros(len(actions))
        for a, es in edges_of.items():
            w[es] = p[a]
        scores, counts = model.simulate_scores(n_runs, horizon, score_var, w, seed=derive_seed(seed, "cross-entropy", it))
        level = min(float(np.quantile(scores, 1 - rho)), float(target))
        elite = scores >= level
        hit_rate = float(np.mean(scores >= target))
        new = {}
        for g in groups.values():
            c = np.array([counts[elite][:, edges_of[a]].sum() for a in g], dtype=float)
            freq = c / c.sum() if c.sum() > 0 else np.array([p[a] for a in g])
            for a, f in zip(g, freq):
                new[a] = smoothing * f + (1 - smoothing) * p[a]
        p = new
        result.history.append({"iteration": it + 1, "level": level, "hit_rate": hit_rate,
                               "elite": int(elite.sum()), "mean_score": float(scores.mean())})
        log(f"CE iter {it + 1}: level {level:g}, P(score >= {target}) ≈ {hit_rate:.4g}, mean score {scores.mean():.2f}")
        if level >= target and hit_rate > 0.5:
            break
    result.weights = p
    return result

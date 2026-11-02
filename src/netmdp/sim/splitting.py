"""
Native importance splitting on a compiled JANI model (JaniModel.restart / JaniModel.fixed_effort), with
expected-success selection of levels and splitting factors (Budde, D'Argenio & Hartmanns, "Automated compositional
importance splitting", 2019; the same method as sampler/splitting/expected_success_method.py and modes'
--levels ExpectedSuccess).

Choices are resolved by a scheduler: per-action weights (memoryless) or a NativePolicy, which may depend on the
state and the step count (e.g. a learned policy); either way the splitting runs on the induced DTMC.
"""
from collections import deque
from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.netmdp.sampler.sampler import Sampler
from src.netmdp.sim.jani_native import JaniModel, Scheduling, derive_seed


@dataclass(frozen=True)
class SplittingDesign:
    thresholds: list[int]   # importance thresholds T_1 < ... < T_m (level = number of thresholds <= importance)
    factors: list[int]      # RESTART splitting factor per threshold (expected-success factors)
    p_up: list[float]       # pilot estimates of P(next importance value | current), per importance value

    def efforts(self, user_effort: int) -> list[int]:
        """ Weighted fixed effort: per-level effort = user_effort x the factor of the threshold that starts it. """
        return [user_effort] + [user_effort * f for f in self.factors]


def expected_success(model: JaniModel, goal: str, importance: str, max_importance: int, horizon: int,
                     scheduler: Scheduling = None, pilot_effort: int = 256, seed: int = 1,
                     max_pilots: int = 1000) -> SplittingDesign:
    """
    Pilot fixed-effort runs with a threshold at every importance value 1..max_importance (constant effort) until the
    goal level is reached; p_up[l] is the running mean of the success fraction at level l. The factor for crossing
    into importance l+1 is round(1/p_up[l] + carry) with the rounding error carried forward; values with factor > 1
    become thresholds. The goal must imply importance >= max_importance.
    """
    thresholds = list(range(1, max_importance + 1))
    efforts = [pilot_effort] * (max_importance + 1)
    p_up, m = np.zeros(max_importance + 1), 0
    while m < max_pilots and p_up[-1] == 0:
        m += 1
        _, _, succ = model.fixed_effort(1, horizon, goal, importance, thresholds, efforts, scheduler,
                                        seed=derive_seed(seed, "pilot", m), level_successes=True)
        p_up += (succ[0] / pilot_effort - p_up) / m
    if p_up[-1] == 0:
        raise RuntimeError(f"expected success: goal level not reached in {max_pilots} pilots")
    chosen, factors, carry = [], [], 0.0
    for level in range(max_importance):   # factor for crossing from importance `level` to `level + 1`
        split = 1.0 / p_up[level] + carry
        factor = int(np.floor(split + 0.5))
        carry = split - factor
        if factor > 1:
            chosen.append(level + 1)
            factors.append(factor)
    return SplittingDesign(chosen, factors, [float(p) for p in p_up])


class NativeSplittingSampler(Sampler):
    """ Feeds per-run splitting estimates to the hypothesis tests (sample() = one RESTART or fixed-effort run). """
    def __init__(self, model: JaniModel, method: str, design: SplittingDesign, goal: str, importance: str,
                 horizon: int, scheduler: Scheduling = None, user_effort: int = 8,
                 batch: int = 1000, seed: int = 1):
        super().__init__()
        if method not in ("restart", "fixed_effort"):
            raise ValueError("method must be 'restart' or 'fixed_effort'")
        self.model, self.method, self.design = model, method, design
        self.goal, self.importance, self.horizon = goal, importance, horizon
        self.scheduler, self.user_effort, self.batch, self.seed = scheduler, user_effort, batch, seed
        self._buffer: deque = deque()
        self.steps = 0
        self._batches = 0

    def __str__(self):
        return f"Native {self.method} sampler [thresholds={self.design.thresholds}, factors={self.design.factors}]"

    def runs(self, n: int) -> np.ndarray:
        self._batches += 1
        seed = derive_seed(self.seed, "evaluation", self._batches)   # never a pilot's stream (expected_success)
        if self.method == "restart":
            out, steps = self.model.restart(n, self.horizon, self.goal, self.importance, self.design.thresholds,
                                            self.design.factors, self.scheduler, seed=seed)
        else:
            out, steps = self.model.fixed_effort(n, self.horizon, self.goal, self.importance, self.design.thresholds,
                                                 self.design.efforts(self.user_effort), self.scheduler, seed=seed)
        self.steps += steps
        return out

    def sample(self) -> float:
        if not self._buffer:
            self._buffer.extend(self.runs(self.batch))
        return float(self._buffer.popleft())

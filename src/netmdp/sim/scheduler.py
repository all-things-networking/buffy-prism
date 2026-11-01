"""
Schedulers resolve an MDP's nondeterministic choices; applying one to a model induces a DTMC (on the product of
states and scheduler memory, for schedulers with memory).

A scheduler maps (simulator state, enabled choices, memory) to a probability distribution over the enabled choices,
identified by action name. Learners (RL agents, distribution-learning methods) implement the same interface, so they
can drive the simulator directly. Two rules keep estimates meaningful:
  - freeze a scheduler while estimating a probability under it (a scheduler that keeps learning changes the DTMC);
  - include the memory in every splitting anchor (Rollout.save / restore do this).
"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

import numpy as np

from src.netmdp.sim.jani_native import JaniModel, NativePolicy
from src.netmdp.sim.simulator import NativeJaniSimulator, Simulator, SimState


class Scheduler(ABC):
    def initial_memory(self) -> Any:
        return None

    @abstractmethod
    def distribution(self, sim: Simulator, choices: list[str], memory: Any) -> np.ndarray:
        """ Probabilities over `choices` (same order), summing to 1. """

    def update_memory(self, memory: Any, sim: Simulator, choice: str) -> Any:
        """ Called after a choice is taken and the simulator has stepped; returns the new memory. """
        return memory

    def sample(self, sim: Simulator, choices: list[str], memory: Any, rng: np.random.Generator) -> tuple[int, float]:
        """ Draws a choice; returns (index, its probability). Single choices are not randomised. """
        if len(choices) == 1:
            return 0, 1.0
        p = self.distribution(sim, choices, memory)
        i = int(rng.choice(len(choices), p=p))
        return i, float(p[i])


class UniformScheduler(Scheduler):
    def distribution(self, sim, choices, memory):
        return np.full(len(choices), 1.0 / len(choices))


class ActionWeightScheduler(Scheduler):
    """
    Memoryless, state-independent: each choice gets a fixed weight by action name, normalised over the enabled
    choices (uniform if all enabled weights are zero). `weights` is a dict or a function of the action name.
    """
    def __init__(self, weights: Union[dict[str, float], Callable[[str], float]]):
        self.weight = weights.get if isinstance(weights, dict) else weights
        self._cache: dict[tuple[str, ...], np.ndarray] = {}

    def distribution(self, sim, choices, memory):
        key = tuple(choices)
        p = self._cache.get(key)
        if p is None:
            w = np.array([self.weight(c) or 0.0 for c in choices], dtype=float)
            p = w / w.sum() if w.sum() > 0 else np.full(len(choices), 1.0 / len(choices))
            self._cache[key] = p
        return p

    def weight_of(self, action: str) -> float:
        return self.weight(action) or 0.0


def arrival_count_scheduler(probs: Union[list[float], dict[int, list[float]]],
                            pattern: str = r"_IQ(\d+)_K(\d+)$") -> ActionWeightScheduler:
    """
    Traffic scheduler over actions named ..._IQ<q>_K<k> (k packets arrive at input queue q): `probs` is one list
    P(k arrivals), k = 0..K, used for every queue, or a dict queue -> list. The course "Weibull" traffic is
    arrival_count_scheduler([0.4, 0.39, 0.14, 0.05, 0.02]).
    """
    rx = re.compile(pattern)

    def weight(action: str) -> float:
        m = rx.search(action)
        if not m:
            return 0.0
        q, k = int(m[1]), int(m[2])
        table = probs[q] if isinstance(probs, dict) else probs
        return table[k] if k < len(table) else 0.0
    return ActionWeightScheduler(weight)


WEIBULL_TRAFFIC = [0.4, 0.39, 0.14, 0.05, 0.02]


class PolicyScheduler(Scheduler):
    """ Wraps a function (sim, choices, memory) -> probabilities, e.g. a learned policy. """
    def __init__(self, policy: Callable[[Simulator, list[str], Any], np.ndarray]):
        self.policy = policy

    def distribution(self, sim, choices, memory):
        return np.asarray(self.policy(sim, choices, memory), dtype=float)


def action_weights(model: JaniModel, scheduler: Scheduler) -> Optional[dict[str, float]]:
    """ The per-action weights of a memoryless, state-independent scheduler (None = uniform), else ValueError. """
    if isinstance(scheduler, UniformScheduler):
        return None
    if isinstance(scheduler, ActionWeightScheduler):
        return {a: scheduler.weight_of(a) for a in set(model.edge_actions)}
    raise ValueError(f"{type(scheduler).__name__} is not given by per-action weights")


def native_policy(model: JaniModel, scheduler: Scheduler) -> NativePolicy:
    """
    The scheduler as a NativePolicy for the native batch simulators and splitting. Per-action weights stay native;
    any other scheduler is called back from C with a NativeJaniSimulator placed at (state, t), about 1 µs per decision.
    Schedulers with memory beyond the step count are not supported (splitting would have to copy the memory).
    """
    try:
        return NativePolicy(model, action_weights(model, scheduler))
    except ValueError:
        pass
    if type(scheduler).update_memory is not Scheduler.update_memory or scheduler.initial_memory() is not None:
        raise ValueError("native policies cannot carry scheduler memory; use Rollout")
    sim = NativeJaniSimulator(model)
    actions = model.edge_actions

    def fn(state: np.ndarray, t: int, enabled: np.ndarray) -> np.ndarray:
        sim.place(state, t, enabled)
        return scheduler.distribution(sim, [actions[e] for e in enabled], None)
    return NativePolicy.callback(model, fn)


@dataclass
class Anchor:
    """ Splitting anchor: simulator position plus scheduler memory. """
    sim_state: SimState
    memory: Any


class Rollout:
    """ Simulates the DTMC induced by a scheduler on a simulator, with anchors that include the scheduler memory. """
    def __init__(self, sim: Simulator, scheduler: Scheduler, rng: Optional[np.random.Generator] = None):
        self.sim, self.scheduler = sim, scheduler
        self.rng = rng or np.random.default_rng()
        self.memory = scheduler.initial_memory()

    def reset(self) -> None:
        self.sim.reset()
        self.memory = self.scheduler.initial_memory()

    def step(self) -> Optional[str]:
        """ One step under the scheduler; returns the action taken, or None on a deadlock. """
        choices = self.sim.choices()
        if not choices:
            return None
        i, _ = self.scheduler.sample(self.sim, choices, self.memory, self.rng)
        self.sim.step(i, self.rng)
        self.memory = self.scheduler.update_memory(self.memory, self.sim, choices[i])
        return choices[i]

    def run(self, horizon: int, goal: Callable[[Simulator], bool]) -> bool:
        """ Steps until goal(sim) holds (True) or the step count reaches `horizon` or a deadlock (False). """
        while True:
            if goal(self.sim):
                return True
            if self.sim.t >= horizon or self.step() is None:
                return False

    def save(self) -> Anchor:
        return Anchor(self.sim.save(), self.memory)

    def restore(self, anchor: Anchor) -> None:
        self.sim.restore(anchor.sim_state)
        self.memory = anchor.memory

"""
Tabular Q-learning of a scheduler for a step-bounded reachability goal, with potential-based reward shaping.

- Learns only at decision points (states with more than one enabled choice); steps in between are accumulated, so
  this is Q-learning on the embedded decision process (undiscounted, episodic).
- States are keyed by (simulator state, step count) when step_aware=True, because optimal schedulers for
  step-bounded goals must know the step count (memoryless schedulers over the raw state, as in modes, can cycle).
- Reward: 1 on reaching the goal. Shaping F = Φ(s') - Φ(s) with Φ = 0 at episode end telescopes to -Φ(s0), so it
  leaves the optimal policy unchanged (Ng, Harada & Russell 1999). A natural Φ is the importance function used for
  splitting, scaled to [0, 1].
- Exploration: with probability epsilon, and in unseen states, the action is drawn from a behaviour scheduler
  (e.g. the nominal traffic distribution).
"""
from dataclasses import dataclass, field
from typing import Callable, Hashable, Optional

import numpy as np

from src.netmdp.sim.jani_native import NativePolicy
from src.netmdp.sim.scheduler import Scheduler, PolicyScheduler, action_weights
from src.netmdp.sim.simulator import NativeJaniSimulator, Simulator


@dataclass
class TrainingLog:
    episodes: int = 0
    successes: int = 0
    first_success: Optional[int] = None
    success_curve: list[float] = field(default_factory=list)  # success rate per block of `log_every` episodes


class ShapedQLearning:
    def __init__(self, sim: Simulator, goal: Callable[[Simulator], bool], horizon: int,
                 behaviour: Scheduler, potential: Optional[Callable[[Simulator], float]] = None,
                 alpha: float = 0.2, epsilon: float = 0.1, step_aware: bool = True):
        self.sim, self.goal, self.horizon = sim, goal, horizon
        self.behaviour = behaviour
        self.potential = potential or (lambda s: 0.0)
        self.alpha, self.epsilon, self.step_aware = alpha, epsilon, step_aware
        self.q: dict[Hashable, np.ndarray] = {}

    def _key(self) -> Hashable:
        return (self.sim.key(), self.sim.t) if self.step_aware else self.sim.key()

    def _greedy(self, values: np.ndarray, rng: np.random.Generator) -> int:
        best = np.flatnonzero(values == values.max())
        return int(best[0] if len(best) == 1 else rng.choice(best))

    def episode(self, rng: np.random.Generator, explore: bool = True) -> bool:
        """
        One episode; the Q-updates for its decisions are applied afterwards in reverse order, so a reward
        propagates along the whole episode at once (still Q-learning, only the update order differs).
        """
        sim = self.sim
        sim.reset()
        decisions: list[list] = []   # [Q row, action, shaped reward accumulated until the next decision]
        phi = self.potential(sim)
        reward, done = 0.0, False
        while True:
            if self.goal(sim):
                reward, done = 1.0, True
            elif sim.t >= self.horizon:
                done = True
            choices = [] if done else sim.choices()
            if not choices:
                break
            a = 0
            if len(choices) > 1:
                row = self.q.get(k := self._key())
                if row is None:
                    row = self.q[k] = np.zeros(len(choices))
                    a, _ = self.behaviour.sample(sim, choices, None, rng)
                elif explore and rng.random() < self.epsilon:
                    a, _ = self.behaviour.sample(sim, choices, None, rng)
                else:
                    a = self._greedy(row, rng)
                decisions.append([row, a, 0.0])
            sim.step(a, rng)
            new_phi = self.potential(sim)
            if decisions:
                decisions[-1][2] += new_phi - phi
            phi = new_phi
        if decisions:          # terminal: reward, and Φ(end) = 0
            decisions[-1][2] += reward - phi
        next_value = 0.0
        for row, a, acc in reversed(decisions):
            row[a] += self.alpha * (acc + next_value - row[a])
            next_value = row.max()
        return reward > 0

    def train(self, episodes: int, rng: np.random.Generator, log_every: int = 1000,
              stop_after_success_rate: Optional[float] = None) -> TrainingLog:
        log, block = TrainingLog(), 0
        for i in range(episodes):
            ok = self.episode(rng)
            log.episodes += 1
            log.successes += ok
            block += ok
            if ok and log.first_success is None:
                log.first_success = i + 1
            if (i + 1) % log_every == 0:
                log.success_curve.append(block / log_every)
                if stop_after_success_rate is not None and block / log_every >= stop_after_success_rate:
                    break
                block = 0
        return log

    def greedy_scheduler(self) -> Scheduler:
        """ The learned policy: greedy in known states, the behaviour scheduler elsewhere. Freeze before estimating. """
        def policy(sim: Simulator, choices: list[str], memory) -> np.ndarray:
            row = self.q.get((sim.key(), sim.t) if self.step_aware else sim.key())
            if row is None or len(row) != len(choices):
                return self.behaviour.distribution(sim, choices, memory)
            p = np.zeros(len(choices))
            p[int(np.argmax(row))] = 1.0
            return p
        return PolicyScheduler(policy)

    def greedy_native_policy(self) -> NativePolicy:
        """
        greedy_scheduler() as a native table policy (keys: all state variables, plus the step count when step-aware)
        for the native batch simulators and splitting. Needs the native backend and a behaviour scheduler given by
        per-action weights, which handles states missing from the table, as in greedy_scheduler().
        """
        if not isinstance(self.sim, NativeJaniSimulator):
            raise ValueError("greedy_native_policy needs a NativeJaniSimulator")
        model = self.sim.model
        rows = {}
        for key, row in self.q.items():
            state_bytes, t = key if self.step_aware else (key, None)
            state = np.frombuffer(state_bytes, dtype=np.int32).copy()
            enabled = model.enabled_edges(state)
            if len(enabled) == len(row):
                rows[tuple(int(v) for v in state) + ((t,) if self.step_aware else ())] = int(enabled[np.argmax(row)])
        return NativePolicy.table(model, rows, step=self.step_aware,
                                  default=action_weights(model, self.behaviour))

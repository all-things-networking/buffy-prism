"""
Simulator interface for MDP/DTMC models, with resumable anchors, and two backends:
NativeJaniSimulator (compiled JANI, fast) and StormpyPrismSimulator (stormpy's PRISM simulator, reference).

A simulator holds a current state; `choices()` lists the enabled nondeterministic choices by action name (one entry
per enabled edge/command, in a fixed order), `step(i, rng)` takes choice i and resolves its probabilistic outcome.
`save()`/`restore()` capture and resume the full simulation position (state and step count) in O(1), which is what
importance splitting needs for its anchors. A scheduler (scheduler.py) resolves the choices, which induces a DTMC.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Hashable, Optional, Union

import numpy as np

from src.netmdp.sim.jani_native import JaniModel


@dataclass(frozen=True)
class SimState:
    """ An anchor: the backend's state snapshot and the number of steps taken. """
    state: Any
    t: int


class Simulator(ABC):
    variables: list[str]

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def choices(self) -> list[str]: ...

    @abstractmethod
    def step(self, choice: int, rng: np.random.Generator) -> None: ...

    @abstractmethod
    def get(self, var: str) -> int: ...

    @abstractmethod
    def save(self) -> SimState: ...

    @abstractmethod
    def restore(self, anchor: SimState) -> None: ...

    @property
    @abstractmethod
    def t(self) -> int: ...

    def key(self) -> Hashable:
        """ A hashable value identifying the current state (without the step count). """
        return tuple(self.valuation().items())

    def valuation(self) -> dict[str, int]:
        return {v: self.get(v) for v in self.variables}


class NativeJaniSimulator(Simulator):
    def __init__(self, model: Union[JaniModel, str, Path], **jani_kwargs):
        self.model = model if isinstance(model, JaniModel) else JaniModel(model, **jani_kwargs)
        self.variables = [v.name for v in self.model.variables]
        self._index = self.model.index
        self._s = self.model.initial_state()
        self._t = 0
        self._enabled: Optional[np.ndarray] = None

    def reset(self) -> None:
        self._s = self.model.initial_state()
        self._t = 0
        self._enabled = None

    def enabled_edges(self) -> np.ndarray:
        if self._enabled is None:
            self._enabled = self.model.enabled_edges(self._s)
        return self._enabled

    def choices(self) -> list[str]:
        return [self.model.edge_actions[e] for e in self.enabled_edges()]

    def step(self, choice: int, rng: np.random.Generator) -> None:
        self.model.step(self._s, int(self.enabled_edges()[choice]), rng.random())
        self._t += 1
        self._enabled = None

    def get(self, var: str) -> int:
        return int(self._s[self._index[var]])

    @property
    def state(self) -> np.ndarray:
        return self._s

    def save(self) -> SimState:
        return SimState(self._s.tobytes(), self._t)

    def restore(self, anchor: SimState) -> None:
        self._s = np.frombuffer(anchor.state, dtype=np.int32).copy()
        self._t = anchor.t
        self._enabled = None

    @property
    def t(self) -> int:
        return self._t

    def key(self) -> Hashable:
        return self._s.tobytes()


class StormpyPrismSimulator(Simulator):
    """ Reference backend on stormpy's PrismSimulator; anchors are Storm's compressed states (no prefix replay). """
    def __init__(self, prism_path: Union[str, Path]):
        import stormpy
        import stormpy.simulator as ssim
        self._program = stormpy.parse_prism_program(str(prism_path))
        self._sim = ssim.create_simulator(self._program)
        self._sim.set_action_mode(ssim.SimulatorActionMode.INDEX_LEVEL)
        self._sim.set_observation_mode(ssim.SimulatorObservationMode.PROGRAM_LEVEL)
        self.variables = [v.name for m in self._program.modules
                          for v in list(m.integer_variables) + list(m.boolean_variables)]
        self._t = 0
        self._obs = None
        self.reset()

    def reset(self) -> None:
        self._obs, _, _ = self._sim.restart()
        self._t = 0

    def choices(self) -> list[str]:
        engine = self._sim._engine
        return [self._program.get_action_name(i) or "τ" for i in engine.get_action_indices()]

    def step(self, choice: int, rng: np.random.Generator) -> None:
        # Storm samples the probabilistic outcome with its own generator; seed it with set_seed for repeatability.
        self._obs, _, _ = self._sim.step(int(choice))
        self._t += 1

    def get(self, var: str) -> int:
        return int(self._obs[var])

    def save(self) -> SimState:
        return SimState(self._sim._engine.get_current_state(), self._t)

    def restore(self, anchor: SimState) -> None:
        self._obs, _, _ = self._sim.restart(anchor.state)
        self._t = anchor.t

    @property
    def t(self) -> int:
        return self._t

    def set_seed(self, seed: int) -> None:
        self._sim.set_seed(seed)

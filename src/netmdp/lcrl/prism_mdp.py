"""A black-box MDP over an arbitrary PRISM program, exposing the API that the
LCRL tool (https://github.com/grockious/lcrl) expects of a custom MDP.

LCRL learns a policy that maximises the probability of satisfying an LTL/LDBA
objective over a user-supplied MDP. Per its README ("Applying LCRL to a custom
black-box MDP and a custom LTL property") and its Q-learning core
(``lcrl.core.lcrl_core``), the MDP object must expose:

    * ``reset()``                -> reset to the initial state
    * ``step(action)``           -> apply ``action``, return the next state (a list)
    * ``state_label(state)``     -> the label(s) of ``state`` (read by the LDBA)
    * ``current_state``          -> the current state, as a ``list``
    * ``action_space``           -> a fixed list of actions, used for every state
    * ``initial_state``          -> the initial state, as a ``list``

This class realises that interface on top of a StormPy program-level simulator,
so it works for *any* PRISM model (DTMC or MDP). Actions are integer indices into
the choices StormPy makes available at the current state (``INDEX_LEVEL`` action
mode), which -- unlike action *names* -- unambiguously select among equally-named
nondeterministic branches.

Two impedance mismatches between PRISM and LCRL are handled here:

1.  **Fixed vs. per-state action space.** LCRL uses one ``action_space`` for
    every state, whereas a PRISM state may enable a different number of choices.
    ``action_space`` is ``[0 .. num_actions-1]`` where ``num_actions`` is the
    maximum branching (auto-detected or supplied), and an action that is out of
    range in the current state is remapped onto an available one -- see
    ``out_of_range``. In a state with a single choice (every DTMC state, and the
    deterministic states of an MDP) every action collapses to that one choice,
    which is exactly correct.

2.  **Atomic propositions for the LDBA.** The labels the LDBA reads are the
    atomic propositions of the LTL property, which are generally richer than the
    ``label`` declarations in the ``.pm`` file. Supply a ``label_fn`` mapping a
    state (``{var: value}`` dict) to a list of proposition strings; if omitted,
    the model's declared PRISM labels are used.
"""

import json
import random

import stormpy
import stormpy.simulator as sim
from stormpy import PrismProgram

from src.netmdp.prism_utils.prism_utils import load_prism_program


class PrismBlackBoxMDP:
    def __init__(
        self,
        program: PrismProgram,
        *,
        state_variables=None,
        label_fn=None,
        num_actions=None,
        out_of_range: str = "clamp",
        discovery_rollouts: int = 8,
        discovery_horizon: int = 512,
        seed=None,
    ):
        """
        Parameters
        ----------
        program:
            A fully-instantiated ``PrismProgram`` (see ``from_file`` / the
            ``load_prism_program`` helper for arbitrary ``.pm`` files with
            undefined constants).
        state_variables:
            Optional ordered list of program variable names to expose as the RL
            state. Defaults to every variable (sorted), which is faithful but can
            be large; project to the relevant variables to keep the Q-table
            tractable. The ordering is fixed and used for ``current_state``.
        label_fn:
            Optional ``callable(state_dict) -> iterable[str]`` returning the
            atomic propositions true in a state, where ``state_dict`` maps *all*
            program variables to their values. Defaults to the model's declared
            PRISM labels reported by the simulator.
        num_actions:
            Size of the (fixed) action space. If ``None``, it is auto-detected as
            the maximum number of available choices seen over a handful of random
            rollouts -- a heuristic; pass an explicit value if a high-branching
            state might be missed.
        out_of_range:
            Policy for an action index not available in the current state:
            ``"clamp"`` (use the last available choice), ``"mod"`` (wrap with
            modulo), or ``"stay"`` (self-loop, state unchanged).
        discovery_rollouts, discovery_horizon:
            Budget for ``num_actions`` auto-detection.
        seed:
            Optional RNG seed for the simulator.
        """
        if out_of_range not in ("clamp", "mod", "stay"):
            raise ValueError(f"unknown out_of_range policy: {out_of_range!r}")

        self.program = program
        self._out_of_range = out_of_range
        self._label_fn = label_fn
        self._state_variables = list(state_variables) if state_variables is not None else None
        self._var_order = list(state_variables) if state_variables is not None else None

        self._sim = self._make_simulator(program, seed)

        # State bookkeeping, populated by _record.
        self._full_state = None      # {var: value} for the current state
        self._labels = []            # labels of the current state
        self.current_state = None    # list, per _var_order

        if num_actions is None:
            num_actions = self._discover_num_actions(discovery_rollouts, discovery_horizon)
        if num_actions < 1:
            raise ValueError("num_actions must be >= 1")
        self.action_space = list(range(num_actions))

        self.reset()
        self.initial_state = self.current_state.copy()

    # ------------------------------------------------------------------ #
    # construction helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def from_file(cls, path: str, constants=None, **kwargs) -> "PrismBlackBoxMDP":
        """Build directly from a ``.pm`` path, instantiating undefined constants
        (``constants`` may be a dict or a ``"K=V,..."`` string)."""
        return cls(load_prism_program(path, constants), **kwargs)

    @staticmethod
    def _make_simulator(program, seed):
        simulator = sim.create_simulator(program, seed=seed)
        # INDEX_LEVEL: an action is an integer index into the current choices,
        # which disambiguates equally-named nondeterministic branches.
        simulator.set_action_mode(sim.SimulatorActionMode.INDEX_LEVEL)
        simulator.set_observation_mode(sim.SimulatorObservationMode.PROGRAM_LEVEL)
        return simulator

    def _discover_num_actions(self, rollouts, horizon):
        """Heuristically find the maximum branching by random exploration."""
        max_actions = 1
        for _ in range(max(1, rollouts)):
            self._sim.restart()
            for _ in range(max(1, horizon)):
                n = self._sim.nr_available_actions()
                if n > max_actions:
                    max_actions = n
                if self._sim.is_done() or n == 0:
                    break
                self._sim.step(random.randrange(n))
        return max_actions

    # ------------------------------------------------------------------ #
    # LCRL MDP interface
    # ------------------------------------------------------------------ #
    def reset(self):
        state, _reward, labels = self._sim.restart()
        self._record(state, labels)
        return self.current_state

    def step(self, action):
        """Apply ``action`` (an index into ``action_space``) and return the next
        state as a list. Absorbing/deadlocked states self-loop."""
        if not self._sim.is_done():
            choice = self._resolve_action(action)
            if choice is not None:
                state, _reward, labels = self._sim.step(choice)
                self._record(state, labels)
        return self.current_state

    def state_label(self, state):
        """Labels (atomic propositions) of ``state``.

        LCRL always calls this on the state most recently returned by ``step`` /
        ``reset``, so we return the labels captured for the current simulator
        state; the ``state`` argument is accepted for API compatibility.
        """
        return self._labels

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _record(self, json_state, storm_labels):
        full = json.loads(str(json_state))
        self._full_state = full
        if self._var_order is None:
            self._var_order = sorted(full.keys())
        self.current_state = [full[v] for v in self._var_order]
        if self._label_fn is not None:
            self._labels = list(self._label_fn(full))
        else:
            self._labels = list(storm_labels)

    def _resolve_action(self, action):
        n = self._sim.nr_available_actions()
        if n == 0:
            return None
        if 0 <= action < n:
            return action
        if self._out_of_range == "clamp":
            return n - 1
        if self._out_of_range == "mod":
            return action % n
        return None  # "stay"

    # ------------------------------------------------------------------ #
    # conveniences (not required by LCRL)
    # ------------------------------------------------------------------ #
    @property
    def state_variables(self):
        """Ordered variable names corresponding to entries of ``current_state``."""
        return list(self._var_order) if self._var_order is not None else None

    @property
    def full_state(self):
        """The current state as a ``{var: value}`` dict over all program variables."""
        return dict(self._full_state) if self._full_state is not None else None

    def is_done(self):
        """Whether the simulator is in an absorbing/sink state."""
        return self._sim.is_done()

    def __str__(self):
        n = len(self.action_space)
        d = len(self._var_order) if self._var_order else 0
        return f"PrismBlackBoxMDP[vars={d}, actions={n}]"

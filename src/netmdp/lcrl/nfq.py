"""Adapter to run LCRL's neural-fitted Q-iteration (``train_nfq``) over a
PrismBlackBoxMDP.

LCRL's ``train_nfq`` / ``train_ddpg`` expect ``MDP.current_state`` to be a
**numpy array** (they call ``current_state.tolist()`` and treat it as a feature
vector), whereas the tabular ``train_ql`` path needs a plain Python **list** (it
does ``current_state + [automaton_state]`` and uses ``str(current_state)`` as a
Q-table key). The two are incompatible on the base class, so this subclass
exposes ``current_state`` as an ``np.ndarray`` for the NFQ/DDPG path only.

Usage mirrors PrismBlackBoxMDP, then hand it to LCRL with ``algorithm='nfq'``:

    from src.netmdp.lcrl.nfq import NFQMDP
    from src.netmdp.lcrl.props import PrismProperties
    from src.netmdp.lcrl.owl import find_owl
    props = PrismProperties(pm_path=PM, constants=C, owl_path=find_owl())
    prop = props[0]
    mdp = NFQMDP.from_file(PM, constants=C, label_fn=prop.label_fn(),
                           state_variables=[...])   # project! NFQ input is |state|+1
    agent = ShapedLCRL(MDP=mdp, LDBA=prop.ldba, ...)      # dense reward still applies
    agent.train_nfq(number_of_episodes, iteration_threshold, nfq_replay_buffer_size,
                    num_of_hidden_neurons=64)

Caveats confirmed against lcrl 1.x (the adapter itself is verified working -- the
MDP hands NFQ an ndarray state correctly):
  * Set ``decaying_learning_rate=False`` on the LCRL/ShapedLCRL constructor, else
    ``train_nfq`` blocks on an interactive ``input()`` prompt (EOF in batch runs).
  * ``iteration_threshold`` MUST be long enough that episodes actually reach the
    accepting state, and at least one episode must reach it. ``train_nfq`` builds
    its target set from "rewarding paths" and does ``high_reward_total[:, -1]``
    (lcrl_core ~L386), which raises ``IndexError`` on the empty (1-D) array when
    no rewarding path has been collected yet. Size episodes/exploration so the
    goal is hit early (for reachable Pmax objectives this is easy).
  * It is SLOW -- a Keras fit runs frequently, so even small smoke tests take many
    minutes. Prefer it only where the tabular greedy provably fails to generalise.
  * NFQ needs a genuine feature vector: keep ``state_variables`` a small numeric
    projection (input dim = |projection| + 1).

Why NFQ: a neural Q **generalises across the huge product state**, which is the
wall the tabular greedy hits on rare-event / fine-abstraction objectives (incast
Pmin, fqcodel worst-case). See experiments/README.md sec.5 and METHODOLOGY.md.
"""

import numpy as np

from src.netmdp.lcrl.prism_mdp import PrismBlackBoxMDP


class NFQMDP(PrismBlackBoxMDP):
    def _record(self, json_state, storm_labels):
        super()._record(json_state, storm_labels)
        # NFQ/DDPG treat current_state as a numeric feature vector.
        self.current_state = np.asarray(self.current_state, dtype=float)

"""Glue the PRISM black-box MDP and the OWL-derived LDBA into an LCRL run.

Given a ``.pm`` model and the property (a line of the sibling ``.props`` file)
to learn a policy for, ``build_mdp_and_ldba`` produces the ``(MDP, LDBA)`` pair
that LCRL consumes, and ``run_lcrl_from_prism`` hands them to ``lcrl.train``.
"""

import matplotlib

matplotlib.use("Agg")  # LCRL's train() calls plt.show(); keep it headless/non-blocking

from lcrl.train import train

from src.netmdp.lcrl.prism_mdp import PrismBlackBoxMDP
from src.netmdp.lcrl.props import PrismProperties


def build_mdp_and_ldba(
    pm_path,
    prop_index=0,
    constants=None,
    *,
    props_path=None,
    owl_path=None,
    state_variables=None,
    **mdp_kwargs,
):
    """Return ``(mdp, ldba, parsed_property)`` for property ``prop_index``.

    ``mdp`` is a ``PrismBlackBoxMDP`` whose ``label_fn`` emits exactly the atomic
    propositions the property's LDBA reads; ``ldba`` is the OWL-derived
    LCRL LDBA. Extra keyword arguments are forwarded to ``PrismBlackBoxMDP``.
    """
    props = PrismProperties(
        props_path=props_path, pm_path=pm_path,
        constants=constants, owl_path=owl_path,
    )
    if prop_index >= len(props):
        detail = "; ".join(f"{raw!r}: {err}" for raw, err in props.errors)
        raise IndexError(
            f"property index {prop_index} out of range: only {len(props)} "
            f"supported propert(ies) in {props.props_path}."
            + (f" Skipped: {detail}" if detail else "")
        )
    prop = props[prop_index]
    mdp = PrismBlackBoxMDP.from_file(
        pm_path,
        constants=constants,
        label_fn=prop.label_fn(),
        state_variables=state_variables,
        **mdp_kwargs,
    )
    return mdp, prop.ldba, prop


def run_lcrl_from_prism(
    pm_path,
    prop_index=0,
    constants=None,
    *,
    props_path=None,
    owl_path=None,
    state_variables=None,
    algorithm="ql",
    episode_num=500,
    iteration_num_max=4000,
    discount_factor=0.95,
    learning_rate=0.9,
    test=False,
    mdp_kwargs=None,
):
    """Build the product from a ``.pm``/``.props`` pair and run LCRL on it.

    Returns ``(task, mdp, ldba, parsed_property)`` where ``task`` is the trained
    LCRL object returned by ``lcrl.train.train``.
    """
    mdp, ldba, prop = build_mdp_and_ldba(
        pm_path, prop_index, constants,
        props_path=props_path, owl_path=owl_path,
        state_variables=state_variables, **(mdp_kwargs or {}),
    )
    task = train(
        mdp, ldba,
        algorithm=algorithm,
        episode_num=episode_num,
        iteration_num_max=iteration_num_max,
        discount_factor=discount_factor,
        learning_rate=learning_rate,
        test=test,
    )
    return task, mdp, ldba, prop

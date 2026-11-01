"""
Exports the DTMC induced by a memoryless, state-independent scheduler (ActionWeightScheduler) on a JANI MDP, so that
tools such as modes can estimate probabilities under it (e.g. with importance splitting).

Edges of the single automaton that share a location and an identical guard form one choice group (they are always
enabled together). A group with positive total weight becomes one edge whose destinations are the union of the
group's destinations, each probability multiplied by weight / total weight. This yields exactly the induced DTMC
provided that, in every state, the enabled edges form one such group or a single edge; otherwise the remaining
nondeterminism is left in the model (and modes resolves it uniformly, with a warning).
"""
import copy
import json
from fractions import Fraction
from typing import Union

from src.netmdp.sim.scheduler import ActionWeightScheduler


def induced_dtmc_jani(mdp: dict, scheduler: ActionWeightScheduler, name_suffix: str = "_induced") -> dict:
    model = copy.deepcopy(mdp)
    if len(model["automata"]) != 1:
        raise ValueError("induced_dtmc_jani supports single-automaton models only")
    automaton = model["automata"][0]
    rename = {s["synchronise"][0]: s.get("result", s["synchronise"][0])
              for s in model.get("system", {}).get("syncs", []) if s["synchronise"][0] is not None}
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for edge in automaton["edges"]:
        key = json.dumps([edge["location"], edge.get("guard")], sort_keys=True)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(edge)
    new_edges = []
    for key in order:
        edges = groups[key]
        weights = [scheduler.weight_of(rename.get(e.get("action"), e.get("action")) or "τ") for e in edges]
        total = sum(weights)
        if len(edges) == 1 or total <= 0:
            new_edges.extend(edges)
            continue
        destinations = []
        for edge, w in zip(edges, weights):
            if w <= 0:
                continue
            share = Fraction(w).limit_denominator(10 ** 9) / Fraction(total).limit_denominator(10 ** 9)
            for d in edge["destinations"]:
                d = copy.deepcopy(d)
                prob = d.get("probability", {}).get("exp", 1)
                d["probability"] = {"exp": _times(share, prob)}
                destinations.append(d)
        new_edges.append({"location": edges[0]["location"], "guard": edges[0].get("guard"),
                          "destinations": destinations})
    automaton["edges"] = new_edges
    model["type"] = "dtmc"
    model["name"] = model.get("name", "model") + name_suffix
    # Actions no longer used by any edge must not appear in synchronisation vectors.
    used = {e.get("action") for e in new_edges if e.get("action")}
    if "system" in model and "syncs" in model["system"]:
        model["system"]["syncs"] = [s for s in model["system"]["syncs"] if s["synchronise"][0] in used]
        model["actions"] = [a for a in model.get("actions", []) if a["name"] in used]
    return model


def _times(share: Fraction, prob: Union[int, float, dict, str]) -> Union[dict, int]:
    frac = {"op": "/", "left": share.numerator, "right": share.denominator}
    if prob == 1:
        return frac
    return {"op": "*", "left": frac, "right": prob}

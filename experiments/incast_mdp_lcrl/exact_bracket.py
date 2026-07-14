#!/usr/bin/env python3
"""Exact Pmax/Pmin on *small* incast_mdp.pm instances (StormPy model checking).

Ground truth for validating the LCRL policy synthesis: on instances small enough
to build, ``Pmax[F(done & odrops>=THRESH)]`` is the true worst-case incast
probability the LCRL (max) policy should recover, and ``Pmin`` the best case.
Exact checking is intractable at the case-study corner (state space explodes),
which is why the full-scale numbers use LCRL + Monte-Carlo instead.

    PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/exact_bracket.py
"""
import os

import stormpy

from src.netmdp.prism_utils.prism_utils import load_prism_program

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MDP = os.path.join(REPO, "models", "example2_desync_short_bursts", "incast_mdp.pm")


def exact_bracket(consts):
    prog = load_prism_program(MDP, consts)
    out = {}
    for direction in ("Pmax", "Pmin"):
        props = stormpy.parse_properties(
            f'{direction}=? [ F ("done" & odrops>=THRESH) ]', prog
        )
        opts = stormpy.BuilderOptions([p.raw_formula for p in props])
        model = stormpy.build_sparse_model_with_options(prog, opts)
        result = stormpy.model_checking(model, props[0])
        out[direction] = result.at(model.initial_states[0])
        out["states"] = model.nr_states
    return out


if __name__ == "__main__":
    for consts in [
        dict(M=4, WIN=1, SLEN=1, BUF=1, THRESH=1),
        dict(M=4, WIN=2, SLEN=2, BUF=2, THRESH=2),
    ]:
        r = exact_bracket(consts)
        print(f"{consts}: Pmax={r['Pmax']}  Pmin={r['Pmin']}  states={r['states']}")

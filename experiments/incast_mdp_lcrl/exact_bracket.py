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
MODEL_DIR = os.path.join(REPO, "models", "example2_desync_short_bursts")


def exact_bracket(model, consts):
    prog = load_prism_program(os.path.join(MODEL_DIR, f"{model}.pm"), consts)
    out = {}
    for direction in ("Pmax", "Pmin"):
        props = stormpy.parse_properties(
            f'{direction}=? [ F ("done" & odrops>=THRESH) ]', prog
        )
        opts = stormpy.BuilderOptions([p.raw_formula for p in props])
        model_ = stormpy.build_sparse_model_with_options(prog, opts)
        result = stormpy.model_checking(model_, props[0])
        out[direction] = result.at(model_.initial_states[0])
        out["states"] = model_.nr_states
    return out


if __name__ == "__main__":
    # incast_mdp: per-slot start choice. Pmin=0 is degenerate (never-send).
    # incast_mdp_Pmin: forced start (wait only while slot<WIN, forced at slot=WIN),
    # so Pmin=0 means loss is avoidable by spreading starts WHILE all senders send.
    for model in ("incast_mdp", "incast_mdp_Pmin"):
        print(f"# {model}")
        for consts in [
            dict(M=4, WIN=1, SLEN=1, BUF=1, THRESH=1),
            dict(M=4, WIN=2, SLEN=2, BUF=2, THRESH=2),
        ]:
            r = exact_bracket(model, consts)
            print(f"  {consts}: Pmax={r['Pmax']}  Pmin={r['Pmin']}  states={r['states']}")

#!/usr/bin/env python3
"""DTMC reference values for the incast case study.

Simulates the original DTMC ``incast.pm`` (uniform random start times built in)
and reports ``P[Q] = P[odrops>=THRESH]`` at given corners -- the numbers the
LCRL ``uniform_hazard`` policy on the MDP should reproduce, and that the case
study's NOTES.md reports (0.54 at the M=16 least-favorable corner).

    PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/dtmc_reference.py
"""
import json
import os
import random

import stormpy.simulator as sim

from src.netmdp.prism_utils.prism_utils import load_prism_program

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DTMC = os.path.join(REPO, "models", "example2_desync_short_bursts", "incast.pm")


def dtmc_pq(consts, n=400, seed=0):
    prog = load_prism_program(DTMC, consts)
    s = sim.create_simulator(prog)
    s.set_action_mode(sim.SimulatorActionMode.INDEX_LEVEL)
    s.set_observation_mode(sim.SimulatorObservationMode.PROGRAM_LEVEL)
    random.seed(seed)
    horizon = consts["WIN"] + consts["M"] * consts["SLEN"] + consts["SLEN"]
    hits, total = 0, 0.0
    for _ in range(n):
        state, _r, _l = s.restart()
        for _ in range(21 * (horizon + 2)):
            if s.is_done():
                break
            state, _r, _l = s.step(random.randrange(s.nr_available_actions()))
        odrops = json.loads(str(state))["odrops"]
        hits += odrops >= consts["THRESH"]
        total += odrops
    return hits / n, total / n


if __name__ == "__main__":
    for M in (16, 20):
        c = dict(BUF=32, THRESH=8, M=M, WIN=96, SLEN=8)
        p, mean = dtmc_pq(c)
        print(f"DTMC incast.pm {c}: P[Q]={p:.3f}  mean_odrops={mean:.2f}")

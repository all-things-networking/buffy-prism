#!/usr/bin/env python3
"""Generate IQ5 input *schedules* by guarding the IQ5 arrival rule on `time`.

Unlike gen_q5_variants.py (which sets a stationary arrival distribution), this lets
IQ5 send a single packet only on a chosen SET of time steps (and optionally send
randomly after a warm-up).  This is what exposes the real driver of starvation:
IQ5 must stay IDLE during the warm-up (t=0..3, while IQ1..IQ4 fill up and migrate
into the OLD list) and only THEN become active -- so each IQ5 packet enters the
NEW list and jumps ahead of the backlogged OLD queues, repeatedly.

Usage:  python3 gen_q5_schedules.py     # writes the headline schedules below
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "fqcodel_5i_dtmc_unif.pm")
S = "(stage'=REC_PKT_ARR_IQ5)"

def _base_line():
    txt = open(BASE).read()
    line = [l for l in txt.splitlines() if "[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 ->" in l][0]
    return txt, line

def deterministic(name, times):
    """IQ5 sends exactly one packet on each step in `times`, nothing otherwise."""
    txt, line = _base_line()
    g = "(" + "|".join(f"time={t}" for t in times) + ")"
    rules = (f"\t[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 & {g} -> {S} & (iq5_arrivals'=1);\n"
             f"\t[REC_PKT_GET_IQ5b] stage=REC_PKT_GET_IQ5 & !{g} -> {S} & (iq5_arrivals'=0);")
    open(os.path.join(HERE, name), "w").write(txt.replace(line, rules))

def idle_then_random(name, warmup, p):
    """IQ5 idle while time<=warmup; afterwards sends 1 packet w.p. p (NON-periodic)."""
    txt, line = _base_line()
    rules = (f"\t[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 & time<={warmup} -> {S} & (iq5_arrivals'=0);\n"
             f"\t[REC_PKT_GET_IQ5b] stage=REC_PKT_GET_IQ5 & time>{warmup} -> "
             f"{1-p:.2f} : {S} & (iq5_arrivals'=0) + {p:.2f} : {S} & (iq5_arrivals'=1);")
    open(os.path.join(HERE, name), "w").write(txt.replace(line, rules))

if __name__ == "__main__":
    WARM = list(range(4, 14))                       # post-warm-up steps t=4..13
    deterministic("q5sch_idle_everystep.pm", WARM)  # idle, then every step  -> deqs_bl up to 10
    deterministic("q5sch_idle_every2.pm", WARM[::2]) # idle, then 1/2 steps  -> P(>=5)=0.97
    deterministic("q5sch_send_in_warmup.pm", [0,4,8,12])  # sends during warm-up -> weak (P(>=4)=0.55)
    idle_then_random("q5sch_idle_random.pm", 3, 0.6)# idle, then Bernoulli .6 -> P(>=4)=0.85 (non-periodic)
    print("wrote q5sch_{idle_everystep,idle_every2,send_in_warmup,idle_random}.pm")

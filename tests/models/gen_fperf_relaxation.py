#!/usr/bin/env python3
"""Generate the models used in FPERF_RELAXATION.md: relaxations of FPerf's certain
FQ-CoDel workload (C1 quiet-early, C2 rate, C4 background-backlog).

All use natural random background for Q1..Q4 unless a background mode is given.
Measure with:  P=? [ G<=(224) (iq5_deqs_bl<n) ]   (problem = Q5 dequeues >= n while all
Q1..Q4 backlogged; FPerf's threshold for T=14 is n=5 = 2*floor(T/5)+1).

Usage:  python3 gen_fperf_relaxation.py     # writes fprlx_*.pm
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "fqcodel_5i_dtmc_unif.pm")
S = "(stage'=REC_PKT_ARR_IQ5)"

def _base():
    txt = open(BASE).read()
    l5 = [l for l in txt.splitlines() if "[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 ->" in l][0]
    return txt, l5

def _set_bg(txt, mode):           # constrain Q1..Q4 (for the C4 experiment)
    if mode == "natural":
        return txt
    for q in (1, 2, 3, 4):
        stg, nxt = f"REC_PKT_GET_IQ{q}", f"REC_PKT_ARR_IQ{q}"
        old = [l for l in txt.splitlines() if f"[{stg}] stage={stg} ->" in l][0]
        Sq = f"(stage'={nxt})"
        if mode == "full":     new = f"\t[{stg}] stage={stg} -> {Sq} & (iq{q}_arrivals'=4);"
        elif mode == "noidle": new = f"\t[{stg}] stage={stg} -> " + " + ".join(
            f"0.25:{Sq}&(iq{q}_arrivals'={k})" for k in (1, 2, 3, 4)) + ";"
        txt = txt.replace(old, new)
    return txt

def det(name, times, bg="natural"):     # Q5 sends 1 pkt at each t in `times`
    txt, l5 = _base()
    g = "(" + "|".join(f"time={t}" for t in times) + ")"
    rules = (f"\t[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 & {g} -> {S} & (iq5_arrivals'=1);\n"
             f"\t[REC_PKT_GET_IQ5b] stage=REC_PKT_GET_IQ5 & !{g} -> {S} & (iq5_arrivals'=0);")
    open(os.path.join(HERE, name), "w").write(_set_bg(txt.replace(l5, rules), bg))

def bern(name, warm, p, bg="natural"):  # idle while time<warm, then Bernoulli(p) single pkts
    txt, l5 = _base()
    rules = (f"\t[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 & time<{warm} -> {S} & (iq5_arrivals'=0);\n"
             f"\t[REC_PKT_GET_IQ5b] stage=REC_PKT_GET_IQ5 & time>={warm} -> "
             f"{1-p:.2f}:{S}&(iq5_arrivals'=0) + {p:.2f}:{S}&(iq5_arrivals'=1);")
    open(os.path.join(HERE, name), "w").write(_set_bg(txt.replace(l5, rules), bg))

if __name__ == "__main__":
    # C4: Q5 = quiet-then-every-2-steps, vary the background constraint
    for bg in ("full", "noidle", "natural"):
        det(f"fprlx_c4_{bg}.pm", list(range(4, 14, 2)), bg=bg)
    # C1: relax the quiet-early period (active = every step, natural bg)
    for W in range(0, 6):
        det(f"fprlx_c1_quiet{W}.pm", list(range(W, 14)))
    # C2: relax the rate (quiet first 4 steps fixed, natural bg)
    det("fprlx_c2_every1.pm", list(range(4, 14)))
    det("fprlx_c2_every2.pm", list(range(4, 14, 2)))
    det("fprlx_c2_every3.pm", list(range(4, 14, 3)))
    for p in (30, 50, 70):
        bern(f"fprlx_c2_rand{p}.pm", 4, p / 100)
    # C3: relax the packet COUNT (quiet first 4 steps fixed, keep spacing>=2 while possible)
    det("fprlx_c3_K4.pm",  [4, 7, 10, 13])                 # 4 pkts (below the query threshold)
    det("fprlx_c3_K5.pm",  [4, 6, 8, 10, 12])              # 5 pkts (= FPerf C3)
    det("fprlx_c3_K6.pm",  [4, 6, 8, 10, 12, 13])          # 6 pkts (one gap=1)
    det("fprlx_c3_K7.pm",  [4, 6, 8, 10, 11, 12, 13])      # 7 pkts (several gap=1)
    det("fprlx_c3_K10.pm", list(range(4, 14)))             # 10 pkts (every step -> spacing collapses)
    print("wrote fprlx_c4_*, fprlx_c1_quiet*, fprlx_c2_* into", HERE)

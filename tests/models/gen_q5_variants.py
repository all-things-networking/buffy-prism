#!/usr/bin/env python3
"""Generate controlled-input variants of the FQ-CoDel model that fix IQ5's
arrival *shape* while keeping the buggy scheduler untouched.

Each variant only rewrites the single IQ5 arrival rule
  [REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 -> ...
so we can ask "what is P(IQ5 starves the others) under THIS input pattern?".

Usage:  python3 gen_q5_variants.py            # writes variants into ./ (tests/models)
"""
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, "fqcodel_5i_dtmc_unif.pm")
S = "(stage'=REC_PKT_ARR_IQ5)"

def base_text():
    txt = open(BASE).read()
    line = [l for l in txt.splitlines() if "[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 ->" in l][0]
    return txt, line

def bernoulli(p):
    """IQ5 sends a single packet with prob p, else nothing (mean load = p)."""
    return f"{1-p:.3f} : {S} & (iq5_arrivals'=0) + {p:.3f} : {S} & (iq5_arrivals'=1)"

def burst(p, k):
    """IQ5 sends a k-packet burst with prob p, else nothing (mean load = p*k)."""
    return f"{1-p:.3f} : {S} & (iq5_arrivals'=0) + {p:.3f} : {S} & (iq5_arrivals'={k})"

def write_bernoulli(name, p):
    txt, line = base_text()
    open(os.path.join(HERE, name), "w").write(txt.replace(line, "\t[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 -> " + bernoulli(p) + ";"))

def write_burst(name, p, k):
    txt, line = base_text()
    open(os.path.join(HERE, name), "w").write(txt.replace(line, "\t[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 -> " + burst(p, k) + ";"))

def write_periodic(name, K):
    """IQ5 sends exactly one packet every K steps (deterministic, sparse)."""
    txt, line = base_text()
    anchor = "\tiq5_max_arr: [0..4] init 0;"
    txt = txt.replace(anchor, anchor + f"\n\tiq5_clk: [0..{K-1}] init 0;")
    rules = (f"\t[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 & mod(iq5_clk,{K})=0 -> {S} & (iq5_arrivals'=1) & (iq5_clk'=mod(iq5_clk+1,{K}));\n"
             f"\t[REC_PKT_GET_IQ5b] stage=REC_PKT_GET_IQ5 & mod(iq5_clk,{K})!=0 -> {S} & (iq5_arrivals'=0) & (iq5_clk'=mod(iq5_clk+1,{K}));")
    open(os.path.join(HERE, name), "w").write(txt.replace(line, rules))

if __name__ == "__main__":
    # The headline case-study variants:
    write_periodic("q5var_per4.pm", 4)        # 1 pkt / 4 steps  -> P(starve)=0.55  *** the example ***
    write_periodic("q5var_per5.pm", 5)        # 1 pkt / 5 steps  -> sends only 3, P(>=3)=0.97
    write_bernoulli("q5var_trk30.pm", 0.30)   # 1 pkt w.p. 0.30  -> P(starve)=0.30 (Bernoulli peak)
    write_burst("q5var_bursty25.pm", 0.25, 4) # 4-pkt bursts, same mean load as trickle_det -> P=0
    write_bernoulli("q5var_dense.pm", 1.0)    # 1 pkt every step (heavy) -> P=0 (control)
    print("wrote q5var_{per4,per5,trk30,bursty25,dense}.pm into", HERE)

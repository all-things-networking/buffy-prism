#!/usr/bin/env python3
"""
Independent from-scratch simulator (oracle) for the chunked-prefill batch
scheduler. Re-implements the exact dynamics of scheduler.pm / gen_scheduler.py
WITHOUT PRISM, to (a) cross-check the PRISM/SMC probabilities and (b) run at
realistic magnitudes PRISM's simulator cannot reach.

Record 0 is the tracked "victim"; records 1..M-1 are background. Units are
generic "iterations of work": one iteration = one forward pass; decode advances
a request by 1 unit; prefill advances it by CHUNK units. So with unit = token,
CHUNK = the prefill chunk size (e.g. 512), a prompt of P tokens takes
ceil(P/CHUNK) prefill iterations and an output of O tokens takes O decode
iterations -- the realistic asymmetry.

Bad event: the victim's worst inter-token gap reaches SLO_TBT.

Usage:
  python3 sched_sim.py                 # cross-check config, prints P(stall)+CI
  (import estimate() for sweeps; see run_regions_oracle.py)
"""
import argparse, math, random

def simulate_once(p, rng):
    M = p['M']
    st = [0]*M; pp = [0]*M; oo = [0]*M; bk = [0]*M; ad = [0]*M   # record 0 = victim
    vgap = 0; vmax = 0
    GAP = p['GAPMAX']
    BIG = 10**9
    for t in range(p['T']):
        # ---- VINJECT: victim enters (waiting) at T_V, into its own record 0 ----
        if t == p['T_V'] and st[0] == 0:
            st[0] = 1; pp[0] = p['VP']; oo[0] = p['VO']; bk[0] = 0; ad[0] = t
        # ---- ARRIVE: n_arr background requests into empty bg records ----
        if p.get('lam') is not None:
            n_arr = rng.poisson(p['lam']) if hasattr(rng, 'poisson') else _pois(rng, p['lam'])
        else:
            n_arr = 1 if rng.random() < p['p_arr'] else 0
        j = 1
        for _ in range(n_arr):
            while j < M and st[j] != 0:
                j += 1
            if j >= M:
                break
            long_prompt = rng.random() < p['p_lp']
            pol = p['p_ol_lp'] if long_prompt else p['p_ol_sp']
            long_output = rng.random() < pol
            pp[j] = p['LP'] if long_prompt else p['SP']
            oo[j] = p['LO'] if long_output else p['SO']
            st[j] = 1; bk[j] = 0; ad[j] = t
            j += 1
        # ---- ADMIT: FCFS/SJF promote waiting->running while a slot is free ----
        nrun = sum(1 for i in range(M) if st[i] == 2)
        avail = p['N_SLOTS'] - nrun
        if avail > 0:
            waiting = [i for i in range(M) if st[i] == 1]
            key = (lambda i: (pp[i], i)) if p['ADM_POLICY'] == 1 else (lambda i: (ad[i], i))
            waiting.sort(key=key)
            for i in waiting[:avail]:
                st[i] = 2
        # ---- SVC: one iteration of work per running record (index order) ----
        for i in range(M):
            if st[i] == 2:
                if pp[i] > 0:                                   # prefill a chunk
                    c = min(pp[i], p['CHUNK']); bk[i] += c; pp[i] -= c
                    if i == 0:
                        vgap = min(GAP, vgap+1);  vmax = max(vmax, vgap)
                elif oo[i] > 0:                                 # decode one token
                    oo[i] -= 1; bk[i] += 1
                    if oo[i] == 0:
                        st[i] = 0; bk[i] = 0                    # finished -> free
                    if i == 0:
                        vgap = 0
                else:                                           # finished (cleanup)
                    st[i] = 0; bk[i] = 0
            elif st[i] == 1 and i == 0:                         # victim waiting -> no progress
                vgap = min(GAP, vgap+1);  vmax = max(vmax, vgap)
        # ---- PREEMPT: evict running->waiting (LIFO / priority) until KV fits ----
        kv = sum(bk)
        while kv > p['KV_CAP']:
            best = -1; best_key = None
            for i in range(M):
                if st[i] == 2 and bk[i] > 0:
                    score = ad[i] - (BIG if (i == 0 and p['POLICY'] == 1) else 0)
                    k = (score, -i)          # max score, tiebreak lower index
                    if best_key is None or k > best_key:
                        best_key = k; best = i
            if best < 0:
                break
            i = best
            st[i] = 1; pp[i] = bk[i]; kv -= bk[i]; bk[i] = 0
            if i == 0:
                vgap = min(GAP, vgap+1); vmax = max(vmax, vgap)
    return 1 if vmax >= p['SLO_TBT'] else 0

def _pois(rng, lam):
    # Knuth Poisson using a plain Random
    L = math.exp(-lam); k = 0; pr = 1.0
    while True:
        k += 1; pr *= rng.random()
        if pr <= L:
            return k-1

def estimate(p, samples=20000, seed=0):
    rng = random.Random(seed)
    s = 0
    for _ in range(samples):
        s += simulate_once(p, rng)
    mean = s / samples
    half = 2.576 * math.sqrt(max(mean*(1-mean), 1e-12) / samples)   # 99% CI
    return mean, half

DEFAULTS = dict(M=8, N_SLOTS=3, KV_CAP=64, CHUNK=1, POLICY=0, ADM_POLICY=0,
                T=64, T_V=5, p_arr=0.9, p_lp=0.3, p_ol_sp=0.3, p_ol_lp=0.3,
                SP=1, LP=4, SO=1, LO=32, VP=1, VO=2, SLO_TBT=3, GAPMAX=64, lam=None)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for k, v in DEFAULTS.items():
        ap.add_argument(f"--{k}", type=(float if isinstance(v, float) else (str if v is None else int)), default=v)
    ap.add_argument("--samples", type=int, default=20000)
    a = vars(ap.parse_args())
    samples = a.pop('samples')
    a['lam'] = None if a['lam'] in (None, 'None') else float(a['lam'])
    m, h = estimate(a, samples)
    print(f"P(stall) = {m:.4f}  (+/- {h:.4f}, 99% CI, n={samples})")

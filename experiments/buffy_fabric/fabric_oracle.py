"""
Independent Monte Carlo oracle for the leaf-spine incast model, written from the model's description (the
header of buffy/examples/jani/fabric.buffy and Buffy's step semantics), without the Buffy program or the
compiler.

One step:
- arrivals: at the start of a round (time % PERIOD == 0) every host's response socket is topped up to SLEN
  packets and every responder draws its start delay uniformly from 0..WIN; the victim's NIC (host H) gets a
  victim packet with probability LV, then every NIC a background packet with probability LB (tail drop at
  NCAP);
- at a round's start the per-round loss counters (incast, victim) are reset;
- every leaf port to a host sends one packet;
- where several inputs send into one output queue in the same step, they are admitted in a random rotation of their
  order, drawn every step: the spines at a leaf's host ports, the leaves at a spine's ports, a leaf's hosts at its
  uplinks;
- every spine port sends its head packet to leaf j: incast packets to host 0, victim packets to host 1, a
  background packet to a uniformly random host of leaf j (tail drop at B);
- every leaf uplink sends its head packet to its spine, into the port for leaf 0 (incast and victim) or for
  a uniformly random other leaf (background);
- every NIC sends its head packet to an uplink of its leaf: a uniformly random spine (ECMP = 0) or the spine
  its host drew at time 0 (ECMP = 1);
- every responder (hosts of leaves 1.., except host H) whose delay has run out hands its NIC one response
  packet if the NIC has room; delays count down.
A packet thus crosses at most one link per step. Classes: 0 incast, 1 victim, 2 background.

Usage: python fabric_oracle.py runs seed [NAME=value ...]   (constants as in fabric.buffy)
Prints P[loss], P[victim] and the means of the cumulative counters at time T.
"""
import random
import sys
from collections import deque

DEFAULTS = dict(NL=3, H=2, NS=2, B=4, NCAP=4, SLEN=3, WIN=4, PERIOD=1000, LV=0.3, LB=0.05, ECMP=0, T=30,
                THRESH=2, VTH=1)


def run(c, rng):
    NL, H, NS, B, NCAP, SLEN, WIN, PERIOD = (c[k] for k in ("NL", "H", "NS", "B", "NCAP", "SLEN", "WIN", "PERIOD"))
    LV, LB, ECMP, T, THRESH, VTH = (c[k] for k in ("LV", "LB", "ECMP", "T", "THRESH", "VTH"))
    N = NL * H
    rsp = [0] * N                                  # response packets still to hand to the NIC
    delay = [0] * N
    nic = [deque() for _ in range(N)]
    up = [[deque() for _ in range(NS)] for _ in range(NL)]       # up[l][s]: leaf l's port to spine s
    sd = [[deque() for _ in range(NL)] for _ in range(NS)]       # sd[s][j]: spine s's port to leaf j
    eg = [deque() for _ in range(N)]                              # leaf port to host k
    flow_spine = [0] * N
    cnt = dict(oLost=0, oGot=0, vLost=0, vGot=0, bLost=0, oBad=0, vBad=0)
    odrops = vdrops = 0
    loss = victim = False

    def lost(cls):
        nonlocal odrops, vdrops
        if cls == 0:
            if odrops == THRESH - 1:
                cnt["oBad"] += 1
            odrops = min(THRESH, odrops + 1)
            cnt["oLost"] += 1
        elif cls == 1:
            if vdrops == VTH - 1:
                cnt["vBad"] += 1
            vdrops = min(VTH, vdrops + 1)
            cnt["vLost"] += 1
        else:
            cnt["bLost"] += 1

    def push(q, pkt):
        if len(q) == B:
            lost(pkt)
        else:
            q.append(pkt)

    for t in range(T):
        # properties at the boundary before step t (the initial state has no losses)
        round_start = t % PERIOD == 0
        draws = [rng.randint(0, WIN) for _ in range(N)] if round_start else None
        if round_start:
            rsp = [SLEN] * N
        for k in range(N):
            if k == H and rng.random() < LV and len(nic[k]) < NCAP:
                nic[k].append(1)
            if rng.random() < LB and len(nic[k]) < NCAP:
                nic[k].append(2)
        if round_start:
            odrops = vdrops = 0
        for k in range(N):
            if eg[k]:
                p = eg[k].popleft()
                if k == 0 and p == 0:
                    cnt["oGot"] += 1
                if k == 1 and p == 1:
                    cnt["vGot"] += 1
        # several inputs of one output queue in a step: admitted in a random rotation of their order
        r1 = rng.randrange(NS)
        for i in range(NS):
            s = (i + r1) % NS
            for j in range(NL):
                if sd[s][j]:
                    p = sd[s][j].popleft()
                    push(eg[p] if p < 2 else eg[j * H + rng.randrange(H)], p)
        r2 = rng.randrange(NL)
        for i in range(NL):
            l = (i + r2) % NL
            for s in range(NS):
                if up[l][s]:
                    p = up[l][s].popleft()
                    push(sd[s][0] if p < 2 else sd[s][(l + rng.randint(1, NL - 1)) % NL], p)
        r3 = rng.randrange(H)
        for l in range(NL):
            for i in range(H):
                k = l * H + (i + r3) % H
                spine = rng.randrange(NS)
                if t == 0:
                    flow_spine[k] = spine
                if ECMP == 1:
                    spine = flow_spine[k]
                if nic[k]:
                    push(up[l][spine], nic[k].popleft())
        for k in range(H + 1, N):
            d = draws[k] if round_start else delay[k]
            if d == 0 and len(nic[k]) < NCAP and rsp[k] > 0:
                rsp[k] -= 1
                nic[k].append(0)
            delay[k] = max(d - 1, 0)
        loss |= odrops >= THRESH
        victim |= vdrops >= VTH
    return loss, victim, cnt


def main():
    runs, seed = int(sys.argv[1]), int(sys.argv[2])
    c = dict(DEFAULTS)
    for kv in sys.argv[3:]:
        k, v = kv.split("=")
        c[k] = float(v) if "." in v else int(v)
    rng = random.Random(seed)
    nl = nv = 0
    tot = dict(oLost=0, oGot=0, vLost=0, vGot=0, bLost=0, oBad=0, vBad=0)
    sq = dict(tot)
    for _ in range(runs):
        a, b, cnt = run(c, rng)
        nl += a
        nv += b
        for k in tot:
            tot[k] += cnt[k]
            sq[k] += cnt[k] ** 2
    out = {"loss": nl / runs, "victim": nv / runs}
    for k in tot:
        m = tot[k] / runs
        out[k] = m
        out[k + "_sd"] = max(sq[k] / runs - m * m, 0) ** 0.5
    print(out)


if __name__ == "__main__":
    main()

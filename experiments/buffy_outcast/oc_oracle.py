"""
Independent Monte Carlo oracle for the TCP outcast case study, written from the model's description
(the header of buffy/examples/jani/outcast.buffy), not from the Buffy program or the compiler.

One time step: the output port sends the head of its FIFO; every flow not in a timeout sends a packet
with probability min(w, R) / R; port A's flows join the upstream FIFO in a uniformly random rotation of
their order (tail drop); port A forwards the upstream head; the two ports' packets enter the output
FIFO in the arbitration order (tail drop); then every flow's TCP state is updated (acknowledgement of
the sent packet, recovery period, timeout).

Usage: python oc_oracle.py runs [NA BUF UPCAP R WMAX W0 RTO ARB T W seed]
"""
import random
import sys
from collections import deque


def run(NA, BUF, UPCAP, R, WMAX, W0, RTO, ARB, STICK, T, W, rng):
    NF = NA + 1
    oq, up = deque(), deque()
    w, acks, rec, dup, rto = [W0] * NF, [0] * NF, [0] * NF, [0] * NF, [0] * NF
    got, to = [0] * NF, [0] * NF
    a_first = 1
    for t in range(T):
        dl = oq.popleft() if oq else -1
        snd = [rto[i] == 0 and rng.random() < min(w[i], R) / R for i in range(NF)]
        lost_up = [False] * NF
        off = rng.randrange(NA)
        for j in range(NA):
            k = (j + off) % NA
            if snd[k]:
                if len(up) == UPCAP:
                    lost_up[k] = True
                else:
                    up.append(k)
        fb = NA if snd[NA] else -1
        fa = up.popleft() if up else -1
        if ARB == 0:
            a_goes = True
        elif ARB == 1:
            a_goes = False
        elif ARB == 2:
            a_goes = rng.random() < 0.5
        else:
            a_goes = rng.random() < (STICK if a_first else 1 - STICK)
        if fa != -1 and fb != -1:
            a_first = 1 if a_goes else 0
        lost2 = -1
        for f in ((fa, fb) if a_goes else (fb, fa)):
            if f != -1:
                if len(oq) == BUF:
                    lost2 = f
                else:
                    oq.append(f)
        for i in range(NF):
            if dl == i and T - W <= t < T:
                got[i] += 1
            if rto[i] > 0:
                rto[i] -= 1
                if rto[i] == 0:
                    w[i], acks[i] = 1, 0
            elif rec[i] > 0:
                if dl == i:
                    dup[i] = min(3, dup[i] + 1)
                rec[i] -= 1
                if rec[i] == 0:
                    if dup[i] >= 3:
                        w[i], acks[i] = max(1, w[i] // 2), 0
                    else:
                        rto[i] = RTO
                        to[i] += 1
            elif lost_up[i] or lost2 == i:
                rec[i], dup[i] = R, 0
            elif dl == i:
                if acks[i] + 1 >= w[i]:
                    w[i], acks[i] = min(WMAX, w[i] + 1), 0
                else:
                    acks[i] += 1
    return got, to


def main():
    a = sys.argv[1:]
    runs = int(a[0])
    dflt = [4, 8, 8, 8, 8, 2, 24, 2, 160, 80, 7]
    NA, BUF, UPCAP, R, WMAX, W0, RTO, ARB, T, W, seed = [int(x) for x in a[1:12]] + dflt[len(a[1:12]):]
    rng = random.Random(seed)
    NF = NA + 1
    sb = sa = gb = ga = tb = 0
    for _ in range(runs):
        got, to = run(NA, BUF, UPCAP, R, WMAX, W0, RTO, ARB, 0.9, T, W, rng)
        sb += 2 * NF * got[NA] <= W
        sa += sum(2 * NF * got[i] <= W for i in range(NA)) / NA
        gb += got[NA]
        ga += sum(got[:NA]) / NA
        tb += to[NA] >= 1
    p = sb / runs
    print(f"oracle NA={NA} BUF={BUF} ARB={ARB}: P[starveB]={p:.4f}±{1.96 * (p * (1 - p) / runs) ** 0.5:.4f} "
          f"P[starveA]={sa / runs:.4f}  P[toB]={tb / runs:.4f}  E[gotB]={gb / runs:.2f}  E[gotA]={ga / runs:.2f}")


if __name__ == "__main__":
    main()

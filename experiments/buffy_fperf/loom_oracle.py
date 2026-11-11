"""
Independent Monte Carlo oracle for the Loom tenant-isolation case study, written from FPerf's module
code (fperf/src/qms/loom_flow_enq_qm.cpp, rr_qm.cpp, loom_nic_enq_qm.cpp, priority_qm.cpp,
loom_demux_qm.cpp; wiring fperf/src/cps/loom_mqprio.cpp) and the policies described in
buffy/examples/jani/loom_isolation.buffy, without using the Buffy program or the compiler.

One step: arrivals (Bernoulli per flow, tail drop), then the whole pipeline in the same step (FPerf's
IMM_QUEUEs): per core flow enqueue (tenant 1 passes up to ENQ packets; tenant 2's Spark and memcached
interleaved, up to ENQ), round robin over the two tenants (one packet), the NIC stage, one packet out.
Classes: 1 tenant-1 Spark, 2 tenant-2 Spark, 3 memcached.

Usage: python loom_oracle.py RHO1 RHO2 RHOM POLICY [runs] [NC T W SHARE CAP ENQ seed]
"""
import random
import sys
from collections import deque


def run(rho1, rho2, rhom, policy, nc, T, W, share, cap, enq, rng):
    flow = [[deque() for _ in range(3)] for _ in range(nc)]   # per core: t1 Spark, t2 Spark, memcached
    ten = [[deque(), deque()] for _ in range(nc)]             # per core: tenant 1, tenant 2
    last = [1] * nc                                            # RRQM: the last queue starts served
    nic = [deque() for _ in range(nc)]
    prio = [deque(), deque(), deque()]
    last_t = 2
    w1 = w2 = 0
    waiting = True

    def put(q, pkt):
        if len(q) < cap:
            q.append(pkt)

    for t in range(T):
        for i in range(nc):
            for k, (p, cls) in enumerate(((rho1 / nc, 1), (rho2 / nc, 2), (rhom / nc, 3))):
                if rng.random() < p:
                    put(flow[i][k], cls)
        q1 = sum(len(flow[i][0]) + sum(1 for c in ten[i][0]) + sum(1 for c in nic[i] if c == 1) for i in range(nc))
        q1 += sum(1 for q in prio for c in q if c == 1)
        if T - W <= t < T and q1 == 0:
            waiting = False
        for i in range(nc):
            # LoomFlowEnqQM: tenant 1 passes its first ENQ packets; tenant 2 takes the first ENQ valid
            # packets of the interleaving F1[0], F2[0], F1[1], F2[1], ...
            for _ in range(min(enq, len(flow[i][0]))):
                put(ten[i][0], flow[i][0].popleft())
            b1, b2 = len(flow[i][1]), len(flow[i][2])
            taken = 0
            for j in range(2 * enq):
                q, off = 1 + j % 2, j // 2
                if taken < enq and off < (b1 if q == 1 else b2):
                    put(ten[i][1], flow[i][q].popleft())
                    taken += 1
            # RRQM over the two tenant queues, one packet.
            for k in (1 - last[i], last[i]):
                if ten[i][k]:
                    nic[i].append(ten[i][k].popleft())
                    last[i] = k
                    break
        out = None
        if policy == 0:
            # LoomNICEnqQM (share 1: the head of each NIC queue) then PriorityQM: memcached first.
            for i in range(nc):
                if nic[i]:
                    c = nic[i].popleft()
                    put(prio[0] if c == 3 else prio[1], c)
            for q in (prio[0], prio[1]):
                if q:
                    out = q.popleft()
                    break
        else:
            for i in range(nc):
                if nic[i]:
                    c = nic[i].popleft()
                    put(prio[0] if c == 1 else prio[1] if c == 3 else prio[2], c)
            t1, t2 = bool(prio[0]), bool(prio[1] or prio[2])
            if t1 and (not t2 or last_t == 2):
                out, last_t = prio[0].popleft(), 1
            elif t2:
                out, last_t = (prio[1] if prio[1] else prio[2]).popleft(), 2
        if out is not None and T - W <= t < T:
            if out == 1:
                w1 += 1
            else:
                w2 += 1
    return waiting and 100 * w1 <= share * W, waiting, w1, w2


def main():
    a = sys.argv[1:]
    rho1, rho2, rhom, policy = float(a[0]), float(a[1]), float(a[2]), int(a[3])
    runs = int(a[4]) if len(a) > 4 else 20000
    nc, T, W, share, cap, enq, seed = (int(x) for x in (a[5:12] + ["4", "60", "20", "40", "10", "4", "7"][len(a[5:12]):]))
    rng = random.Random(seed)
    starved = waits = s1 = s2 = 0
    for _ in range(runs):
        st, wt, w1, w2 = run(rho1, rho2, rhom, policy, nc, T, W, share, cap, enq, rng)
        starved += st
        waits += wt
        s1 += w1
        s2 += w2
    p = starved / runs
    half = 1.96 * (max(p * (1 - p), 1e-12) / runs) ** 0.5
    print(f"oracle POLICY={policy} rho=({rho1},{rho2},{rhom}): starved={p:.4f}±{half:.4f}  waiting={waits / runs:.4f}  "
          f"e_w1={s1 / runs:.3f}  e_w2={s2 / runs:.3f}", flush=True)


if __name__ == "__main__":
    main()

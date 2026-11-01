"""Direct Monte Carlo of the Buffy paper's Fig. 2 scheduler, independent of every compiler/model.

N=5, SZ=8, T=14; queues 0..3 get uniform 0..4 arrivals, the last queue P0 of none and (1-P0)/4 of
1..4. Estimates P(deqs_bl reaches 4 within T steps). Usage: python fig2_mc.py RUNS [P0]
"""
import random, sys
N, SZ, K, T = 5, 8, 4, 14
P0 = float(sys.argv[2]) if len(sys.argv) > 2 else 0.2
def arrivals(rng, i):
    if i < N - 1:
        return rng.randint(0, K)
    return 0 if rng.random() < P0 else rng.randint(1, K)
def run(rng):
    b = [0] * N; nq = []; oq = []; bl = 0
    for t in range(T):
        for i in range(N): b[i] = min(SZ, b[i] + arrivals(rng, i))
        for i in range(N):
            if b[i] > 0 and i not in oq and i not in nq: nq.append(i)
        for _ in range(N):
            head = nq.pop(0) if nq else (oq.pop(0) if oq else -1)
            if head == -1: continue
            if b[head] > 1: oq.append(head)
            if b[head] > 0:
                if head == N - 1 and all(b[j] > 0 for j in range(N - 1)): bl += 1
                b[head] -= 1
                break
        if bl >= 4: return 1
    return 0
rng = random.Random(1); n = int(sys.argv[1])
v = sum(run(rng) for _ in range(n)) / n
print(f"P0={P0}: P(deqs_bl reaches 4 within {T} steps) = {v:.6f}  (n={n}, 99% half-width ~ {2.576*(v*(1-v)/n)**0.5:.6f})")

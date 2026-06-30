"""
Monte-Carlo oracle for the ToR incast model (mirrors incast.pm exactly).

Topology:
  - 1 OUTPUT port -> receiver (drains 1 packet/slot).
  - D SERVER input ports: 1 in-rack sender each.
  - U UPLINK input ports: `m` out-of-rack flows each.
  Every input port forwards <=1 packet/slot into the output buffer.
  EVERY buffer (inputs and output) has the same capacity B.

Each sender picks a start slot uniformly in [0..W] and sends S packets
back-to-back (1/slot).

Per slot (store-and-forward, output-queued; matches incast.pm):
  1. output drains 1 to the receiver
  2. every backlogged input port forwards 1 into the output buffer;
     overflow at the output = OUTPUT drops (receiver-facing incast loss)
  3. arrivals enter the input buffers; overflow there = INPUT drops
The run continues until all packets have drained (output drains 1/slot), so
loss that happens during the post-arrival drain is counted (this matters!).

incast.pm uses D=2 servers, U=4 uplink ports of which FANOUT are active,
m=2 flows per uplink:  simulate(2, FANOUT, 2, S, W, B).
"""
import numpy as np


def simulate(D, U, m, S, W, B, nsamples=100_000, seed=0):
    rng = np.random.default_rng(seed)
    P = D + U
    N = D + U * m
    HORIZON = W + S + N * S                 # run to full drain
    per_port = [1] * D + [m] * U
    starts = [rng.integers(0, W + 1, size=(nsamples, k)) for k in per_port]

    inq = np.zeros((nsamples, P), dtype=np.int32)
    outq = np.zeros(nsamples, dtype=np.int32)
    out_drop = np.zeros(nsamples, dtype=np.int32)
    in_drop = np.zeros(nsamples, dtype=np.int32)
    max_fwd = np.zeros(nsamples, dtype=np.int32)

    for tau in range(HORIZON):
        outq = np.maximum(outq - 1, 0)                       # 1. drain to receiver
        fwd = (inq > 0).astype(np.int32)                     # 2. inputs -> output
        inq -= fwd
        F = fwd.sum(axis=1)
        max_fwd = np.maximum(max_fwd, F)
        room = B - outq
        admitted = np.minimum(F, room)
        out_drop += F - admitted
        outq += admitted
        a = np.empty((nsamples, P), dtype=np.int32)          # 3. arrivals
        for k in range(P):
            s = starts[k]
            a[:, k] = ((s <= tau) & (tau < s + S)).sum(axis=1)
        room_k = B - inq
        adm_k = np.minimum(a, room_k)
        in_drop += (a - adm_k).sum(axis=1)
        inq += adm_k

    return {"out_drop": out_drop, "in_drop": in_drop,
            "total": out_drop + in_drop, "max_fwd": max_fwd}


def Pout(D, U, m, S, W, B, p, n=120_000, seed=1):
    return float(np.mean(simulate(D, U, m, S, W, B, n, seed)["out_drop"] >= p))


def Pin(D, U, m, S, W, B, p, n=120_000, seed=1):
    return float(np.mean(simulate(D, U, m, S, W, B, n, seed)["in_drop"] >= p))


if __name__ == "__main__":
    S, B, p = 3, 5, 3
    Ws = [2, 4, 8, 12, 16, 22, 30]
    print(f"# incast.pm regime: 2 servers + FANOUT uplinks (2 flows each), "
          f"S={S} B={B} THRESH={p}")
    print("# P[receiver loss] over the (fan-out, window) plane:")
    print("        " + "  ".join(f"W={w:<2}" for w in Ws))
    for G in range(0, 5):
        row = [Pout(2, G, 2, S, w, B, p) for w in Ws]
        print(f"FANOUT={G} " + "  ".join(f"{x:4.2f}" for x in row))
    print("\n# every input port stays healthy in this regime (max P[input loss]):")
    for G in range(0, 5):
        mx = max(Pin(2, G, 2, S, w, B, p) for w in Ws)
        print(f"FANOUT={G}: max P[input loss] = {mx:.3f}")

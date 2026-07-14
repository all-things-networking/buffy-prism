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

incast.pm uses all-uplink ports, MPP=2 flows per uplink, and a single
input-traffic knob M = total senders (so the number of active uplinks is M/2):
    simulate(0, M//2, 2, SLEN, WIN, BUF).
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


def pq(M, WIN, SLEN, BUF, THRESH, n=120_000, seed=0):
    """P[Q] for the incast.pm regime: all uplinks, MPP=2 flows each, M senders."""
    return Pout(0, M // 2, 2, SLEN, WIN, BUF, THRESH, n, seed)


def certify_box(name, Mr, Wr, Sr, BUF, THRESH):
    """P[Q] is monotone (up in M & SLEN, down in WIN), so the box minimum is at
    (M_lo, WIN_hi, SLEN_lo) and the maximum at (M_hi, WIN_lo, SLEN_hi)."""
    mn = pq(Mr[0], Wr[1], Sr[0], BUF, THRESH)
    mx = pq(Mr[1], Wr[0], Sr[1], BUF, THRESH)
    print(f"\n{name}   (BUF={BUF}, THRESH={THRESH})")
    print(f"  A = (M in [{Mr[0]},{Mr[1]}]) & (WIN in [{Wr[0]},{Wr[1]}]) "
          f"& (SLEN in [{Sr[0]},{Sr[1]}])")
    print(f"  least-favorable corner (M={Mr[0]},WIN={Wr[1]},SLEN={Sr[0]}): "
          f"P[Q] = {mn:.3f}   (WIN/SLEN = {Wr[1]/Sr[0]:.0f}x)  <- holds for ALL of A")
    print(f"  most-severe     corner (M={Mr[1]},WIN={Wr[0]},SLEN={Sr[1]}): "
          f"P[Q] = {mx:.3f}")


def grid(name, Ms, Ws, Ss, BUF, THRESH):
    print(f"\n{name}  P[Q]  (BUF={BUF}, THRESH={THRESH})")
    for S in Ss:
        print(f"  SLEN={S}   " + "".join(f"W={w:<4}" for w in Ws))
        for M in Ms:
            print(f"    M={M:<3} " + " ".join(f"{pq(M,w,S,BUF,THRESH):5.3f}" for w in Ws))


if __name__ == "__main__":
    BUF, THRESH = 32, 8
    # Three boxes for the "probabilistic vs 100%-only" argument (see NOTES.md).
    # All are in the example-2 regime (short flows), BUF=32, THRESH=8.

    print("=== Box P1 (probabilistic, 1-D: the sync window) ===")
    grid("A_P1 = M=16, SLEN=8, WIN in [96,120]",
         [16], [96, 104, 112, 120], [8], BUF, THRESH)

    print("\n=== Box P2 (probabilistic, 2-D: burst length AND sync window) ===")
    grid("A_P2 = M=16, SLEN in [8,9], WIN in [116,124]",
         [16], [116, 120, 124], [8, 9], BUF, THRESH)

    print("\n=== Box P3 (3 SLEN values, same M=16 fan-in) ===")
    grid("A_P3 = M=16, SLEN in [10,12], WIN in [184,192]",
         [16], [184, 192], [10, 11, 12], BUF, THRESH)

    print("\n=== Box P4 (4 SLEN values, M=12) ===")
    grid("A_P4 = M=12, SLEN in [13,16], WIN in [196,204]",
         [12], [196, 204], [13, 14, 15, 16], BUF, THRESH)

    print("\n=== Box E (extreme / obvious: many uplinks, nearly synchronised) ===")
    certify_box("A_E = (20<=M<=24) & (0<=WIN<=24) & (8<=SLEN<=12)",
                (20, 24), (0, 24), (8, 12), BUF, THRESH)

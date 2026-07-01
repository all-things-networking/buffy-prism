# ToR incast case study — example 2 (short bursts, de-synchronised senders)

Same contention point and framing as `example1_moderate_fanout/`, but a
**less obvious** assumption. Example 1 used long bursts (`SLEN ∈ [16,24]`)
relative to a window `WIN ≤ 48`, so `WIN/SLEN ≤ 3`: a burst spans a third of the
window and collisions are almost forced. Here the bursts are **short** and the
senders are **genuinely de-synchronised** (`WIN` up to 12× the burst length), yet
the receiver still overflows.

## Why these parameters (credible sizes)
`SLEN` is the flow/response length in packets (≈ 1.5 KB MTU):

| workload | flow size | ≈ packets |
|---|---|---|
| partition-aggregate query responses (DCTCP: web search / RPC / memcached) | 1.6–2 KB | 1–2 |
| general query traffic (DCTCP) | 2–20 KB | 1–14 |
| storage / Hadoop SRU (Phanishayee FAST'08: "apps ask in small chunks, 1–256 KB") | 10–32 KB | ~7–22 |

So incast-causing flows are typically **short** (a few to ~20 packets); the
classic partition-aggregate case is just a couple of packets. Fan-in is
realistically large (tens of responders; 44 servers/rack, "cast of thousands").
Example 2 therefore uses `SLEN ∈ [8,12]` (≈ 12–18 KB), a fan-in of `M ∈ [16,20]`
senders (8–10 uplinks × 2 flows), and `BUF = 32` packets/port.

Sources:
- Phanishayee et al., *Measurement and Analysis of TCP Throughput Collapse in
  Cluster-based Storage Systems*, FAST 2008
  (https://www.cs.cmu.edu/~dga/papers/incast-fast2008/).
- Alizadeh et al., *Data Center TCP (DCTCP)*, SIGCOMM 2010
  (https://www.microsoft.com/en-us/research/wp-content/uploads/2010/01/dctcp-public.pdf).

## Model
`incast.pm` here is the all-uplink model with `MMAX = 20` sender slots (10 uplink
ports), auto-generated with the same dynamics as example 1. `M` (even), `WIN`,
`SLEN` are the swept input-traffic parameters; `BUF`, `THRESH` are fixed.

## Bad event
`Q` = "at least `THRESH` packets dropped at the output buffer" (`odrops>=THRESH`),
with `THRESH = 8`.

## The assumption, as a formula
```
A  ≡  (16 ≤ M ≤ 20)  ∧  (48 ≤ WIN ≤ 96)  ∧  (8 ≤ SLEN ≤ 12)        [BUF=32, THRESH=8]
```
`P[Q]` is monotone (up in `M` and `SLEN`, down in `WIN`), so the box minimum is
its corner `(M=16, WIN=96, SLEN=8)`:

| corner of `A` | point | `WIN/SLEN` | `P[Q]` |
|---|---|---|---|
| least favorable | `M=16, WIN=96, SLEN=8` | **12×** | **0.54** |
| most severe | `M=20, WIN=48, SLEN=12` | 4× | 1.00 |

So **for every `(M, WIN, SLEN) ∈ A`, `P[Q] ≥ 0.54`**, and `P[input-buffer loss]
= 0` throughout. (Trim the window slightly — `WIN ≤ 80`, still 10× the burst —
and the whole box is `≥ 0.98`.)

## Why this is less obvious than example 1
- **The senders are genuinely de-synchronised.** At the least-favorable corner
  they start uniformly over a window **twelve times** the length of a flow. At
  any instant only a small fraction of the ten uplinks are transmitting, and a
  *direct* collision of two given flows is rare. You would expect the shallow
  receiver buffer to absorb such spread-out, short bursts.
- **It overflows anyway**, because incast is about *aggregate coincidence*, not
  pairwise synchronisation: with enough independent short flows converging on a
  1-packet/slot output, at some moment enough uplinks are simultaneously
  backlogged to overrun the buffer. Synchronisation is **not required** — only a
  large enough fan-in.
- **Nothing shows up per-port.** Every uplink carries just two short flows; its
  own buffer never overflows (`P[input loss] = 0`). The contention is purely the
  fan-in into the shared output, invisible to any single-port check.

This is the strongest form of the paper's point: the mild, range-valued
assumption that makes incast likely does **not** invoke tight synchronisation, a
tiny buffer, or extreme burst lengths — only a realistic fan-in of short,
well-spread flows — and only `P[Q | A]` over the parameter box reveals it.

## Running it
```
# evaluate the whole box A:
prism incast.pm incast.props -prop 1 \
      -const BUF=32,THRESH=8,M=16:2:20,WIN=48:8:96,SLEN=8:2:12 \
      -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 8000

# certify A by its least-favorable corner alone:
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=16,WIN=96,SLEN=8 \
      -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 8000

# oracle (no PRISM needed): prints the box certification
python3 incast_sim.py
```
PRISM (simulation) matches the oracle at every checked corner (e.g. the
least-favorable corner: PRISM 0.538 vs oracle 0.539). Exact model checking is
intractable at this scale, as in the FQ-CoDel study.

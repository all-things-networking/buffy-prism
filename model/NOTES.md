# ToR incast case study — notes

A motivating use case for **conditional probabilistic reasoning about a
contention point**: given a *bad event* `Q` and an *assumption* `A` over the
parameters that describe the input traffic, the tool reports **how probable `Q`
is under `A`** — `P[Q | A]`. The point is to find an assumption that is *mild /
non-obvious* yet still makes `Q` likely, where **`A` is a range (a box) that
applies to every parameter combination inside it**, not a single point.

## Files
- `incast.pm` — the PRISM DTMC (the model to read / walk through).
- `incast.props` — the queries.
- `incast_sim.py` — a Monte-Carlo oracle with the *exact* same dynamics; used
  to explore and to cross-check PRISM (they agree).

## Scenario → contention model
We are the **top-of-rack (ToR) switch** in front of the receiver where incast
happens. One **output port** drains 1 packet/slot to the receiver. Every other
port is an **uplink** carrying `MPP = 2` out-of-rack flows (traffic via
higher-layer switches), one buffer per port, **every buffer the same capacity
`BUF`**, and every input port forwards at most 1 packet/slot into the output.

The single **input-traffic knob is `M` = total number of senders**; with two
flows per uplink the number of active uplinks (the fan-out) is `M/2`. Each
sender picks a start slot uniformly in `[0..WIN]` and sends `SLEN` packets
back-to-back.

The **input-traffic parameters** are therefore `M`, `WIN`, `SLEN`. `BUF` (a
switch property) and `THRESH` (the severity that defines `Q`) are held fixed at
representative values:

- `BUF = 32` packets per port (a shallow but data-center-plausible buffer,
  ~48 KB at 1.5 KB/packet),
- `THRESH = 8` (a "significant" receiver-loss burst, a quarter of a buffer).

## Bad event
`Q` = "at least `THRESH` packets dropped at the output buffer" — receiver-facing
incast loss (`odrops >= THRESH`).

## The assumption, as a formula
We look for a **box** `A` such that `P[Q] ` is non-negligible for **every**
point in it. Because the dynamics are **monotone** — `P[Q]` increases with `M`
and `SLEN`, decreases with `WIN` — the box's worst case is its corner
`(M_lo, WIN_hi, SLEN_lo)`. If `Q` is likely there, it is likely throughout `A`.

The robust assumption:

```
A  ≡  (6 ≤ M ≤ 12)  ∧  (0 ≤ WIN ≤ 48)  ∧  (16 ≤ SLEN ≤ 24)        [BUF=32, THRESH=8]
```

| corner of `A` | point | `P[Q]` |
|---|---|---|
| least favorable (fewest senders, widest window, shortest burst) | `M=6, WIN=48, SLEN=16` | **0.64** |
| most severe (most senders, tightest window, longest burst) | `M=12, WIN=0, SLEN=24` | 1.00 |

So **for every `(M, WIN, SLEN) ∈ A`, `P[Q] ≥ 0.64`** — and `P[input-buffer
loss] = 0` across the whole box. The receiver overflows while every uplink
buffer stays healthy.

For context, the surface `P[Q]` at `SLEN=24` (one face of the box; `M=2` is one
uplink, outside `A`):

```
            WIN=0  8     16    32    48    64
M=2 (U=1)   0.00  0.00  0.00  0.00  0.00  0.00     <- a single uplink can never overflow the output
M=4 (U=2)   1.00  1.00  0.90  0.60  0.33  0.17
M=6 (U=3)   1.00  1.00  1.00  1.00  1.00  1.00
M=8 (U=4)   1.00  1.00  1.00  1.00  1.00  1.00
```

## Why this is the right kind of assumption (and a trap to avoid)
- **It is a range, not a point.** `A` makes a claim about *every* combination of
  3–6 converging uplinks, any synchronization from perfect to spread-over-48,
  and 16–24-packet request bursts.
- **It is mild / non-obvious.** It does **not** assume tight synchronization
  (it spans `WIN` all the way to 48 — well desynchronized, which you would
  expect to be safe), nor a huge sender count, nor a tiny buffer. The only thing
  it pins down is a moderate fan-out (`M/2 ≥ 3`). Yet `Q` is likely throughout.
  And nothing is visible at any single port — every uplink buffer is empty-ish;
  the contention is purely the *fan-out* into the shared output.
- **It is robust, not corner-skewed.** This is the subtle part. Consider
  instead

  ```
  A' ≡ (2 ≤ M ≤ 12) ∧ (0 ≤ WIN ≤ 64) ∧ (SLEN = 24)
  ```
  `A'` looks dangerous on average, but its least-favorable corner
  (`M=2, WIN=64`) has `P[Q] = 0.00`: the "danger" is carried entirely by its
  synchronized / high-fan-out corner. Averaged over `A'` you would report a
  non-negligible number that **evaporates** once you exclude that corner — a
  misleading assumption. Certifying a box by its least-favorable corner (cheap,
  thanks to monotonicity) is exactly what rules this out, and is why `A` starts
  at `M=6`, not `M=2`.

**Takeaway for the paper.** The obvious knobs (tight synchronization, a tiny
buffer, a huge sender count) are not needed to make incast likely. The mild,
range-valued assumption that does — *a moderate fan-out of uplinks, regardless
of how the senders are spread in time* — is invisible per-port and only
`P[Q | A]` over the parameter box reveals it. A single counterexample cannot.

## Running it
```
# evaluate the whole box A (receiver loss):
prism incast.pm incast.props -prop 1 \
      -const BUF=32,THRESH=8,M=6:2:12,WIN=0:8:48,SLEN=16:4:24 \
      -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 5200

# certify A by its least-favorable corner alone:
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=6,WIN=48,SLEN=16 \
      -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 5200

# oracle (no PRISM needed): prints the box certification
python3 incast_sim.py
```
`M` is even (= 2 × number of active uplinks). Exact (numerical) model checking
is intractable here — the state space is far too large — so we use statistical
model checking (simulation), as in the FQ-CoDel study, cross-checked against the
oracle.

## Relation to the FQ-CoDel case study (common abstraction)
Same shape: a DTMC with a **probabilistic input** stage (each sender's start is
a uniform draw, realised by the per-slot hazard `1/(WIN+1-slot)`), feeding a
**deterministic contention point** (fabric + buffers), with monotone
**bad-event counters** (`odrops`, `idrops`) and **input-describing parameters**
(`M`, `WIN`, `SLEN`). The analysis primitive is the same: `P[Q | A]` for `A` a
range over those parameters.

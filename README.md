# buffy-prism — ToR incast case study

A small, self-contained case study for **conditional probabilistic reasoning
about a network contention point**. Given a *bad event* `Q` (packets dropped at
a buffer) and an *assumption* `A` over the parameters that describe the input
traffic, we use the [PRISM model checker](https://www.prismmodelchecker.org/)
to compute **how probable `Q` is under `A`** — `P[Q | A]` — and to search for a
*non-obvious* assumption (a range of parameters) that still carries non-trivial
probability.

The modelled contention point is a **top-of-rack switch during TCP incast**: an
output port to the receiver, fed by uplink ports that aggregate out-of-rack
flows, each with its own (representative, data-center-shallow) buffer. The
assumption `A` is a *box* over the input-traffic parameters — total senders `M`,
synchronization window `WIN`, burst length `SLEN` — and we certify that `Q` is
likely across the *whole* box, not just a skewing corner.

## Examples (`model/`)
Each example is a self-contained model + queries + oracle + notes for one
assumption box.

- **`example1_moderate_fanout/`** — a moderate fan-out of uplinks (`M/2 ≥ 3`)
  makes receiver loss likely for *any* synchronization window, while every
  input port's buffer stays healthy. Assumption box
  `A = (M in [6..12]) & (WIN in [0..48]) & (SLEN in [16..24])`, `BUF=32`,
  `THRESH=8`; `P[Q] ≥ 0.64` throughout.

## Quick start (example 1)
```
cd model/example1_moderate_fanout
# evaluate the whole assumption box A:
prism incast.pm incast.props -prop 1 \
     -const BUF=32,THRESH=8,M=6:2:12,WIN=0:8:48,SLEN=16:4:24 \
     -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 5200

# or, with no PRISM installed (prints the box certification):
python3 incast_sim.py
```
See each example's `NOTES.md` for results and discussion.

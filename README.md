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

## Contents (`model/`)
- `incast.pm` — the PRISM DTMC.
- `incast.props` — the queries (`P=? [ F (done & odrops>=THRESH) ]`, …).
- `incast_sim.py` — a Monte-Carlo oracle with the identical dynamics, for
  exploration and cross-checking PRISM.
- `NOTES.md` — the scenario, the dynamics, and the **non-obvious assumption**
  (a mild range — a moderate fan-out of uplinks, *any* synchronization — under
  which receiver loss is likely, while every input port's buffer stays healthy).

## Quick start
```
# evaluate the assumption box A = (M in [6..12]) & (WIN in [0..48]) & (SLEN in [16..24])
prism model/incast.pm model/incast.props -prop 1 \
     -const BUF=32,THRESH=8,M=6:2:12,WIN=0:8:48,SLEN=16:4:24 \
     -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 5200

# or, with no PRISM installed (prints the box certification):
python3 model/incast_sim.py
```
See `model/NOTES.md` for the results and discussion.

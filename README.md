# buffy-prism — ToR incast case study

A small, self-contained case study for **conditional probabilistic reasoning
about a network contention point**. Given a *bad event* `Q` (packets dropped at
a buffer) and an *assumption* `A` over the parameters that describe the input
traffic, we use the [PRISM model checker](https://www.prismmodelchecker.org/)
to compute **how probable `Q` is under `A`** — `P[Q | A]` — and to search for a
*non-obvious* assumption (a range of parameters) that still carries non-trivial
probability.

The modelled contention point is a **top-of-rack switch during TCP incast**: an
output port to the receiver, fed by in-rack server ports and uplink ports that
aggregate out-of-rack flows, each with a shallow buffer.

## Contents (`model/`)
- `incast.pm` — the PRISM DTMC.
- `incast.props` — the queries (`P=? [ F (done & odrops>=THRESH) ]`, …).
- `incast_sim.py` — a Monte-Carlo oracle with the identical dynamics, for
  exploration and cross-checking PRISM.
- `NOTES.md` — the scenario, the dynamics, and the **non-obvious finding**
  (receiver loss is driven by *port fan-out*, not by per-port or total load;
  every input port stays healthy while the receiver overflows).

## Quick start
```
# receiver-loss probability over the (fan-out, window) plane
prism model/incast.pm model/incast.props -prop 1 \
     -const SLEN=3,BUF=5,THRESH=3,FANOUT=0:1:4,WIN=2:2:30 \
     -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 900

# or, with no PRISM installed:
python3 model/incast_sim.py
```
See `model/NOTES.md` for the results and discussion.

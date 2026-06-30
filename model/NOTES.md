# ToR incast case study — notes

A motivating use case for **conditional probabilistic reasoning about a
contention point**: given a *bad event* `Q` and an *assumption* `A` over the
parameters that describe the input, the tool answers **how probable `Q` is
under `A`** — `P[Q | A]`. The value is in finding an assumption that is
*mild / non-obvious* yet still carries non-trivial probability, rather than an
"obvious" extreme one.

## Files
- `incast.pm` — the PRISM DTMC (the model to read / walk through).
- `incast.props` — the queries.
- `incast_sim.py` — a Monte-Carlo oracle implementing the *exact* same
  dynamics; used to explore and to cross-check PRISM (they agree).

## Scenario → contention model
We are the **top-of-rack (ToR) switch** in front of the receiver where incast
happens. One **output port** drains 1 packet/slot to the receiver. Several
**input ports**, one buffer each (all buffers share the same capacity `BUF`):

- `2` **server ports** — one in-rack sender each.
- `4` **uplink ports** — each aggregates `2` out-of-rack flows (traffic via
  higher-layer switches). The **fan-out `FANOUT`** = how many uplinks actually
  carry traffic (only uplinks `1..FANOUT` are active).

Every input port forwards at most 1 packet/slot into the output buffer. Each
sender picks a start slot uniformly in `[0..WIN]` (the synchronization window)
and then sends `SLEN` packets back-to-back. Drops happen at the **output**
buffer (receiver-facing incast loss, the bad event) and, in principle, at the
**input** buffers.

`WIN, SLEN, BUF, THRESH, FANOUT` are undefined constants, **swept over ranges**
(PRISM experiments). The assumption `A` we look for is a *range* of them.

Realistic-data-center ratios: the receiver link is the bottleneck (drains
1/slot), many *lightly loaded* sources converge on it, and buffers are shallow
— the standard ingredients of TCP incast.

## Bad event
`Q` = "at least `THRESH` packets dropped at the output buffer" (`odrops>=THRESH`).

## The non-obvious finding
Representative point `SLEN=3, BUF=5, THRESH=3`. `P[Q]` over the
(fan-out, window) plane (PRISM simulation == oracle, agree to ~CI width):

```
          WIN=2  WIN=4  WIN=8  WIN=12 WIN=16 WIN=22 WIN=30
FANOUT=0   0.00   0.00   0.00   0.00   0.00   0.00   0.00
FANOUT=1   0.00   0.00   0.00   0.00   0.00   0.00   0.00
FANOUT=2   1.00   1.00   0.90   0.39   0.17   0.06   0.02
FANOUT=3   1.00   1.00   1.00   1.00   0.82   0.40   0.16
FANOUT=4   1.00   1.00   1.00   1.00   1.00   0.92   0.51
```
…and across this whole plane **`P[input-buffer loss] = 0`**: every input port
stays perfectly healthy.

Read it as conditional probabilities `P[Q | A]`:

| assumption `A` (a *range*) | `P[Q | A]` | reading |
|---|---|---|
| `FANOUT <= 1` (any `WIN`, any `BUF`) | **0.00** | **safety certificate** — receiver never overflows |
| `WIN <= 4` (tight sync), `FANOUT>=2` | ~1.00 | the *obvious* danger — and it is real, but obvious |
| **`FANOUT >= 3`** (almost any `WIN`) | **high** | the danger is the **fan-out**, not the sync |
| `FANOUT = 2`, `WIN in [4,12]` | 0.39–1.0 | a genuine **threshold band**, not a point |

**Why it is non-obvious.** The naive intuition is "incast = many senders /
tight synchronization, so size the buffer for the load." But here:

1. **Every input port is lightly loaded and never overflows** (`P[input loss]=0`),
   so per-port inspection says everything is fine — yet the *receiver* drowns.
2. **What matters is the fan-out** — how many input ports are simultaneously
   backlogged — not the per-port load or the total load. Each port forwards
   only 1/slot, so the receiver (which also drains 1/slot) overflows precisely
   when `>=2` ports deliver at once for long enough. Concentrating the same
   flows behind *fewer* uplinks would *protect* the receiver (a backlogged
   uplink emits only 1/slot), pushing any loss onto that uplink's own buffer.
3. **De-synchronizing in time barely helps once fan-out is high.** You would
   expect a larger `WIN` to fix incast; it does at `FANOUT=2`, but at
   `FANOUT=4` even `WIN=22` still drops with prob 0.92. The safe `WIN` grows
   steeply with fan-out — the assumption that matters is a *region* in
   `(FANOUT, WIN)`, dominated by the axis (`FANOUT`) you would least suspect.

A single counterexample (one overflowing trace) cannot tell you any of this;
`P[Q | A]` over the parameter ranges does.

## A note on method (why the oracle and PRISM are both here)
An earlier version of the oracle stopped the simulation at `WIN+SLEN` instead
of running to full drain. That produced a dramatic but **spurious**
"moderate-sync-is-worst" reversal: it was dropping the post-arrival drain phase,
during which a backlogged uplink keeps feeding the output. Cross-checking the
PRISM model against the oracle exposed the discrepancy; with the drain included
both agree, and the reversal disappears. The contention point's behaviour is
exactly the kind of thing that is easy to get subtly wrong by eye and worth
pinning down with a model checker.

## Running it
```
# the (fan-out, window) surface, receiver loss:
prism incast.pm incast.props -prop 1 -const SLEN=3,BUF=5,THRESH=3,FANOUT=0:1:4,WIN=2:2:30 \
      -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 900

# single point, true/false check of an assumption:
prism incast.pm incast.props -prop 3 -const SLEN=3,BUF=5,THRESH=3,FANOUT=2,WIN=12 \
      -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 900

# oracle (no PRISM needed):
python3 incast_sim.py
```
`WIN >= 1` is required (the start-slot range is `[0..WIN]`). Exact
(numerical) model checking is intractable here — the state space is far too
large — so we use statistical model checking (simulation), exactly as in the
FQ-CoDel study, and cross-check against `incast_sim.py`.

## Relation to the FQ-CoDel case study (common abstraction)
Same shape: a DTMC with a **probabilistic input** stage (each sender's start is
a uniform draw, realised by the per-slot hazard `1/(WIN+1-slot)`), feeding a
**deterministic contention point** (the switch fabric + buffers), with monotone
**bad-event counters** (`odrops`, `idrops`) and **input-describing parameters**
(`FANOUT`, `WIN`, `SLEN`, `BUF`) used to phrase the assumption. The analysis
primitive is the same: `P[Q | A]` for `A` a range over those parameters.

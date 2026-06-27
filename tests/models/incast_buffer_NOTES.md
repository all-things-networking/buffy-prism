# Shared-buffer "incast" case study

A second motivating use case for probabilistic reasoning about contention
points, in the same style as the FQ-CoDel example
(`fqcodel_5i_dtmc_unif.pm` / `fqcodel_bl_5i_conditional_queries.props`).

The point of the use case: given a **bad event** `Q` and a **condition** `A`
over the *input* to a contended component, a probabilistic tool can report
`P[Q | A]` — *how likely the bad event is under that condition*. A single
counterexample only tells you `Q` is *possible*; `P[Q | A]` tells you whether
it is a *severe* or a *negligible* problem, and lets you search for a condition
that is **mild** (happens with non-trivial probability) yet **informative**
(strongly raises the probability of the bad event).

## Files
- `incast_buffer_dtmc.pm` — the PRISM DTMC.
- `incast_buffer_conditional_queries.props` — PLTL queries, grouped in 3s.
- `incast_buffer_solver.py` — a tiny exact oracle (independent of PRISM) that
  enumerates the input distribution and computes the same probabilities; used to
  pick parameters and to cross-check PRISM.

## Scenario → contention model
One shared **buffer** holds `BUF` packets and is drained at `SVC` packets/slot.
`N` **senders** each independently pick a start slot uniformly in `[0..WIN]`
(the synchronization window `W`) and then send `SLEN` packets back-to-back, one
per slot. The senders' start slots are the **input**.

Per slot `tau` the buffer serves first, then admits arrivals, dropping the
overflow:

```
arrivals   = # senders transmitting at tau          (offered load this slot)
departures = min(q, SVC)
room       = BUF - q + departures                   (free space after service)
admitted   = min(arrivals, room)
dropped    = arrivals - admitted
q'         = q - departures + admitted
```

The model runs in two phases: a **sampling** phase where each sender draws its
start slot (fixing the input), then a **running** phase that advances slot by
slot to `HORIZON = WIN + SLEN`, accumulating `drops` and tracking `peak`.

`peak` = peak concurrency = the largest number of senders ever transmitting in
the same slot. It is a function of the **input alone** and equals *the largest
number of senders that start within any `SLEN` consecutive slots* — i.e. the
burstiness of the arrival pattern, the textbook "incast" signal. Conditions `A`
are phrased over `peak` (and, in Group 5, directly over the start slots).

## Parameters (as committed)
`N=5, SLEN=3, WIN=8, BUF=4, SVC=2, THRESH=1` → `HORIZON=11`.

These were chosen so the buffer is **under-loaded on average** — mean offered
load is `N·SLEN/(WIN+SLEN) = 15/11 ≈ 1.36 < SVC = 2`, so a provisioning rule of
thumb would call the buffer adequately sized. Yet **synchronization** still
causes drops a third of the time. Note `BUF > SVC`: a single slot of high
concurrency does not immediately overflow, so `peak` is a *probabilistic*
predictor of drops (the burst must be *sustained*), not a logical restatement of
the bad event — which is exactly where a probabilistic tool earns its keep.

## Bad event
`Q` = "at least `THRESH` packets dropped" = `drops >= THRESH` (here `THRESH=1`,
i.e. *any* drop). Larger `THRESH` asks about *severe* loss.

## Results (PRISM exact = solver; cross-checked with simulation/CI)

Baseline `P[Q] = 0.330`.

| Group | Condition `A`            | `P[A]`  | `P[Q\|A]` | lift  | reading |
|------:|--------------------------|:-------:|:---------:|:-----:|---------|
| 1 | `peak >= 4`                  | 0.239   | **0.957** | 2.9×  | **mild & informative** — the useful, non-obvious condition |
| 2 | `peak >= 5` (all 5 synced)   | 0.026   | 1.000     | 3.0×  | obvious / extreme, but rare |
| 3 | `peak >= 3`                  | 0.820   | 0.402     | 1.2×  | mild but only weakly predictive |
| 4 | `peak <= 2`                  | 0.180   | **0.000** | 0×    | **safety certificate** — provably no drops |
| 5 | `spread <= 3` (starts bunched in a 3-slot window) | 0.083 | 1.000 | 3.0× | obvious / rare, phrased directly over the input |

`P[Q|A]` is computed as `Query2 / Query3` within each group (and compared to the
baseline `Query1`), exactly as in the FQ-CoDel queries.

## The story for the paper
- **A single counterexample is not enough.** The "obvious" sufficient condition —
  all `N` senders nearly synchronized (`peak >= 5`, or `spread <= 3`) — *does*
  force a drop, but it occurs only ~2.6% / ~8% of the time. A counterexample
  drawn from it is unrepresentative; it does not tell you whether drops are a
  real operational risk.
- **The mild condition is the payoff.** `peak >= 4` — *four of the five senders'
  transmissions overlapping within a 3-slot window* — is far from extreme: it
  happens ~24% of the time. Yet under it the drop probability jumps from 33% to
  **96%**. That is the kind of mild-but-strong condition that is actually
  actionable (e.g. it argues for jitter/pacing to keep concurrency ≤ 3).
- **Not every mild condition is informative.** `peak >= 3` is even more common
  (82%) but barely moves the needle (33% → 40%). The tool is what distinguishes
  the informative mild condition from the uninformative one.
- **Conditions can also certify safety.** `peak <= 2` drives `P[Q|A]` to 0: a
  quantitative "if concurrency stays ≤ 2, no packet is ever dropped."

## Running it

Exact (builds the full DTMC, ~0.7M states):
```
prism incast_buffer_dtmc.pm incast_buffer_conditional_queries.props
```

Simulation / statistical model checking (the FQ-CoDel workflow), per property:
```
prism incast_buffer_dtmc.pm incast_buffer_conditional_queries.props \
      -property 1 -sim -simmethod ci -simwidth 1e-4 -simconf 0.01 -simpathlen 40
```
The run reaches the absorbing `done` state within `N + HORIZON = 16` steps, so a
simulation path length of ~32–40 is plenty.

Exact oracle without PRISM:
```
python3 incast_buffer_solver.py
```

## Relation to a common abstraction
Both this and the FQ-CoDel model share the same shape: a DTMC with a
**probabilistic input** stage (uniform choices) feeding a **deterministic
contended component**, a monotone **bad-event counter** (`drops` here,
`iq5_deqs_bl` there), and **input-describing features** used to phrase
conditions (`peak`/`spread` here; `time`/`iq5_cenq`/`iq5_aipg` there). The
conditional query `P[Q | A] = P[Q ∧ A] / P[A]` is the common analysis primitive.

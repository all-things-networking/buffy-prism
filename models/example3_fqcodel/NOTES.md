# Example 3 — FQ-CoDel starvation: synthesising the worst-case traffic with LCRL

Where examples 1–2 (incast) study *how likely* a bad event is under an
*assumption box*, example 3 asks a different question that plays to LCRL's
strength: **given an MDP with a known bug, find the input that triggers it, and
read that input back as a causal explanation.**

## The model
`fqcodel.pm` is the buggy FQ-CoDel AQM (active queue management) scheduler:
5 input queues, 1 output, run for `TIME_STEPS = 14` service cycles. The
**nondeterministic choice in this MDP is the input traffic** (the per-cycle
packet arrivals / the FQ-CoDel record it produces). It is adapted from
`tests/models/fqcodel_5i_mdp.pm`:

- **`DEQ` commands guarded by `time<TIME_STEPS`, plus a terminal `[end]`
  self-loop and a `label "done" = (time=TIME_STEPS)`.** The original relies on
  the declared `time:[0..TIME_STEPS]` range to disable the `time'=time+1`
  dequeue at `time=14` (so it deadlocks = ends) — which works for *exact* model
  checking but **not for the StormPy simulator, which does not enforce variable
  ranges**, so `time` overflows past 14 and the run never terminates. The guard
  + `[end]` reproduce the intended end-of-run for the simulator/LCRL, absorbing
  (self-looping) at `done` rather than deadlocking. Nothing else changes.

## The bad event and the specification
`iq5_deqs_bl` counts how many times flow 5 is dequeued *while all other input
queues are backlogged* — its share of the output under contention. The
correctness expectation FQ-CoDel should meet is **fairness**: no flow hogs the
link, i.e. by end of run `iq5_deqs_bl <= 3`. The **bug** lets adversarial traffic
make FQ-CoDel **over-serve flow 5** — dequeue it more than 3 times while the
other queues are backlogged — so flow 5 hogs the output and **flows 1–4 starve**.
As an (unbounded) LTL property, the bad event is

```
Q  =  F (time=14 & iq5_deqs_bl > 3)          // flow 5 over-served -> flows 1-4 starved
```

`time=14` (= `TIME_STEPS`) marks end of run. It is written as a state predicate
rather than the `done` label because StormPy's program-level **simulator** does
not report this model's declared label (a relational atom is evaluated directly
from the state, and still works for exact model checking); the `done` label is
kept in the `.pm` for reference. `iq5_deqs_bl` is monotone, so `Q` equals
"`iq5_deqs_bl` eventually exceeds 4". The fairness spec is the complement
`F(time=14 & iq5_deqs_bl<=3)`; the bug is exactly its violation.
Verified: the derived LDBA reaches its accepting state **iff** the run ends with
`iq5_deqs_bl>3`.

## The study
**Train LCRL to MAXIMISE `P[Q]`.** Because the nondeterminism is the traffic,
the synthesised policy *is* the worst-case traffic pattern — an interpretable
explanation of how the starvation bug is provoked (which arrival sequence keeps
flow 5 from being served). Sample the learned policy, or determinise it, to read
off the offending schedule.

This is the **maximisation** direction, which is where LCRL is strong (reward at
the accepting state, `Q_init=0` pessimistic, no optimistic-init pathology — see
`experiments/incast_mdp_lcrl/METHODOLOGY.md`). It is the natural counterpart to
the incast `Pmax` (worst-case incast) study, and a contrast to the incast `Pmin`
(loss-*avoidance*) direction, which is hard for value-based RL.

## What is known so far
- The model is a well-formed MDP (max 5 nondeterministic actions) and terminates
  at end of run (200/200 random rollouts, ~216–233 simulator micro-steps ≈
  14×16).
- **The bad event is rare but reachable.** `iq5_deqs_bl` increments at most once
  per dequeue-cycle (≤ 14 total), so over-serving flow 5 requires *sustained*
  adversarial traffic that keeps flows 1–4 backlogged while flow 5 is repeatedly
  served. Under **random** traffic the final count is heavily 2–3 and **caps at 4**
  (`{1:5, 2:1078, 3:916, 4:1}` over 2200 rollouts) — `iq5_deqs_bl>3` occurs ~1 in
  2200, i.e. `Pmax[Q]` is small under random. This makes the worst-case a
  genuinely **non-obvious** traffic pattern LCRL must discover (unlike a saturated
  event) — the point of the study.
- **State abstraction matters.** A deterministic policy over `[time, stage,
  iq5_deqs_bl]` cannot engineer the queue backlog needed to over-serve flow 5 (it
  does *worse* than random). The projection must expose the scheduling state — e.g.
  whether all of flows 1–4 are backlogged, and flow 5's queue contents / FQ-CoDel
  ranks — so the policy can control when flow 5 is dequeued under contention.
- `Pmin[Q] = 1 - Pmax[fairness]` answers the dual, harder question — *can a
  scheduler always keep flow 5 fair?* — the loss-avoidance direction (see the
  incast `Pmin` discussion for why value-based RL struggles there).

## Files
```
fqcodel.pm      buggy FQ-CoDel MDP + done label + terminal self-loop
fqcodel.props   Q = F(time=14 & iq5_deqs_bl>3) [maximise], plus the fairness complement
NOTES.md        this file
```

## How to run
```
PYTHONPATH=. .venv/bin/python experiments/example3_fqcodel/run_fqcodel.py
```
It maximises Q (native +1-at-accepting reward + dense +Δiq5_deqs_bl) and prints
the over-service profile `P[iq5_deqs_bl>t]` for the learned greedy vs random.

## Status / how to continue
Current result: with the projection `[time, stage, iq5_deqs_bl]` — and even a
richer one adding `iqs_bl`, `iq5_contents`, `iq5_new_rank`, `iq5_old_rank` at
6000 episodes — LCRL does **not** yet synthesise the worst-case: it reaches
`P[>3]=0` and a mean *below* random (~2.0 vs ~2.5). Over-service is rare and needs
precise multi-step control the tabular greedy cannot capture. Next steps
(see `experiments/README.md` §5 for the general playbook):
1. **Find a witness first.** A directed/beam search over the simulator
   (`s._get_current_state()` + `s.restart(state)` to save/restore) confirms `>3`
   is reachable and yields a concrete offending traffic trace; use it to sanity-
   check the property and to warm-start RL.
2. **Expose the scheduling state the policy must control** — richer/less-lossy
   features around FQ-CoDel's new/old lists and ranks (what decides *who* is
   dequeued under contention), and the per-flow contents; iterate until the
   learned greedy beats the random baseline's mean.
3. If the tabular projection stays insufficient, move to **function
   approximation** (LCRL `train_nfq`) so the policy can generalise.

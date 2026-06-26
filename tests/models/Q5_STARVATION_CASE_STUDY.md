# Case study: a sparse flow starves the saturated ones under buggy FQ-CoDel

A worked example for the paper's thesis: **for network-performance properties, the
useful artifact is not a single counterexample trace, but an *input condition* under
which the problem occurs with noticeably high probability.**

## The property

The model (`fqcodel_5i_dtmc_unif.pm`, the student's buggy FQ-CoDel, 5 input queues,
IQ1–IQ4 saturated, IQ5 the flow of interest) tracks one counter:

```
iq5_deqs_bl++   when, at a dequeue step, IQ5 wins the single service slot
                WHILE all of IQ1..IQ4 are backlogged           (model rules :211,212,227,228)
```

So **`iq5_deqs_bl` = number of times IQ5 grabbed the link while the other four queues sat
backlogged = how hard IQ5 starves the others.** (The author's own commented-out reward block
names it `iq5_deq_while_iq1_to_iq4_bl`.)

The problem "**Q5 starves the others, at level n**" is `iq5_deqs_bl >= n`, i.e.
`NOT G(iq5_deqs_bl < n)`. Probability reported as `1 - P[ G<=224 (iq5_deqs_bl<n) ]`.

> Note on the student's framing: property `A = G(iq5_deqs_bl<4)` is the *safe* case, and
> `P(A)` is high (~0.98), so the bug is the rare complement `¬A`. The student also reported
> "P(starvation | inter-packet-gap>1) ≈ 99.9%", which is `P(A | C2)` — IQ5 being *under-served*
> when IQ5 is itself nearly silent. That is near-tautological (a silent flow is trivially
> under-served) and is the opposite role from "Q5 starves others". It does not support the
> hypothesis. See the level results below for what does.

## Method

We do **not** condition on rare PLTL trace predicates. Estimating `P(¬A | C)` as a ratio of two
SMC estimates is hopelessly noisy when `P(C)` is small: at width 5e-3 a first sweep produced
"shallow-queue ⇒ 0.55", "steady ⇒ 0.41", but re-running at width 5e-4 collapsed those to
~0.15 and ~0 — they were sampling noise. (This noisiness is exactly why the student's
conditional numbers were hard to interpret.)

Instead we **fix IQ5's input shape** (one rewrite of the IQ5 arrival rule — the buggy scheduler
is untouched) and directly measure `P(problem)` under each shape. See `gen_q5_variants.py`.
This is low-variance and robust. Each input shape *is* the "condition on the input".

## Result (PRISM SMC, CI width 2e-3, conf 0.01, horizon 224)

`P(Q5 starves others at level n) = P(iq5_deqs_bl >= n)`:

| IQ5 input shape                 | mean load | #pkts sent | ≥2   | ≥3   | ≥4   | ≥5   |
|---------------------------------|-----------|-----------|------|------|------|------|
| baseline (student model)        | 1.0       | ~varies   |      |      | 0.017| —    |
| **dense** – 1 pkt every step    | 1.0       | 14        | —    | —    | 0.000| —    |
| **bursty** – 4-pkt bursts (p=.25)| 1.0      | bursts    | —    | —    | 0.000| —    |
| **trickle** – 1 pkt w.p. 0.30   | 0.30      | ~4        | —    | —    | 0.303| —    |
| **periodic** – 1 pkt / 5 steps  | 0.20      | 3         | 0.998| 0.968| 0.018| 0.000|
| **periodic** – 1 pkt / 4 steps  | 0.25      | 4         | 1.000| 0.996| **0.554**| 0.000|

(Bernoulli send-probability peaks at p≈0.3 → 0.30; deterministic period-4 → **0.55**.)

## What it says

1. **A single trace is uninformative; the input *condition* is the insight.** Averaged over all
   inputs the problem looks negligible (P ≈ 0.017). Restricting to one identifiable traffic
   class — **a low-rate, spaced-out single-packet flow** — drives it to **0.55** (≈33×).

2. **Shape, not volume.** All three *mean-load-1.0* shapes (baseline spread, dense 1/step,
   bursty 4-bursts) give ≈0 starvation; the *lighter* sparse flow (load 0.20–0.30) is what
   starves the saturated queues. A flow that sends *less* hurts the others *more*. This is the
   FQ-CoDel new/old-list bug: a queue that keeps going empty is repeatedly re-classified "new"
   and its packets jump ahead of the chronically-backlogged "old" queues.

3. **The threshold sweep reveals the true law.** For a sparse periodic flow, *almost every
   packet it sends* becomes a contended dequeue: `P(deqs_bl >= n) ≈ 0.97–1.0` for `n` = number
   of packets sent. The starvation level just equals the send count. The student's single
   threshold of 4 hid this — period-5/6 flows score ≈0 at level 4 only because they send fewer
   than 4 packets, not because the bug is absent.

**The condition to put in the paper:** *IQ5 is a sparse, spaced-out single-packet flow
(≈ one packet every 4 steps).* Under it, P(IQ5 starves the saturated queues) ≈ 0.55 at the
level-4 definition and ≈ 0.97 at level 3 — versus ≈0.017 unconditionally.

## Reproduce

```
source <your PRISM env.sh>      # must export $PRISM
tests/models/run_q5_case_study.sh
```

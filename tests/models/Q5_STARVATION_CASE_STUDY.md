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

## Follow-up: the real driver is the warm-up, not periodicity

Inspecting simulation paths (`prism <model> -simpath 224 out`) shows the mechanism:

**All queues start EMPTY.** During the warm-up `t=0..3`, IQ1..IQ4 fill from their random
arrivals and each is dequeued once, migrating from the NEW list into the OLD list. Only after
`t≈4` are they "backlogged and in the old list". From then on everything sits in the old list
and is served round-robin, so a queue that participated in the warm-up gets exactly its fair
1/5 share (~3 contended dequeues over the horizon — this is why `dense` IQ5 caps at 3 and never
reaches level 4).

To exceed fair share, IQ5 must keep **re-entering the NEW list** (drain to empty, then a fresh
packet is classified "new" and jumps ahead of the backlogged OLD queues). The way to do that
reliably is to **stay idle through the warm-up and only then become active**: IQ5 never gets
absorbed into the old-list round-robin, so every one of its packets jumps the queue.

Path (IQ5 idle t=0..3, then sends every step), served queue per time step:
```
 t:   0 1 2 3 4  5  6  7  8  9 10 11 12 13
served:1 2 3 4 5* 5* 5* 5* 5* 5* 5* 5* 5* 5*     deqs_bl = 10   (IQ5 takes EVERY post-warm-up slot)
```
This happens in ~2/3 of runs; the other ~1/3 (warm-up doesn't line up) gives <3. Hence the flat
~0.68 profile below.

### Results across starvation levels (PRISM SMC, width 2e-3 / 5e-3)

`P(iq5_deqs_bl >= n)`:

| IQ5 input condition                         | ≥3   | ≥4   | ≥5   | ≥6   | ≥7   | ≥9   | ≥11 |
|---------------------------------------------|------|------|------|------|------|------|-----|
| sends DURING warm-up (1/4 steps, t=0,4,8,12)| 0.996| 0.553| 0.000| —    | —    | —    | —   |
| **idle warm-up, then every 2 steps**        | 0.979| 0.980| **0.972**| 0.000| —| —    | —   |
| **idle warm-up, then every step**           | 0.68 | 0.68 | 0.68 | 0.68 | 0.68 | **0.675**| 0.000 |
| **idle warm-up, then random (Bernoulli .6)**| 0.871| **0.846**| 0.777| 0.636| 0.434| —| —   |
| baseline (unconditioned)                    | 0.763| 0.017| 0.000| —    | —    | —    | —   |

### Answers to the three follow-up questions

1. **Are the other queues backlogged / in the old list from the start?** No. Everything inits
   empty; IQ1..IQ4 fill during `t=0..3` and enter the OLD list only after their first dequeue.
   This warm-up is decisive: a flow that sends *during* it joins the old-list round-robin (fair
   share); a flow that waits stays able to exploit new-list priority.

2. **Is level n=5 or 6 (or more) reachable, and with what condition?** Yes, easily. *Idle
   warm-up, then 1 packet every 2 steps* gives `P(≥5)=0.97`. *Idle warm-up, then a packet every
   step* gives `P(≥6)=…=P(≥9)≈0.68` — IQ5 captures up to all ~10 post-warm-up slots (the ceiling
   is ~10 because only 10 dequeues remain after the warm-up).

3. **Any non-periodic condition for n≥4?** Yes, and it is *stronger* than the periodic one.
   *Idle warm-up, then random Bernoulli(0.6) single-packet sends* gives `P(≥4)=0.85`,
   `P(≥6)=0.64`. Periodicity was never the point — the discriminating condition is the
   **idle-then-active phase structure**. (A simple stationary Bernoulli(0.3) with no idle phase
   still gives `P(≥4)=0.30`, also non-periodic.)

Schedules generated by `gen_q5_schedules.py`; levels in `q5_starvation_levels_hi.props`.

## Reproduce

```
source <your PRISM env.sh>      # must export $PRISM
tests/models/run_q5_case_study.sh
```

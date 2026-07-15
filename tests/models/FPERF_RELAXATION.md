# FPerf's certain-but-contrived workload vs. probabilistic relaxations

FPerf (NSDI'23, §2.1) synthesizes, for the FQ-CoDel starvation query, a workload that
makes the property hold with **certainty (100%)**. For `T=14`, query = `cdeq(Q5,T) > 2⌊T/5⌋`
(Q5 dequeues **≥5**, i.e. > 2× its fair share):

```
C1:  ∀t∈[1,6]  cenq(Q5,t) ≤ 1        # Q5 quiet early  -> not demoted to the "old" list
C2:  ∀t∈[7,14] aipg(Q5,t) ≥ 2        # <=1 pkt / 2 steps -> Q5 empties, re-activates as "new" (the bug)
C3:  ∀t∈[13,14] cenq(Q5,t) ≥ 5       # enough packets to dequeue 5
C4:  ∧_{i=1}^4 ∀t cenq(Qi,t) ≥ t     # Q1..Q4 backlogged EVERY step  (the query's antecedent)
```

The question: when we allow the probability to slip below 100%, which of these constraints
are essential, and which are incidental precision that a probabilistic assumption can drop?
Method: fix IQ5's arrival shape, use **natural random background** for Q1..Q4 (mean 2 pkt/step)
unless noted, and measure `P(iq5_deqs_bl ≥ n)` (SMC, width 3-4e-3, horizon 224). Note
`iq5_deqs_bl` only counts a Q5 dequeue when **all four** of Q1..Q4 are backlogged at that
instant — so every counted event is genuine theft under full 5-way contention.

## C4 (Q1..Q4 backlogged ∀t) — droppable almost for free, but it's a query artifact

C4 is the query's antecedent, not a discovered pattern, so relaxing it is the weakest of the
three points. Still, it is instructive:

| background Q1..Q4 | P(Q5 ≥5) |
|---|---|
| always full (≈ C4, strong) | **1.000** |
| never idle (≈ C4) | 1.000 |
| **natural random (C4 dropped)** | **0.971** |

Dropping C4 costs ~3 points, and it stays genuine theft:
- `P(Q5 ever served while a victim was idle) = 0.005` — under natural traffic the four others
  are backlogged at essentially every moment Q5 is served, so the *global* `∀t` assumption buys
  almost nothing over the *per-event* backlog check.
- Victim side (natural bg, Q5 idle-then-active): a background queue Q1 falls **below its fair
  share** (≤2 of ~2.8) with probability **0.68**, vs **0.01** when Q5 is a normal flow — the
  same 0.68 as `P(Q5 ≥5)`. Q5's over-serving *is* the victim's deprivation.

## C1 (quiet-early period) — ESSENTIAL, a real requirement

Relax the idle period (active = every step afterwards, natural bg):

| quiet for first ... | P(≥3) | P(≥4) | P(≥5) | P(≥7) |
|---|---|---|---|---|
| 0 steps (no idle) | 0.61 | **0.00** | 0.00 | 0.00 |
| 1 step | 0.31 | 0.00 | 0.00 | 0.00 |
| 2 steps | 0.31 | 0.00 | 0.00 | 0.00 |
| 3 steps | 0.37 | 0.00 | 0.00 | 0.00 |
| **4 steps** | 0.68 | **0.68** | 0.68 | 0.68 |
| **5 steps** | 0.97 | 0.97 | 0.96 | 0.96 |

There is a sharp threshold at the warm-up length (~4 steps here = the time for Q1..Q4 to each
be dequeued once and migrate to the old list). **Without the quiet start, the problem beyond
fair share disappears** (P(≥4)=0): Q5 joins the old-list round-robin and gets only its fair
1/5 share. So C1 is not contrivance we can wish away — it captures a genuine condition: *Q5
must be a newly-arriving / just-activated flow.* What IS relaxable is its exact length
(quiet-4 ≈ 0.68, quiet-5 ≈ 0.97, FPerf's `≤1 in first 6` ≈ 1) — a soft probability knob.

## C2 (exact aipg≥2 rate) — ROBUST, a whole family works

Relax the rate (quiet first 4 steps fixed, natural bg):

| Q5 rate after warm-up | P(≥3) | P(≥4) | P(≥5) |
|---|---|---|---|
| every step (dense) | 0.68 | 0.68 | 0.68 |
| **1 / 2 steps (= FPerf C2)** | 0.98 | 0.98 | 0.98 |
| 1 / 3 steps (slower) | 1.00 | 0.99 | 0.00* |
| random, p=0.3 (jittery, non-exact) | 0.66 | 0.40 | 0.19 |

(*1/3 sends only 4 packets in the window, so it can't reach level 5 — a count limit, not a
rate effect: each sparse packet still jumps the queue.)

FPerf's `aipg≥2` is one point in a broad family. Any sparse cadence — every 1, 2, or 3 steps,
and even a jittery random rate — triggers the bug; the rate mainly sets *how many* packets Q5
sends (hence the reachable level), because nearly every spaced packet becomes a contended
dequeue. So the exact rate is incidental precision that a qualitative assumption ("Q5 sends
sparingly") can drop.

## Takeaway

The probabilistic view **characterizes** which of FPerf's certain-workload constraints matter:

- **C4** (backlog ∀t): incidental (a query antecedent); droppable at ~3 points, and the global
  assumption is doing almost no work that the per-event contention check doesn't already do.
- **C1** (quiet start): a real, essential requirement (Q5 is a *new/joining* flow); only its
  exact length is a soft knob.
- **C2** (exact rate): incidental precision; a broad family of sparse rates works.

So the "much nicer assumption" is: **a new light flow that joins an already-busy link and
sends sparingly** — qualitatively C1 (quiet start) + C2 (sparse), dropping C3's exact count and
C4's global-backlog assumption. It holds with probability 0.68-0.97 instead of a rigid,
certain, four-part spec with specific time windows. And relaxing all the way to a stationary
"Q5 is a light flow (~0.3 pkt/step)" — no idle phase, no cadence — lands at P(≥4)=0.30,
squarely in the interesting operating regime rather than an adversarial corner.

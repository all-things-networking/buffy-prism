# Case study B, finished: the buggy FQ scheduler

*Model: `buffy/examples/jani/fq_buggy.buffy` (the Buffy paper's scheduler, HotNets'24 Fig. 2); runs:
`experiments/buffy_fq/` (`run_study.sh`). This replaces the preliminary numbers of draft §3.*

**The contention point.** One fair-queuing scheduler with five input queues and one dequeue per step,
over T = 14 steps. Queues 1–4 are bulk flows: 0 to 4 packets per step, uniformly. Queue 5 is the thin
flow, the one fair queuing is meant to protect. It receives no packet with probability P0 and 1–4
packets otherwise, uniformly. Buffers hold 8 packets.

**What the bug is, and what `Q` means.** The scheduler keeps a *new* list and an *old* list. A queue
that becomes backlogged while in neither list joins the new list, which is served first. A queue whose
last packet is dequeued leaves both lists. So a flow that sends single packets is emptied by every
service, rejoins the *new* list on its next packet, and jumps ahead of the backlogged bulk flows again.
RFC 8290 prevents this: a new queue that empties moves to the end of the *old* list. The bug omits
that rule. `FIX = 1` adds it.

`Q` is "the thin flow is served at least 4 times while all four bulk queues are backlogged", i.e.
`deqs_bl ≥ 4` within 14 steps. Round robin among five backlogged queues gives the thin flow at most 3
services in 14 steps, so `Q` is the bug's signature: the thin flow overtakes the bulk flows through the
new list, and the bulk flows starve. (The draft left the reading open; it is the bulk flows that are
starved, by the flow fair queuing favours.)

**Base rates** (2,000,000 runs each, `results/base_rates.log`):

| | P0 = 0.2 (uniform) | P0 = 0.6 (thin flow idle 60%) |
|---|---|---|
| the paper's scheduler | 3.6·10⁻⁴ | 0.0121 |
| with RFC 8290's rule (`FIX = 1`) | 4·10⁻⁶ | 4.8·10⁻⁴ |

The draft quoted the uniform base rate (≈ 4·10⁻⁴) but described the 60%-idle input. These are two
configurations, and both are kept here.

## Method

1. **Input histories at scale** (`fq_history.buffy`, `fq_histories.py`). Monitors record each step's
   arrivals, so the native batch simulator returns whole input histories at about 10 million runs per
   minute. Kept: every run with `Q` and a weighted 2% / 0.4% of the others (4M runs at P0 = 0.6, 20M at
   0.2).
2. **Learning** (`learn_fq.py`). Candidates are bounded-LTL formulas over the thin flow's per-step
   arrivals: runs of k steps with 0, exactly 1, ≤ 1, ≥ 1, ≥ 2 or ≥ 3 packets, in a window, and their
   negations. They also include the count family the draft used ("at most / at least c thin-flow packets
   by step b", `G (time != b || cenq <= c)`), and conjunctions of two. Formulas over the bulk flows'
   arrivals are candidates too. Each is scored on a training half and re-scored on a held-out half.
3. **Certification with `--condition-on`** (`certify_fq.py`). Each condition A is a `given` query. The
   compiler conditions the thin flow's source on A exactly and reports P(A) exactly; P(Q | A) comes
   from runs that all satisfy A. For the first conditions of each table, the old estimate (`_joint /
   _given` from 4M or 20M unconditioned runs) is shown alongside. It agrees everywhere.

## Results

**The bulk flows' arrival pattern does not matter.** Every condition on the bulk queues' arrivals
has lift 1.0 (`results/learn.log`). The anomaly is determined by the thin flow's timing alone. The
bulk queues are backlogged almost always anyway.

**P0 = 0.6** (base P(Q) = 0.0119; 200,000 conditioned runs each; `results/certify_p06.log`):

| condition A on the thin flow's arrivals | P(A), exact | P(Q \| A) | lift | rejection check |
|---|---|---|---|---|
| at most 1 packet by step 5 (the draft's condition) | 0.143 | 0.0694 | 6 | 0.0693 |
| … and at most 2 by step 7 | 0.079 | 0.0971 | 8 | 0.0969 |
| at most 1 by step 5, then single packets in two consecutive steps | 0.0113 | 0.293 | 25 | 0.296 |
| at most 1 by step 6, then single packets in two consecutive steps by step 10 | 0.0033 | **0.495** | 42 | — |
| packets in three consecutive steps among the first four | 0.179 | 5·10⁻⁶ | ≈ 0 | — |
| never two silent steps in a row through step 10 | 0.053 | 0 (< 1.8·10⁻⁵) | 0 | — |

**P0 = 0.2, uniform** (base P(Q) = 3.6·10⁻⁴; 1,000,000 conditioned runs each; rejection from 20M runs;
`results/certify_p02.log`):

| condition A | P(A), exact | P(Q \| A) | lift | rejection check |
|---|---|---|---|---|
| at most 2 packets by step 3 and at most 10 by step 7 | 0.050 | 0.0070 | 20 | 0.0071 |
| at most 3 packets by step 6 | 0.0054 | 0.066 | 187 | 0.066 |
| at most 1 packet by step 5 (the draft's condition) | 0.0019 | **0.162** | 455 | 0.161 |
| a packet in every one of the first four steps | 0.41 | 0 (< 3.7·10⁻⁶) | 0 | — |
| never two silent steps in a row through step 10 | 0.73 | 0 (< 3.7·10⁻⁶) | 0 | — |

**Reading.**
- **The danger is a quiet start followed by single packets.** While the thin flow is quiet, the bulk
  queues fill up and all four stay backlogged. Then each single packet it sends empties its queue on
  service, so its next packet rejoins the new list and overtakes the bulk flows again. Four such
  overtakes in 14 steps is `Q`.
- **The draft's hand-picked condition was the right idea.** "Little early traffic" is the best mild
  single condition at P0 = 0.6. The learner sharpens it by adding the single-packet pattern that
  follows: P(Q | A) rises from 0.07 to 0.50 as P(A) falls from 0.14 to 0.003.
- **At uniform load there is no mild dangerous condition.** The milder conditions (P(A) = 5%) raise `Q`
  only 20×, to 0.7%. Making `Q` likely needs a rare input profile (P(A) = 0.2%, P(Q | A) = 0.16). This
  is the "rare A" difficulty the draft anticipated, and `--condition-on` removes it: P(A) is exact,
  and P(Q | A) costs 1/P(A) ≈ 500× fewer runs than rejection.
- **The protective conditions are mild and absolute.** If the thin flow sends something in each of
  its first four steps (41% of runs at uniform load), `Q` did not occur in 1,000,000 conditioned runs.
  The same holds if it is never silent twice in a row (73%). Once it builds up a backlog early, it sits
  in the old list and is served in turn.

**The remedy.** With RFC 8290's rule the danger disappears even under the worst learned input
profiles (`results/certify_fixed.log`):

| condition | the paper's scheduler | with the fix |
|---|---|---|
| P0 = 0.6, the sharpest (P(A) = 0.0033) | 0.495 | 0.0027 |
| P0 = 0.6, the draft's | 0.069 | 0.0006 |
| P0 = 0.2, the draft's (P(A) = 0.0019) | 0.162 | 0.0006 |

**Possible, but essentially never: the existential view against the probabilistic one.** In the
samples, *every* run with `Q` had a quiet start:
- at uniform load, at most 3 thin-flow packets in the first 6 steps (7,222 `Q` runs out of 20M);
- at P0 = 0.6, at most 3 in the first 5 steps (47,892 out of 4M).

This is not a logical necessity. Z3 on Buffy's SMT-LIB unrolling, which covers every workload in the
distributions' support, finds that `Q` *can* happen after a loud start: with 4 or more thin-flow
packets by step 3, 4, 5 or 6, every query is `sat` (`run_necessary.sh`, `results/necessary.log`).
Probabilistically those workloads do not matter. P(`Q` and at least 4 packets by step 6) < 1.8·10⁻⁷
at uniform load (0 of 20M runs, 95% bound), against P(`Q`) = 3.6·10⁻⁴; and P(`Q` and at least 4 by
step 5) < 9.2·10⁻⁷ at P0 = 0.6, against 0.012. So more than 99.9% of the bug's probability lies in
the quiet-start region. An existential analysis (FPerf, or Buffy's SMT backend) can only say that
both kinds of workload trigger the bug; the probability says which one is the bug's real exposure.

**Validation.**
- Every conditioned estimate checked against rejection sampling agrees within its interval, as do the
  exact P(A) values against their rejection estimates.
- `--condition-on` itself is checked exactly against Storm's `_joint / _given` in `test/jani`
  (`cond_input.buffy`).

**Reproduce.** `experiments/buffy_fq/run_study.sh` runs everything: about 15 minutes, plus the Z3
queries.

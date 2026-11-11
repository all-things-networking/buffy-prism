# Case study F: PFC congestion spreading

*Model: `buffy/examples/jani/pfc.buffy`; runs: `experiments/buffy_pfc/` (`run_study.sh`).*

**The contention point.** RDMA fabrics run Ethernet *lossless* with priority flow control (PFC). When
a switch's ingress buffer passes a threshold (XOFF), it tells the upstream sender to *pause* until the
buffer drains to XON. That avoids drops, but a pause stops *every* packet on the link, so congestion
at one port can spread upstream to flows that never go near it. Guo et al. (SIGCOMM'16) report this
from production as congestion spreading and head-of-line blocking.

```mermaid
flowchart LR
    H["host H<br/>flows V and U"] -- "NIC link<br/>(paused by switch 1)" --> S1{"switch 1"}
    C["culprit C"] --> S1
    S1 --> O1(("O1: U<br/>idle"))
    S1 -- "link<br/>(paused by switch 2)" --> S2{"switch 2"}
    I["incast hosts<br/>(bursts)"] --> S2
    S2 --> O2(("O2: C + incast<br/>congested"))
    S2 --> O3(("O3: V<br/>idle"))
    style O2 fill:#f8d7da,stroke:#c33
```

**The model** (one priority class; every port and link moves one packet per step; 60 steps):
- **Flows.** Host H sends two flows over its one NIC link. V goes to switch 2's idle port O3. U goes
  to switch 1's idle port O1, and never touches switch 2. A culprit C enters switch 1 on another port
  and goes to switch 2's port O2, which an incast from hosts at switch 2 also targets.
- **Switches.** Each switch keeps one FIFO per ingress. The head moves to its egress queue when there
  is room; otherwise it blocks the FIFO (head-of-line blocking). O2 serves its two ingresses in
  alternation.
- **PFC (`PFC = 1`).** Switch 2's ingress from switch 1 pauses switch 1's link to it at XOFF = 4
  packets, until it drains to XON = 1. Switch 1's ingress from H pauses H's NIC the same way. With
  `PFC = 0` the ingresses tail-drop instead (lossy Ethernet).
- **Input.** V, U and C send a packet per step with probability 0.3, 0.3 and 0.5. The incast hosts
  together send a burst of 1–3 packets with probability 0.3 per step: one random draw, so conditions
  on the incast are certifiable with `--condition-on`. O2's offered load is 1.1, slightly overloaded.
- **Measured in the last 30 steps.** V or U is *blocked* in a step if it waits for reasons other than
  its own port: V behind a culprit packet stuck at switch 2's ingress head, or in a paused link or
  NIC; U behind a V packet stuck at switch 1's ingress head (its egress full), or in a paused NIC.
  **Q**: U is blocked in at least 10 of the 30 steps.

**Sources are open-loop** (no rate control such as DCQCN), so these are the dynamics of the switches
and PFC under a given offered load, not of a full RDMA stack.

## Results

**Spreading exists only with PFC, and it is rare** (100,000 runs per point, `results/sweep.log`):

| incast, culprit load | PFC | U blocked (Q) | H ever paused | V blocked ≥ 10 steps | V gets ≤ half its traffic |
|---|---|---|---|---|---|
| 0.3, 0.4 | off | 0 | 0 | 0.32 | 0.026 |
| 0.3, 0.4 | on | 0.00016 | 0.004 | 0.26 | 0.012 |
| 0.3, 0.5 | off | 0 | 0 | 0.64 | 0.086 |
| 0.3, 0.5 | on | **0.0013** | 0.030 | 0.53 | 0.028 |
| 0.4, 0.5 | off | 0 | 0 | 0.78 | 0.120 |
| 0.4, 0.5 | on | 0.0030 | 0.048 | 0.69 | 0.036 |

- **U, which never touches switch 2, is blocked only when pauses spread.** This happens in 0.13–0.30%
  of runs once O2 is overloaded.
- **V is blocked often with or without PFC.** It shares switch 2's ingress buffer with the culprit,
  whose packets wait for the congested O2: head-of-line blocking, which is not PFC's doing.
- **PFC helps V's delivery.** It improves threefold, because without PFC V's packets are dropped in
  that blocked buffer. With open-loop sources, PFC trades drops for blocking. Its cost is the spreading
  to U.

**Learned conditions** (4,000,000 runs, `learn_pfc.py`, `results/learn.log`; certified at incast 0.3
and culprit 0.5, base P(Q) = 0.00155, `results/certify_blkU.log`):

| condition A | P(A) | P(Q \| A) | how certified |
|---|---|---|---|
| the culprit sends in 8 consecutive steps between steps 20 and 40, and never pauses 3 steps in steps 20–50 | 0.0064 | 0.0157 | rejection (two sources) |
| the culprit sends in 6 consecutive steps between 20 and 40, and at least 26 incast packets by step 40 | 0.062 | 0.0076 | rejection |
| at least 42 incast packets by step 50 | 0.061 (exact) | 0.0034 | `--condition-on`; rejection 0.0035 |
| at least 44 by step 50, and no 6 consecutive steps without incast | 0.014 (exact) | 0.0039 | `--condition-on` |
| **at most 14 incast packets by step 40** | 0.064 (exact) | **7.5·10⁻⁵** | `--condition-on` |
| … and at most 30 by step 60 | 0.057 (exact) | 7.0·10⁻⁵ | `--condition-on` |

**Reading.**
- **No short pattern makes spreading likely.** The best conditions reach P(Q | A) ≈ 1.6%, a tenfold
  lift, and need a *persistent culprit*: one that sends without a break for 8 steps. Heavy incast volume
  alone lifts it only twice. Spreading needs a sustained overload of O2 *and* the victims' own packets
  to be in the wrong place when the pauses come. That is a combination of three independent sources,
  which a short formula over one of them cannot capture. This is the case where the recipe's answer is
  "no mild dangerous assumption exists". That is itself useful: the hazard is diffuse, not
  input-pattern driven.
- **The useful assumption is protective.** If the incast brings at most 14 packets in the first 40
  steps (6% of runs), spreading becomes 20 times rarer. The learner's sample had suggested "never";
  certification on 200,000 conditioned runs corrected it to 7.5·10⁻⁵. This is the reason to certify
  learned conditions on fresh runs.
- **Exact conditioning had a cost here.** The incast's state for conditions on counts up to step 50
  is large (step × packets so far × monitor). The conditioned model of the second incast condition was
  a 10 MB C file that took several minutes to compile. With `--target native` the same condition
  compiles in 0.14 s and h is computed on demand (see the joint round below).

## Joint conditions over all four sources (`--target native`)

The first round could condition exactly only on the incast, since `--condition-on` supported one random
source. The native target now conditions several sources jointly: it reweights their joint outcome
in each step, with h memoised over the input states the recursion reaches (decision 52). This round
learns over all four sources and certifies every condition exactly:
- the incast bursts;
- the culprit C;
- the victims' own sends, U and V.

**Method.**
- **Histories.** 8,000,000 runs (`pfc_histories.py`, `results/histories4.log`; 12,222 with Q).
- **Learner.** `learn_joint.py` (`results/learn_joint.log`) searches:
  - runs and their negations, as before, over atoms of every source;
  - counts so far of each source (`inc`, `cc`, `cu`, `cv`);
  - conjunctions of up to three formulas, from a beam of the 40 best formulas of each source.
- **Certification.** `certify_joint.py` (`results/certify_joint.log`; 200,000 conditioned runs per
  condition, with P(A) exact).

**A bound shapes the question.** P(Q | A) ≤ P(Q) / P(A). With P(Q) = 0.0015, a condition holding in 1%
of runs can make Q at most 15% likely, and one holding in 0.1% at most 100% likely. So the question is
not whether a mild condition makes spreading likely, which is impossible here. It is how much of
spreading a short input condition explains: its precision P(Q | A), and its recall P(A | Q).

**Certified results.** Base P(Q) = 0.00154 (4,000,000 runs):

| A (the best found for its sources) | sources | P(A), exact | P(Q \| A) | lift | P(A \| Q) | input states |
|---|---|---|---|---|---|---|
| ≥ 50 incast packets by step 60, ≥ 12 by step 10 | incast | 0.0108 | 0.0038 | 2 | 0.03 | 9,045 |
| culprit ≥ 25 packets by step 40, ≥ 32 by 50, ≥ 39 by 60 | culprit | 0.0108 | 0.0196 | 13 | 0.14 | 1,950 |
| culprit ≥ 25 / ≥ 31 by steps 40 / 50, U ≥ 21 sends by 60 | culprit, U | 0.0105 | 0.0208 | 13 | 0.14 | 80,740 |
| culprit ≥ 31 / ≥ 36 by steps 50 / 60, V ≥ 21 sends by 60 | culprit, V | 0.0109 | **0.0247** | 16 | 0.18 | 76,390 |
| culprit ≥ 26 / 35 / 38 by steps 40 / 50 / 60 | culprit | 0.0031 | 0.0264 | 17 | 0.05 | 1,930 |
| culprit ≥ 24 / 32 by steps 40 / 50, V ≥ 23 sends by 60 | culprit, V | 0.0033 | 0.0347 | 23 | 0.07 | 79,630 |
| culprit ≥ 31 by step 50, V ≥ 21 by 60, ≥ 28 incast packets by 40 | incast, culprit, V | 0.0040 | **0.0389** | 25 | 0.10 | 11,057,020 |
| culprit ≥ 28 / 36 / 39 by steps 40 / 50 / 60 | culprit | 0.0011 | 0.0315 | 20 | 0.02 | 1,940 |
| culprit ≥ 25 by step 40, V sends 6 steps in a row in steps 21–56 | culprit, V | 0.0012 | 0.0371 | 24 | 0.03 | 7,542 |

**Reading.**
- **The culprit's volume drives spreading, not the incast.** Conditions on the incast alone lift Q only
  2–3 times. Conditions on the culprit's cumulative arrivals lift it 13–20 times. The incast already
  overloads O2 on average. What decides whether pauses reach H is how many culprit packets pile up in
  switch 1's egress e1 and switch 2's ingress. That pile-up stops V at switch 1's ingress head, and U
  waits behind V. The first round could not see this, because it could certify only incast conditions
  exactly. Its culprit conditions were runs, not counts, and were estimated by rejection.
- **The victims' own traffic adds a little.** V sending more (it shares H's NIC with U) gives the best
  two-source conditions, about 1.25 times the precision of culprit-only conditions with equal P(A).
  Adding the incast gives the best condition found (lift 25). U's own sends add almost nothing.
- **Still no short explanation.** The best condition reaches P(Q | A) = 0.039, a tenth of what the
  bound allows at its P(A), and covers 10% of Q. At 1% of runs, conditions explain at most 18% of Q.
  The first round's conclusion stands, now over all four sources rather than one: spreading is a
  diffuse, accumulated effect. The culprit's volume is its main input-side cause.
- **Certification corrects the learner again.** The last row's held-out estimate was 0.046;
  certification gives 0.037.

**Validation and cost.**
- **Rejection cross-check.** For the culprit-and-V condition at 1%, rejection over 4,000,000 runs gives
  1,076 / 43,744 = 0.0246 with P(A) ≈ 0.01094. The conditioned estimate is 0.0247 with P(A) = 0.01094
  exact.
- **Earlier conditions, now exact.** The first round's two-source conditions agree with their
  rejection estimates:
  - culprit runs: P(A) = 0.006407 exact against ≈ 0.00643;
  - culprit and incast: P(A) = 0.0623 against ≈ 0.0624.
- **Exactness of the method.** `cond_joint.buffy` checks it against Storm, in buffy-prism's
  `tests/test_native_conditioning.py`.
- **Cost.** The three-source condition memoises h over 11 million input states, about 25 s in all.
  Every other condition takes under 10 s. Each is one Buffy compile of under a second and one
  simulator build.

**Validation.** `--condition-on` agrees with rejection where both were run (0.0034 vs 0.0035), and its
exact P(A) matches the rejection estimates. The model's semantics are checked only by these
cross-checks and by the expected limiting cases: without PFC, U is never blocked; at lower load,
spreading vanishes. There is no independent oracle or reference model for this study.

**Reproduce.** `experiments/buffy_pfc/run_study.sh` (about 45 minutes, plus about 30 for the joint round).


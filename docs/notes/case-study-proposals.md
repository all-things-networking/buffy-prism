# Proposed case studies: bursty traffic, rewards, adversaries (2026-11-01)

Not started; recorded for later. Each one uses compiler features added in the third round (Buffy
`main` 77d8ce2: phases and state-dependent distributions, rewards and expected values, derived
importance functions, the choose layout) and needs something the Modest Toolset cannot provide at
FQ size. What modes cannot do was measured on `bursty`/`bursty_mdp` and on FQ (see
`experiments/buffy_jani/README.md`, third round):

- `modes` estimates expected rewards only as `C<=k` and `F`: for `I=k` it returns the initial value,
  and it cannot simulate long-run averages (`S`) on discrete-time models.
- `mcsta` (exact) checks only `F` reward forms, and is limited to small models like Storm.
- For MDPs, `modes` resolves nondeterminism uniformly, or by lightweight scheduler sampling for
  probabilities. It does not optimise expected rewards, and its importance splitting assumes a
  fully probabilistic model.

Exact checking (Storm) is used only on reduced instances (N = 2–3 flows, small capacities) to
validate each study's estimator; FQ-sized results are statistical, always under `timeout`.

## A. FQ starvation under bursty traffic at equal load

**Question.** Does burstiness alone change the probability that the FQ bug starves a flow, at the same
mean arrival rate? And how do per-flow long-run throughput and backlog shift?

**Model.** `fq_buggy.buffy` with each source replaced by an ON/OFF phase (`phase on_i ~ ...` and
`traffic ~ on_i == 1 ? ... : ...`), parameterised by mean load and burstiness (mean ON/OFF sojourn),
at the same P0 grid as the paper.

**Measures.** `P[F<=T starve]` (simulation can do this), plus per-flow long-run throughput and backlog
`E{tput_i}[S]`, `E{backlog_i}[S]`, and the backlog curve over time `E{backlog_i}[I=k]` for k = 0..T.

**Beyond modes.** `S` and `I=k` are not available in modes. A native estimator is needed: batch means
or regenerative estimates for `S`, and per-step marginals for `I=k`.

**Expected result.** Starvation and backlog vs burstiness at fixed load: a curve, not a single point.
The hypothesis is that bursts of the competing flows lengthen the windows in which the buggy
dequeue path starves the victim, so the same bug shows up at loads where i.i.d. traffic hides it.

## B. Worst-case expected loss: adversarial bursts (MDP)

**Question.** Over all workloads of one adversarial flow, what is the maximum expected number of
packets lost (or the backlog) of the other flows within T steps, and what does that worst workload
look like?

**Model.** As A, with the adversary's phase `nondet` (it chooses ON/OFF each step) or its traffic
`nondet`, in the choose layout (one decision per source and step).

**Measures.** `Emax{drops_i}[C<=T]`, `Emax{backlog_i}[S]`, and the learned adversarial policy.

**Beyond modes.** Modes cannot optimise expected rewards over schedulers. A learned scheduler (RL)
evaluated by native simulation gives sound statistical **lower** bounds on `Emax`. Storm on reduced
instances gives the exact value to compare against.

**Expected result.** A worst-case loss that exceeds every i.i.d. or bursty-but-fixed workload, and a
readable adversary (for example, "burst when the victim's deficit counter is low"). This is the
quantitative counterpart of FPerf's workload synthesis.

## C. Rare worst-case starvation (MDP + importance splitting)

**Question.** At low load (P0 = 0.2), how likely can an adversary make starvation, which is rare under
i.i.d. traffic (3.3e-4)?

**Measures.** `Pmax[F<=T starve]` together with the derived importance function `starve_imp`.

**Beyond modes.** RESTART in modes needs a fully probabilistic model; optimising over schedulers and
splitting at the same time is not supported. A natively learned adversary plus splitting is needed:
learn the policy, then evaluate the induced DTMC with RESTART driven by the compiled `starve_imp`.

**Expected result.** The gap between the typical and worst-case starvation probability: orders of
magnitude at low load if the adversary can line the victim up with the bug.

## D. Long-run fairness of FQ under bursty traffic

**Question.** Does FQ stay fair in the long run when flows have different burstiness but equal mean
rates?

**Measures.** Per-flow long-run throughput `E{tput_i}[S]` and its spread, or Jain's index computed
from the per-flow values. Also long-run drop rates `E{drops_i}[S]`.

**Beyond modes.** Long-run averages again (not available in modes); Storm only for N = 2–3.

**Expected result.** Fairness as a function of the burstiness ratio, plus the long-run cost of the
bug (the throughput a starved flow loses), both of which i.i.d. models cannot show.

## E. Transient recovery after a burst

**Question.** After a synchronised burst on all flows, how long does FQ take to return to its
steady-state backlog, and does the bug delay recovery for one flow?

**Measures.** The curve `E{backlog_i}[I=k]` for k = 0..T from a post-burst initial state,
and `E{steps}[F backlog_i <= b]` (expected time to drain). Compiler addition needed: network
`init` currently sets globals only; it would have to accept initial buffer contents.

**Beyond modes.** `I=k` is not available in modes (it returns the initial value). The expected-time
part (`F`) is available, which makes it a cross-check between the two tools.

**Expected result.** Recovery-time curves per flow; a visible extra delay for the flow the bug
penalises.

## Validation shared by all studies

- Reduced instances (N = 2–3) are checked exactly with Storm (every reward form) and, for `F`,
  `mcsta`. Native estimates must lie within their confidence intervals.
- Any measure modes can estimate (`P`, `C<=k`, `F`) is cross-checked against modes at full size.
- Adversarial policies are re-evaluated as fixed schedulers (DTMCs) by independent simulation, so a
  reported worst case is always backed by a concrete workload.

## Combined list (with the netmdp native-simulator brainstorm)

Agreed with the netmdp session; proposals only, nothing started. "Native" means the netmdp native
JANI simulator, which now estimates `C<=k` and `I=k` (`JaniModel.simulate_rewards`, any
`NativePolicy`; `curve=True` gives every bound from one batch, `start=` runs from an arbitrary
state). On full `fq_buggy` (P0 = 0.6, T = 14) its `C<=14` values match modes (for example
backlog at queue 4: 67.775 against 67.771) at about 17x the speed per run, and its `I=14` backlog
at queue 4 is 7.032 where modes returns 0.

| # | Study | Measures | Why modes can't | Compiler side | Native side |
|---|---|---|---|---|---|
| 1 | Bursty traffic at equal load (A) | `P[F<=T starve]`; per-flow `C<=T` drops and backlog; `I=k` backlog curve; long-run `S` | `I=k`, `S`; no common random numbers across models | parameterised bursty FQ models (phases exist) | sweep driver with common random numbers (see N3); regenerative `S` estimator (N2) |
| 2 | Worst-case expected loss, learned adversaries (B) | `Emax{drops_i}[C<=T]`, `Emax{backlog_i}[S]`, as statistical lower bounds from a re-simulated learned policy; Storm exact at N = 2-3 | no optimisation of expected rewards | per-flow rewards (exist); `once` phases for a family-based comparison | native lightweight scheduler sampling as the baseline (N4); Q-learning or cross-entropy on the (dense) reward signal; lower bounds as in N5; `S` (N2) |
| 3 | Rare worst-case starvation (C) | `Pmax[F<=T starve]` at P0 = 0.2 (i.i.d.: 3.3e-4) | RESTART needs a fully probabilistic model | `--auto-importance` (exists); possibly a finer importance function with occupancy terms, since a single counter gives splitting too few levels | learner, then native RESTART on the induced DTMC (exists), with a compositional importance function that has intermediate levels (N6) |
| 4 | Tails of loss and CVaR (new) | quantiles and CVaR_0.99 of `C<=T` drops; `P(total loss >= x)` for rare x via RESTART on a loss monitor, under learned adversaries too | `--cdf` only for plain Monte Carlo; no splitting under schedulers | loss monitors (exist) | quantiles and CVaR by adaptive multilevel splitting; `P(total loss >= x)` by RESTART on the monitor (N7) |
| 5 | Fairness (D) | finite horizon: Jain's index of per-flow `C<=T` served or dropped, from joint per-run samples (possible now); long run: per-flow `S` | Jain's index is nonlinear in per-flow totals, so it needs joint per-run samples; `S` | per-flow throughput rewards (expressible) | per-run Jain's index with DKW intervals (N8); `S` (N2) |
| 6 | Transient recovery after a burst (E) | `I=k` backlog curves for all k from one batch; `E{steps}[F backlog_i <= b]` | `I=k` | network `init` of buffer contents, so the model starts post-burst and modes can cross-check the `F` part | `start=` already runs from a post-burst state; `F` as in N1 |

Expected results: (1) bursts expose the FQ bug at loads where i.i.d. traffic hides it; (2) much
more loss than uniform traffic, and possibly different loss-maximising and starvation-maximising
adversaries; (4) FQ variants with similar mean loss differ sharply in the tail; (5) equal mean rates
with different burstiness give unfair long-run shares under the buggy FQ.

Shared validation: as above (N = 2-3 exact with Storm for every reward form; native estimates
within confidence intervals; modes cross-checks at full size; worst cases backed by a concrete
re-simulated policy).

Suggested build order: native `S` and `F` (N1, N2; unblocks 1, 2, 5, 6), then lightweight scheduler
sampling and reward-driven learning (2, 3), then tails (4). Compiler side: network `init` of buffers
(6), then `once` phases (2, 3). Models: an `S`-ready FQ example (e.g. `fq_buggy_lr.buffy`) for
studies 1, 2 and 5 (see N2).

### Native-side implementation details

Statistics used throughout: decisions against a threshold use the betting test
(`hyptest/betting.py`, valid at every sample size); fixed-sample intervals use Clopper-Pearson for
probabilities and DKW for bounded rewards (`hyptest/intervals.py`); a family of reported intervals
or tests gets per-interval levels from `per_test_level` (Bonferroni). Learning, pilot and evaluation
runs use separate random streams (`derive_seed(seed, phase, i)`).

- **N1. `E[F goal]` (reward until a goal).** The value is infinite if the goal can be missed, and
  the per-run reward has no a-priori bound, so a simple step cap changes the query. Report:
  (a) a sound lower bound by the limit-PAC DKW-E-Lower procedure of Budde, Hartmanns, Meggendorfer,
  Weininger & Wienhöft (TACAS 2025), which needs no reward bound; and (b) where useful, the
  truncated quantity `E[reward until min(goal, k)]`, which is bounded by k times the largest
  per-step reward, gets a two-sided DKW interval, and is itself a lower bound on `E[F goal]`.
- **N2. Long-run average `S`.** Use the regenerative method: a cycle starts each time the run is at
  a step boundary (`turn = 0` in the choose layout) with all queues empty; the estimate is the ratio
  of the summed cycle rewards to the summed cycle lengths. This handles the period K+1 of the choose
  layout (batch means would need batch lengths that are multiples of K+1 and a mixing check).
  Requirements: the model is recurrent. A network with `horizon T` has a bounded `time` counter, so
  every run ends in an absorbing state and `S` is that state's value; monitors that saturate (FQ's
  `cenq`, `aipg`, `deqs_bl`) leave their initial values for good, so a regeneration state that
  includes them never recurs. An `S`-ready example (e.g.
  `fq_buggy_lr.buffy`) drops `horizon` and replaces saturating monitors with wrapping ones or none;
  no compiler change is needed. In the choose layout `turn = 0` holds at every time-step boundary,
  and "all queues empty" is recurrent under any load below 1. Further, the
  scheduler is stationary (`NativePolicy` keys without the step count); the regeneration state is
  recurrent under that scheduler, which is checked by counting cycles (too few cycles: report no
  value). The interval for the ratio is asymptotic (CLT for regenerative ratios) and labelled so;
  a finite-sample alternative is the PAC mean-payoff method of Agarwal, Guha, Křetínský & Pazhamalai
  (FMSD 2025), which needs the minimum transition probability and many more samples.
- **N3. Common random numbers.** Each step uses one uniform for the destinations of all
  synchronised participants (inverse CDF, rescaled within each chosen interval) and one for the
  scheduler's choice when several edges are enabled. Runs with the same seed are therefore coupled
  but not perfectly synchronised: changing one participant's probabilities shifts the uniform seen
  by the later participants in that step, and a change in the number of enabled edges shifts the
  stream. Each marginal estimate stays unbiased; the variance reduction of differences is measured
  (paired against independent seeds), not assumed. Finite differences of a parameter are biased by
  the step size (Glasserman & Yao 1992); report them as differences, not derivatives.
- **N4. Lightweight scheduler sampling (baseline adversary).** A scheduler is a 64-bit seed; its
  choice in a state is a hash of (seed, state, t) (or (seed, state) for stationary schedulers), as in
  modes (D'Argenio, Legay, Sedwards & Traonouez, STTT 2015). It is a third `jm_pick` source next to
  tables and callbacks. Screening many seeds with few runs each, then re-evaluating the best few on
  fresh streams (smart sampling), gives the baseline that learned adversaries must beat.
- **N5. Lower bounds on Pmax / Emax from a concrete scheduler.** Any fixed scheduler's value is at
  most the optimum, so a valid lower confidence bound under a frozen scheduler (learned table, LSS
  seed) is a valid lower bound on Pmax / Emax. The scheduler is frozen before evaluation and
  evaluated on fresh streams; when the best of m candidates is reported, the bound uses
  `per_test_level(level, m)`. Probabilities use Clopper-Pearson or the betting test; expected
  rewards use DKW with the bound horizon × largest per-step reward.
- **N6. Importance functions for splitting under a scheduler.** RESTART and fixed effort need
  intermediate levels; `fq_deqs_bl` alone jumps to the goal in one step. Use a compositional
  importance function built from the model structure and the property (Budde, D'Argenio &
  Hartmanns, "Automated compositional importance splitting", SCP 2019), e.g. combining the
  dequeue-backlog counter with queue occupancy, with levels by expected success. RESTART per-run
  estimates can exceed 1 (re-crossings), so their bound for DKW or the betting test is the product
  of the splitting factors; fixed-effort estimates lie in [0, 1] and are preferred when a
  bounded-sample guarantee is needed.
- **N7. Loss tails.** `P(total loss >= x)` for a given x: RESTART with importance = the loss monitor;
  for several x, a per-x level from `per_test_level`. Quantiles (VaR) and CVaR: adaptive multilevel
  splitting (Cérou & Guyader, Ann. Appl. Probab. 2016; Guyader, Hengartner & Matzner-Løber 2011),
  whose quantile estimator has a known distribution; plug-in CVaR from a splitting-estimated tail is
  a ratio of estimates and biased. Small DTMC instances get exact tails from Storm (or Dice) as
  ground truth.
- **N8. Fairness.** The reported measure is the expected per-run Jain's index E[J(x_1..x_N)] of the
  per-flow totals (served or dropped, `C<=T`). J lies in [1/N, 1], so DKW gives a sound interval.
  J of the expected totals is a different quantity (J is nonlinear) and is reported only as a
  secondary figure, with an asymptotic (delta-method) interval.

Note on study 4: a Dice back end (see `buffy-mdp-and-frontends.md`, section 6) could give the exact
distribution of total loss on small DTMC instances, as ground truth for the native tail estimators.

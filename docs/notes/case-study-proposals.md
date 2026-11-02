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
| 1 | Bursty traffic at equal load (A) | `P[F<=T starve]`; per-flow `C<=T` drops and backlog; `I=k` backlog curve; long-run `S` | `I=k`, `S`; no common random numbers across models | parameterised bursty FQ models (phases exist) | sweep driver with common random numbers (same seed, one inverse-CDF uniform per step) for low-variance differences between burstiness levels; `S` estimators (batch means or regeneration) |
| 2 | Worst-case expected loss, learned adversaries (B) | `Emax{drops_i}[C<=T]`, `Emax{backlog_i}[S]`, as statistical lower bounds from a re-simulated learned policy; Storm exact at N = 2-3 | no optimisation of expected rewards | per-flow rewards (exist); `once` phases for a family-based comparison | Q-learning or cross-entropy on the (dense) reward signal; `S` |
| 3 | Rare worst-case starvation (C) | `Pmax[F<=T starve]` at P0 = 0.2 (i.i.d.: 3.3e-4) | RESTART needs a fully probabilistic model | `--auto-importance` (exists); possibly a finer importance function with occupancy terms, since a single counter gives splitting too few levels | learner, then native RESTART on the induced DTMC (exists) |
| 4 | Tails of loss and CVaR (new) | quantiles and CVaR_0.99 of `C<=T` drops; `P(total loss >= x)` for rare x via RESTART on a loss monitor, under learned adversaries too | `--cdf` only for plain Monte Carlo; no splitting under schedulers | loss monitors (exist) | tail and CVaR estimators with DKW bands; splitting on the monitor |
| 5 | Fairness (D) | finite horizon: Jain's index of per-flow `C<=T` served or dropped, from joint per-run samples (possible now); long run: per-flow `S` | Jain's index is nonlinear in per-flow totals, so it needs joint per-run samples; `S` | per-flow throughput rewards (expressible) | `S` estimators |
| 6 | Transient recovery after a burst (E) | `I=k` backlog curves for all k from one batch; `E{steps}[F backlog_i <= b]` | `I=k` | network `init` of buffer contents, so the model starts post-burst and modes can cross-check the `F` part | `start=` already runs from a post-burst state; `F` with a step cap |

Expected results: (1) bursts expose the FQ bug at loads where i.i.d. traffic hides it; (2) much
more loss than uniform traffic, and possibly different loss-maximising and starvation-maximising
adversaries; (4) FQ variants with similar mean loss differ sharply in the tail; (5) equal mean rates
with different burstiness give unfair long-run shares under the buggy FQ.

Shared validation: as above (N = 2-3 exact with Storm for every reward form; native estimates
within confidence intervals; modes cross-checks at full size; worst cases backed by a concrete
re-simulated policy).

Suggested build order: native `S` estimators and `F` with a step cap (unblocks 1, 2, 5, 6), then
reward-driven learning (2, 3), then tails (4). Compiler side: network `init` of buffers (6), then
`once` phases (2, 3).

Note on study 4: a Dice back end (see `buffy-mdp-and-frontends.md`, section 6) could give the exact
distribution of total loss on small DTMC instances, as ground truth for the native tail estimators.

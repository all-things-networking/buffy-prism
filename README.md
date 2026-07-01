# buffy-prism — Case study: the LLM inference batch scheduler

This branch (`llm-batch-scheduler-case-study`) develops the **third motivating case
study** for probabilistic reasoning about *contention points* in networks and systems.
The goal, shared across all three case studies, is to show the value of a tool that —
given a description of a **bad event** and a **condition** over the parameters that
describe the input to a contended component — reports **how probable that bad event is
under that condition**, and in particular can surface a **non-obvious, "mild" assumption
about the input pattern** that makes something undesirable surprisingly likely.

The contention point here is the **batch scheduler of a GPU worker in LLM inference
serving**: requests of different shapes (prompt length, output length, arrival timing)
arrive and must be batched while balancing prefill vs. decode work and a shared,
finite KV-cache memory pool.

> New to LLM serving? Start with **[SCHEDULING_PRIMER.md](model/llm_batch_scheduler/SCHEDULING_PRIMER.md)** —
> a ground-up, cited walkthrough of how state-of-the-art scheduling works (prefill/decode,
> continuous batching, PagedAttention, chunked prefill, preemption, FCFS vs. sophisticated
> policies, SLO metrics, and real request-pattern inputs).

## The reusable methodology (from the FQ-CoDel and incast case studies)

Each case study follows the same template:

**probabilistic input stage → deterministic contention point → monotone "bad-event"
counter → conditions expressed over input-describing variables.**

The payoff is an assumption `C` about the input that is **mild** (non-trivial
probability / broad range) yet **informative** (strongly raises `P(bad)`), and whose
danger is typically **invisible at any single component** — something a single
counterexample cannot reveal. Two complementary ways to express the assumption:

- **Flavor A — conditional queries.** Track an input-feature state variable, then compute
  `P(bad | C) = P(bad & C) / P(C)` and compare against the baseline `P(bad)`. This matches
  the tool's framing directly.
- **Flavor B — parameter box + monotonicity.** Leave the input-shape parameters as
  undefined constants; the assumption is a *box* (range) over them, certified cheaply at
  its least-favorable corner. Robust against the "corner-skewed assumption" trap.

This branch uses **conditional queries as the primary flavor, complemented by a
request-shape sweep** (fixing the input shape and measuring `P(bad)` directly, which
avoids the noisy statistical-model-checking ratios that arise when conditioning on rare
predicates).

## Probabilistic model checking with PRISM

Models are **discrete-time Markov chains (DTMCs)**: multiple transitions per state, each
weighted, weights summing to 1 — used here to model random request arrivals and their
sampled characteristics. One DTMC step corresponds to one scheduler iteration.

Properties are path properties in PCTL. PRISM supports two evaluation modes with no
change to the model:
- **Exact (verification)** — precise probabilities via sparse-matrix computation; feasible
  only for small state spaces.
- **Statistical model checking (SMC / "Simulation")** — Monte-Carlo trials with confidence
  intervals; orders of magnitude faster, converges to the exact value. Needed for large
  models. Caveat: conditional probabilities computed as a **ratio** of two rare-event
  estimates can be noisy under SMC, so we keep the model small enough for exact
  verification where possible and complement ratios with direct `P(bad)` measurements.

PRISM computes conditional probabilities by division: `P(A | C) = P=?[A & C] / P=?[C]`,
where `A` and `C` are path conditions (see reference [2] for a more efficient
model-transformation approach).

## Repository layout (this branch)

- [`model/llm_batch_scheduler/`](model/llm_batch_scheduler/) — the case study.
  - [`SCHEDULING_PRIMER.md`](model/llm_batch_scheduler/SCHEDULING_PRIMER.md) — domain primer.
  - *(PRISM model, queries, Python oracle, and notes — added as the study is built.)*

The general SMC framework and the earlier FQ-CoDel / priority-queue models live on the
`main` branch; this branch is intentionally stripped to the case study, mirroring the
`incast-buffer-case-study` branch.

## Selected references

1. G. Agha and K. Palmskog, "A Survey of Statistical Model Checking," *ACM TOMACS*, 28(1), 2018. doi:10.1145/3158668.
2. C. Baier, J. Klein, S. Klüppelholz, and S. Märcker, "Computing Conditional Probabilities in Markovian Models Efficiently," in *TACAS 2014*, Springer, pp. 515–530. doi:10.1007/978-3-642-54862-8_43.
3. M. E. Andrés and P. van Rossum, "Conditional Probabilities over Probabilistic and Nondeterministic Systems," in *TACAS 2008*, Springer, pp. 157–172. doi:10.1007/978-3-540-78800-3_12.
4. M. Kwiatkowska, G. Norman, and D. Parker, "PRISM 4.0: Verification of Probabilistic Real-time Systems," in *CAV 2011*, LNCS 6806, Springer, pp. 585–591.
5. M. Kwiatkowska, G. Norman, and D. Parker, "Stochastic Model Checking," in *SFM 2007*, LNCS 4486, Springer, pp. 220–270.
6. M. Ji, D. Wu, and Z. Chen, "Verification Method of Conditional Probability Based on Automaton," *J. Networks*, 8(6), 2013, pp. 1329–1335. doi:10.4304/JNW.8.6.1329-1335.

Domain references for the LLM-serving model (Orca, PagedAttention, Sarathi-Serve,
DistServe, and others) are cited in
[SCHEDULING_PRIMER.md](model/llm_batch_scheduler/SCHEDULING_PRIMER.md).

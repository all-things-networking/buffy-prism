# Case study C, finished: the LLM inference batch scheduler

*Model: `buffy/examples/jani/llm_sched.buffy` at realistic scale (8 request records, 40 iterations, as in
`experiments/buffy_case_studies/run_smc.sh`); runs: `experiments/buffy_llm/` (`run_study.sh`). This replaces
the exploratory findings of draft §4.*

**The configuration.** One GPU worker with continuous batching and chunked prefill:
- 3 batch slots, a KV pool of 32 blocks and prefill chunks of 8 blocks;
- prompts of 1 or 8 blocks and outputs of 1 or 16 tokens;
- a background request arrives in an iteration with probability 0.9, its prompt and output each long
  with probability 1/2;
- one tracked interactive request (short prompt, 2-token output) arrives at iteration 5;
- admission first-come-first-served (`ADM_POLICY = 0`) and eviction of the latest arrival (last in,
  first out) are the defaults.

The arrivals are one random draw per iteration with five outcomes: none, or one of four shapes. So
every condition on the arrival history reads a single source, and `--condition-on` certifies it
exactly.

**The bad events.** At this scale the tracked request's worst gap between tokens (counting the wait
before its first token) is bimodal. Either it is admitted and decodes normally, with gaps of 1–4
iterations (59%), or it waits behind long requests for a slot, with gaps of 13–31 iterations (41%).
The draft's stall threshold of 3 iterations therefore holds in 47% of runs and is not a rare event.
We study two rare ones:
- **evicted**: the tracked request is evicted at least once (P = 0.055). With the policy that never
  evicts it (`POLICY = 1`) this is 0, and the long-wait probability is unchanged, so the waits are
  queueing, not eviction;
- **wait ≥ 20**: its worst gap is at least 20 iterations, half the horizon (P = 0.060).

The draft's cascade threshold (2 evictions in total) holds in 99.9% of runs at this scale and is not
informative.

**Method** (as in case study B, `docs/notes/case-study-fq.md`):
1. **Histories.** Monitors record every iteration's arrival draw (`llm_history.buffy`,
   `llm_histories.py`), 1,000,000 runs.
2. **Learning** (`learn_llm.py`). Candidates are bounded-LTL formulas over the per-iteration shape:
   none, any, long prompt, long output, both long, both short, short prompt. They include runs of k
   iterations in a window and their negations, counts of long-prompt / long-output draws by an
   iteration ("at most / at least c"), and conjunctions of two. Each is scored on a training and a
   held-out half.
3. **Certification** with `--condition-on` (`certify_llm.py`): exact P(A), and P(Q | A) from 100,000
   conditioned runs. The first two conditions of each table are cross-checked against rejection
   from 1,000,000 runs; they agree.

## Results

Iterations are counted from 0; the tracked request arrives in iteration 5, so "the first five
iterations" are the ones before it.

**Eviction** (base 0.055; `results/certify_evicted.log`):

| condition A on the arrivals | P(A), exact | P(Q \| A) | rejection check |
|---|---|---|---|
| two long-prompt, long-output requests in a row, starting in iterations 2–4, and at most 3 long outputs in iterations 0–4 | 0.087 | 0.225 | 0.223 |
| at least 3 long outputs in iterations 0–4, at most 1 in iterations 0–2 | 0.083 | 0.207 | 0.206 |
| two long/long requests in a row before it, and no long output in iterations 2–4 | 0.0084 | 0.337 | — |
| **no long-prompt, long-output request before it** | **0.280** | **0** (< 3.7·10⁻⁵) | — |
| no long-output request in iterations 0–2 | 0.166 | 0 (< 3.7·10⁻⁵) | — |

Eviction needs a long/long request admitted *before* the tracked one: under last-in-first-out
eviction, that request's memory fills the pool and the tracked request, admitted later, is the one
evicted. This is the privileged model's finding ("a long request before the victim"), now confirmed
at realistic scale with the victim competing normally. It holds as a mild *protective* condition: in
28% of runs no such request comes first, and eviction never happens. Dangerous conditions, though,
only reach P ≈ 0.2–0.34. The rest depends on details of the mix that short formulas do not capture.

**Long wait** (base 0.060; `results/certify_wait20.log`):

| condition A | P(A), exact | P(Q \| A) | rejection check |
|---|---|---|---|
| at least 4 long-output requests in iterations 0–4, and at least 2 long prompts in iterations 0–2 | 0.063 | **0.635** | 0.634 |
| a long-output request in every one of iterations 0–4 | 0.018 | **1** (18,206 of 18,206) | 1 |
| **at most one long-output request in iterations 0–2** | **0.575** | **0** (< 3.7·10⁻⁵) | — |
| no long-output request in iterations 0–1 | 0.303 | 0 (< 3.7·10⁻⁵) | — |

The tracked request waits half the horizon exactly when long-output requests occupy the batch slots
ahead of it. Each holds a slot for 16 decode iterations, and first-come-first-served admission makes
the newcomer wait for all of them. Two early long outputs are needed: with at most one in the first
three iterations (58% of runs) it never waits 20. Five in a row before it make the wait certain.

**Certain and necessary, statistically, not proven.** "A long output in each of iterations 0–4" gave
the long wait in all 18,206 rejection runs and all 100,000 conditioned runs, so P(wait | A) > 0.99996
(95%). "At most one long output in iterations 0–2" gave no long wait in 100,000 conditioned runs,
so P < 3.7·10⁻⁵. We also asked Z3, on Buffy's SMT-LIB unrolling of the full-scale model (40
iterations, 8 records), whether either holds for *every* workload. Both queries timed out after 50
minutes (`results/proofs.log`). Unlike case study B's 14-step model, this one is too large for the
solver at this horizon, so the claims stay statistical.

**The remedy.** Shortest-job-first admission (`ADM_POLICY = 1`) cuts the long wait from 0.060 to
0.0019, and defuses the dangerous conditions: P(wait ≥ 20 | five long outputs first) falls from 1 to
0.0016, and P(wait | the mild condition) from 0.64 to 0.007. Protecting the tracked request from
eviction (`POLICY = 1`) removes eviction and leaves the wait unchanged.

**What changed from the draft.** The draft could not find a mild condition that makes a bad event
clearly probable, at a toy, exactly checkable scale. At realistic scale, with learned conditions:
- the long wait has a mild dangerous condition (6% of runs, P = 0.64), a certain one (1.8%, P = 1)
  and a mild ruling-out condition (58%, P = 0);
- eviction has a mild ruling-out condition (28%) that confirms the earlier timing story, but no
  dangerous condition above P ≈ 0.34.

**Reproduce.** `experiments/buffy_llm/run_study.sh`.

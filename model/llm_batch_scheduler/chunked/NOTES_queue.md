# Notes — queue-based chunked scheduler (v2, `scheduler_queue.pm`)

The realistic redesign from the design review: **no scheduler privilege for the
victim** (Q3), **decoupled prompt/output length** (Q6), and a **real waiting queue with
evict-to-queue** (Q8). Unified request records (`empty|waiting|running`); the victim is
an ordinary record that competes for `N_SLOTS` batch slots and is admitted/evicted by
the same FCFS/LIFO rules as background. See header of `scheduler_queue.pm`.

Still exact-checkable at the exploration scale (~182k states); intended for SMC at
realistic scale (see `../PARAMETERS.md`).

## What the redesign revealed (important)

**v1's "victim gets preempted" finding was partly an artifact** of the privileged
setup (dedicated slot + 3 concurrent requests). With a realistic slot limit
(`N_SLOTS=2`) and the victim competing, the small victim co-runs with at most one
background request, so `victim_blk (≤2 while decoding) + bg_blk (≤6) ≤ KV_CAP=8` — the
victim can **never** push the pool over the cap, so **P(victim preempted) = 0**. The
victim's real harm is **queueing delay**: waiting for a slot behind long requests. (This
is exactly the FQ-CoDel-standard critique paying off.)

## The robust finding — queueing delay, timing not volume

`POLICY=fcfs, p_arr=0.5, p_lp=0.4, p_ol=0.4`. Bad event = victim TBT stall
(`v_maxgap ≥ SLO_TBT`), baseline **0.108**:

| condition C on the request pattern | P(stall \| C) | P(C) | vs baseline |
|---|---|---|---|
| a long-prompt bg arrived **before** the victim, none after | **0.221** | 0.19 | **2.0×** |
| the same longs arrived **after** the victim, none before | **0.018** | 0.34 | 0.17× (protective) |
| ≥2 long requests arrived (volume) | 0.163 | 0.50 | 1.5× |
| long in **both** prompt & output (`n_lp≥2 & n_lo≥2`) | **0.236** | 0.24 | **2.2×** |

- **Timing, not volume:** a long request arriving *before* the victim holds a slot long
  enough that the victim queues behind it and its first/next token is delayed. The same
  longs arriving *after* the victim are *protective* (it already holds/obtains a slot).
- **Decoupling pays off (Q6):** requests long in *both* prompt and output hold a slot the
  longest and hurt most — a correlation effect v1 (bundled lengths) could not express.
- Same "mild but informative, invisible per component" character as FQ-CoDel/incast, now
  via a queueing mechanism rather than eviction.

## Candidate paper assumption — a parameter BOX (Flavor B, monotone-certified)

Assumptions must be *ranges* over input parameters, not points (incast standard).
Sweeping `P(victim stall)` over `T_V × p_arr × p_lp × p_ol` (exact, `sweep_queue.sh`
/ experiment mode) gives clean monotonicity:

| input parameter | monotone in `P(stall)`? |
|---|---|
| `p_lp` (long-**prompt** fraction) | **yes, ↑** (0/72 grid violations) |
| `p_ol` (long-**output** fraction) | **yes, ↑** (0/48) |
| `p_arr` (arrival load) | yes, ↑ (1/64) |
| `T_V` (victim arrival time) | **no** — finite-horizon artifact (earlier arrival = more exposure); kept OUT of the box as a fixed input assumption |

Because `P(stall)` is monotone ↑ in `p_lp, p_ol, p_arr`, a box over them is certified at
its **lower corner**. Candidate assumption:

> **A = { p_arr ∈ [0.6,0.8], p_lp ∈ [0.6,0.8], p_ol = 0.6 }** (a long-heavy mix at
> moderate-to-high load). Across all of A (and all `T_V`), `P(victim stall) ≥ 0.19`
> (worst corner), typically ~0.36–0.48.
>
> **Contrast** (short-mix): `{ p_lp ≤ 0.4, p_ol = 0.3 }` gives `P ≤ 0.12` even at higher load.

**The non-obvious point — composition beats load:**

| regime | `P(stall)` |
|---|---|
| moderate load, long-heavy (`p_arr=0.6, p_lp=0.8, p_ol=0.6`) | **0.359** |
| high load, short mix (`p_arr=0.8, p_lp=0.2, p_ol=0.3`) | **0.101** |

A moderately-loaded worker with a long-heavy request mix starves the interactive request
**3.5× more** than a heavily-loaded worker with short requests. Per-range sensitivity
(anchor `T_V=3, p_arr=0.6, p_lp=0.4, p_ol=0.3` → 0.114): varying `p_lp` 0.2→0.8 gives
×3.6; `p_arr` 0.4→0.8 gives ×2.9; `p_ol` gives ×1.8/step. The **long-request fraction,
not the arrival rate**, is the dominant driver — the "shape not volume" theme, now as a
monotone parameter box. This is a naive-capacity-planning trap: keeping *load* moderate is
not enough if the *mix* is long-heavy.

(The earlier Flavor-A "long arrived before the victim" conditional is a real
mechanism illustration but does not become a clean monotone box, because the timing
handle `T_V` is non-monotone under a finite horizon. The composition box above is the
stronger, paper-ready form.)

## THE non-obvious finding — long prompts are irrelevant; long OUTPUTS starve interactive requests

An expert rightly finds "long-heavy mix hurts interactive latency" *obvious* (it is the
founding motivation of the whole subfield). Searching four candidate non-obvious
directions (below) surfaced one sharp, counterintuitive, and actionable result — after
fixing a realism bug in the prefill chunk size.

**The realism fix.** With `CHUNK_BLK=1` a long prompt (3 blocks) takes 3 iterations to
prefill, so prompt length inflates slot-occupancy time. Realistically a chunk is ~512
tokens ≫ a prompt, so **a prompt prefills in ~1 iteration** (`CHUNK_BLK ≥ LP`). Under that
realistic setting:

`P(victim stall)` over a `p_lp × p_ol` grid (realistic prefill, `N_SLOTS=1`, `p_arr=0.8`):

|          | p_ol=0.0 | p_ol=0.5 | p_ol=1.0 |
|---|---|---|---|
| **p_lp=0.0** | 0.640 | 0.864 | 0.960 |
| **p_lp=0.5** | 0.640 | 0.864 | 0.960 |
| **p_lp=1.0** | 0.640 | 0.864 | 0.960 |

**`P(interactive stall)` is EXACTLY invariant to the long-*prompt* fraction (spread 0.000)
and monotone in the long-*output* fraction.** (Holds at `N_SLOTS=2` too: `p_lp` 0.2→0.8 gives
0.017→0.017; `p_ol` 0.2→0.8 gives 0.017→0.138.)

**Why (mechanism):** chunked prefill collapses any prompt into ~1 iteration, so prompt
length no longer affects how long a request holds a slot — only its *output* length does
(one decode iteration per output block). The interactive request's queueing delay is set
purely by how long incumbents hold slots = their **output** length.

**Paper-ready assumption (Flavor B, monotone box over the OUTPUT-length parameter):**
> Under realistic chunked prefill, `P(interactive stall)` is **invariant to the long-prompt
> fraction `p_lp ∈ [0,1]`** and monotone ↑ in the long-output fraction. For `p_ol ≥ 0.5`
> (at this load) `P(stall) ≥ 0.86`, *regardless of prompt lengths*.

**Why it's non-obvious & actionable:**
- Contradicts the standard worry that **long-context (long-prompt) requests** threaten
  interactive latency — chunked prefill *fully neutralizes* prompt length for this bad event.
- The residual danger is **output length** — which is exactly the quantity the scheduler
  **cannot observe at admission** (see the primer's known/unknown asymmetry). So
  prompt-length-based admission / routing / prioritization (all using the *visible* feature)
  is useless for protecting interactive latency; you need *output* prediction.
- It is a "the SOTA mitigation moved the bottleneck" result: pre-chunking, long prompts
  hogged iterations (the classic stall); post-chunking, prompt length is irrelevant and
  output-driven slot-occupancy is the sole driver.

### The four explored directions (honest outcomes)

1. **Sneaky-cheap / SJF-by-prompt backfire — refuted (for the interactive victim).** With a
   forced queue, SJF-by-prompt *helps* the short victim (0.857→0.380), as SJF should; it does
   not backfire on it. (A backfire would hit a *long-prompt* victim / system metric.)
2. **Adding capacity backfires — partial / a real tradeoff.** More `KV_CAP` monotonically
   *reduces* stalls; but at *fixed* KV, raising batch width `N_SLOTS` sharply *increases*
   preemption (e.g. `KV_CAP=8`: `N_SLOTS` 1→2→3 gives P(preempt) 0→0.11→0.27). Adding batch
   slots trades queueing-stall for preemption/recompute thrash unless KV scales too.
3. **Priority blind spot — confirmed.** In the queueing regime (`N_SLOTS=2`), priority-as-
   eviction-policy gives *identical* `P(stall)` (0.335) to FCFS: protecting the victim from
   *eviction* does nothing for its *queueing* delay. "Priority tiers" don't help interactive
   latency when the bottleneck is admission, not eviction.
4. **Correlation / structure beats averages — refuted.** At equal marginals, prompt↔output
   correlation barely moves `P(stall)` (independent 0.231, positive 0.236, negative 0.198);
   the small effect is in the *obvious* direction (long-in-both marginally worst).

The strongest, genuinely non-obvious result is the **prompt-invariance / output-dominance**
finding above; #2 and #3 are secondary, mild, real effects.

## Caveats / next steps

- At this tiny scale, `preempts` never reaches 2 (only 2 slots → no in-iteration cascade)
  and victim preemption is 0; preemption bad events need the larger validation config
  (more slots, bigger KV) — where they should re-emerge. Run under SMC (`../PARAMETERS.md`).
- Victim arrival `T_V=3` is still fixed (a legitimate input assumption, not a privilege);
  sweep it to confirm robustness.
- TODO: a `scheduler_queue.props` + runner mirroring `scheduler.props`/`run_case_study.sh`
  for one-command reproduction; a tunable prompt↔output correlation (condition `p_ol` on
  prompt class); the larger SMC validation config + a slot generator (PRISM has no arrays).
- `scheduler.pm` (v1, exact, privileged victim) is kept as the initial-exploration
  artifact; `scheduler_queue.pm` (v2) is the more faithful model going forward.

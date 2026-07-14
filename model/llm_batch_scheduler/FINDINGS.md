# Findings — LLM batch-scheduler case study (paper-ready summary)

Consolidated results for writing. Details, code, and reproduction live in `chunked/`
(`NOTES.md`, `REGIONS.md`, `VALIDATION.md`), `PARAMETERS.md`, and `SCHEDULING_PRIMER.md`.

## One paragraph

The contention point is the **batch scheduler of a GPU worker** running chunked-prefill
continuous batching (the vLLM-V1 default). Requests compete for a fixed number of batch
slots (`N_SLOTS`) and a shared KV pool; we track one **interactive request** (short
prompt, modest output) with no scheduler privilege and ask how often its inter-token
latency stalls. **Main finding:** at realistic magnitudes the stall risk is governed by
the fraction of **long-output** requests and by **provisioning** (`N_SLOTS`) — and *not*
by prompt length. A long-output request holds a slot for one iteration per output token
(hundreds), so it starves the interactive request; a long-context (long-*prompt*) request,
under chunked prefill, holds a slot for only a few chunk-iterations and barely matters.
Crucially, **output length is the one feature the scheduler cannot observe at admission**,
so prompt-length-based admission/routing/prioritization targets the wrong variable.
Framed probabilistically, a 100%/reachability method can only certify the obvious
provisioning extremes (badly under- or over-provisioned); the realistic operating regime
is a **coin-flip region** whose outcome is set by the unobservable output-length mix.

## Model & bad event

- One DTMC step = one scheduler iteration (forward pass). Requests are **records**, each
  `empty | waiting | running`. Arrival → waiting (the queue) → admitted (FCFS or SJF) →
  running (prefill `CHUNK` units/iter, then decode 1 token/iter) → done; KV exhaustion
  evicts running → waiting (LIFO, or protect the tracked request under a priority policy).
  The tracked request (record 0) uses the same rules as everyone; only its *input* (short
  shape, fixed arrival) is its own — the assumption under study, à la FQ-CoDel's `q5`.
- **Bad event:** `v_maxgap ≥ SLO_TBT` — the tracked request's worst inter-token gap reaches
  the TBT SLO (an interactive-latency stall).
- Input parameters (the "condition" ranges over these): `p_arr`/λ (load), `p_lp` (fraction
  long-prompt), `p_ol` (fraction long-output), and config knobs `N_SLOTS`, `KV_CAP`, chunk.

## Realistic parameters & the ratio that matters

Absolute magnitudes are scaled for tractability; the **ratios** are realistic (full table
in `PARAMETERS.md`). Realistic oracle config (`chunked/sched_sim.py`, token units):

| quantity | value | real system |
|---|---|---|
| prefill chunk | 512 tokens | 512 (Sarathi-Serve / vLLM) |
| prompt short / long | 16 / 2048 tokens (long = 4 prefill chunks) | ~16 / 10²–10³ |
| output short / long | 8 / 256 tokens (long = 256 decode iters) | ~8 / 40–500 |
| **decode-iters : prefill-iters (long class)** | **256 : 4 = 64 : 1** | ~10–64 : 1 |
| batch width `N_SLOTS` | swept; knee ≈ 20–24 for this load | `max_num_seqs` ≈ 256 |
| load | Poisson λ = 0.3 req/iter | tuned near saturation |

The one ratio the finding depends on — **decode iterations ≫ prefill iterations** — is
realistic (a request spends far longer decoding than prefilling).

## Finding 1 — output length dominates; prompt length is near-irrelevant (and is the visible one)

Per-request effect on the tracked request (realistic 64:1, `N_SLOTS=22`); a fraction `f`
of background is "long" in **one** dimension only:

| f | long-**prompt** (2048-tok) only | long-**output** (256-tok) only |
|---|---|---|
| 0.3 | **0.000** | 0.332 |
| 0.5 | **0.000** | 0.967 |

A long-context prompt request causes ~zero stall; long-output requests drive it to
near-certain. **Mechanism:** chunked prefill spreads a prompt over `⌈prompt/512⌉` ≈ a few
iterations, so prompt length barely changes how long a request holds a slot; output length
sets it (one decode iteration per token). Output length is **unobservable at admission**,
so a prompt-based scheduler cannot target the real driver.

(At a *toy* output length `LO=32` the ratio is only 8:1 and prompt appears to matter ~2–4×;
that is a small-scale artifact. The invariance is exact only when a prompt fits in one
chunk. See `chunked/NOTES.md` and `chunked/VALIDATION.md`.)

## Finding 2 — sharp in provisioning, gradual in the output mix, flat in prompt mix

`P(stall)` over the input/config axes (realistic oracle):

```
  N_SLOTS (p_lp=p_ol=0.3):  12→0.98  16→0.84  20→0.51  22→0.34  24→0.20  28→0.05  32→0.008
  p_ol   (N=22, p_lp=0.3):  0.22→0.06  0.26→0.17  0.30→0.34  0.34→0.54  0.38→0.71   (gradual)
  p_lp   (N=22, p_ol=0.3):  0.1→0.34   0.5→0.34   0.9→0.35                          (flat)
```

So the genuinely-uncertain region is a thin band at the **provisioning knee** (`N_SLOTS`≈22)
and along the **output-fraction** axis; prompt fraction does not move it.

## Finding 3 — regions: obvious (provable) vs. mild (probabilistic)

**Obvious / provable — certain stall, `P(stall) = 1` (a verification/reachability method finds these):**
- **Provable by exact model checking** (small model, all corners = 1.000):
  `A_E ≡ (N_SLOTS = 1) ∧ (p_arr = 1) ∧ (p_lp ∈ [0,1]) ∧ (p_ol ∈ [0,1]) ∧ (T_V ∈ [2,5])` → **`P(stall) = 1`.**
  A **saturated, under-provisioned** worker (one slot, always occupied) stalls the interactive request
  with certainty — *regardless of the request mix* (`p_lp, p_ol` range over everything). The workload
  composition that decides the mild region becomes irrelevant here.
- **Realistic-scale analog** (oracle; `P = 1.0000`, no counterexample in 10⁴ samples, over a
  multi-parameter box): `A_E' ≡ (N_SLOTS ∈ [8,12]) ∧ (λ ∈ [0.5,0.7]) ∧ (p_ol ∈ [0.5,0.7])` →
  **`P(stall) = 1.000`** throughout — under-provisioned ∧ high-load ∧ output-heavy.
- **Never stalls** (the opposite obvious extreme): `A_over ≡ (N_SLOTS ≥ 28)` → `P ≤ 0.05`;
  `A_light ≡ (p_ol ≤ 0.22)` → `P ≤ 0.06`.

**Mild / non-obvious (probabilistic — every point a coin-flip; monotone, so corners certify):**
- **Workload box** (ranges the *invisible* long-output fraction):
  `A_w ≡ (N_SLOTS = 22) ∧ (p_ol ∈ [0.26, 0.34]) ∧ (p_lp ∈ [0,1])` → **`P(stall) ∈ [0.17, 0.54]`**
- **Config box** (ranges the provisioning knob operators can't set well):
  `A_cfg ≡ (N_SLOTS ∈ [20, 24]) ∧ (p_ol = 0.3) ∧ (p_lp ∈ [0,1])` → **`P(stall) ∈ [0.19, 0.56]`**

In both, prompt fraction `p_lp` is free (≤0.05 swing); the outcome is set by provisioning
and the long-output fraction.

**Methodological point (the paper's thesis).** A certainty method can only certify the
extremes where `P(stall)` is exactly 0 or 1 — the *saturated, under-provisioned* box `A_E`
(certain stall) and the *over-provisioned* box `A_over` (never). Both are obvious, and in
`A_E` the workload composition is irrelevant. The realistic operating regime (batch width at
the knee, moderate partly-invisible output mix) has no certain answer, and is exactly where a
quantified `P(stall | A) ∈ [0.17, 0.56]` is the actionable one — and it points at the
*output-length distribution*, not prompt length, as the lever.

## Validation

- **Independent oracle vs. PRISM** at the small (exact-checkable) config — agrees within CI
  at every corner: `(N=3,p_lp=.2,p_ol=.2)` 0.183 vs 0.181; `(N=3,.4,.4)` 0.564 vs 0.568;
  `N=2/3/4 (.3,.3)` 0.800/0.375/0.086 vs 0.802/0.372/0.085.
- **Cross-scale consistency**: the same sharp-provisioning / output-dominance structure
  appears in the small PRISM model (`chunked/scheduler.pm`, exact), the mid model
  (`chunked/scheduler_mc.pm`, SMC), and the realistic oracle. Realistic magnitudes are
  oracle-only (PRISM cannot reach them) — the same division of labor as incast's
  `example3` (numbers from `incast_sim.py`, PRISM cross-checks the mechanism).

## Reproduce

```bash
source ~/buffy-prism-tools/env.sh
cd model/llm_batch_scheduler/chunked
./run_regions.sh          # small PRISM/SMC regions (exact-scale)
./run_regions_oracle.sh   # realistic-magnitude regions (oracle)
python3 sched_sim.py --help   # the oracle; --lam for Poisson load, token-scale sizes
```

## Honest caveats

- KV-cache preemption is modeled but the realistic runs set `KV_CAP` generous to isolate
  the queueing stall; a KV-tight regime (preemption cascades) is a separate sweep.
- Only the inter-token stall (TBT) is scored; a TTFT-SLO label (admission latency) is not
  yet added.
- `N_SLOTS` knee here is ~22 (load-dependent); pushing to vLLM's default `max_num_seqs=256`
  just needs raising λ so the knee lands there — same structure, larger run.
- Victim arrival `T_V` is fixed (an input assumption), not random.

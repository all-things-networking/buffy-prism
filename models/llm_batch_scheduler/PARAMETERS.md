# Parameters: model values vs. real systems

The model uses deliberately small magnitudes so the state space stays exactly
checkable (the "exploration" config). The concern (rightly) is that toy magnitudes
could surface *artificial* pathologies. This table makes the gap explicit, separates
the **magnitudes** (toy) from the **ratios** (what we claim is faithful), and proposes a
larger **validation** config to re-run once a candidate assumption is found — to confirm
it is not an artifact of scale.

## Absolute parameters

| parameter | real systems (source) | exploration (current) | validation (proposed) |
|---|---|---|---|
| concurrent seqs (batch width, `max_num_seqs`) | **256** default (vLLM) | **3** (victim + 2 bg) | 16–32 |
| KV pool size | **~500–5,000** 16-tok blocks (≈ leftover HBM after weights; 13B on 40–80 GB) [PagedAttention] | **8** blocks | 256–512 |
| per-iteration prefill budget (`max_num_batched_tokens`) | **512** (chunked/strict) – **2,048** (throughput) tokens ≈ 32–128 blocks [vLLM; Sarathi-Serve] | **1** block (16 tok) | 8–32 blocks |
| prompt length | heavy-tailed; median ~10²–10³ tok, P99 ~4× median [Azure trace; BurstGPT] | short **1** blk (16 tok), long **3** blk (48 tok) | short ~4 blk, long ~32–64 blk |
| output length | high variance; conversation median ~40 tok / P99 ~500; code median ~8 [Splitwise; BurstGPT] | short **2** blk, long **3** blk | short ~2 blk, long ~16–32 blk |
| request lifetime (iterations) | = output length → 10¹–10³ iters | horizon **T=10** | T = 50–100 |
| block size | **16 tokens** (PagedAttention default) | 16 tokens (implicit) | 16 tokens |

**None of the magnitudes are realistic** — they are 1–3 orders of magnitude small. This is
a mechanism model, in the same spirit as FQ-CoDel (5 queues, size 8) and incast (BUF=32).

## Ratios — what we actually claim is faithful

The pathology depends on these dimensionless ratios, not on absolute sizes:

| ratio | why it matters | real (approx) | exploration | validation |
|---|---|---|---|---|
| **KV oversubscription** = peak demand / pool | if <1, preemption never happens; real serving runs oversubscribed at the tail (that's why preemption exists) | ≳1 at the tail | 3×6 / 8 ≈ **2.3×** | tune to ~1.5–2.5× |
| **long : short prompt** | sets how badly one big prefill dents the shared pool | ~4× (median→P99), often larger | 3 / 1 = **3×** | ~8–16× |
| **prefill chunk : long prompt** | how many iterations a long prompt is spread over | 512/2000 ≈ **0.25** | 1 / 3 ≈ **0.33** | ~0.1–0.25 |
| **arrival load : batch width** | whether the queue/pool is pressured | tuned near saturation | swept via `p_arr` | swept |

The exploration ratios are in the right ballpark except **long:short**, which is compressed
(3× vs. real ≳8×) — the validation config widens it. The **oversubscription** ratio (the
one that actually drives preemption) is realistic.

## Plan

1. **Explore** on the small exact config to *find* candidate assumptions (the timing/LIFO
   finding). Exact model checking, no statistical noise.
2. **Validate** each surviving assumption on the larger config above. That model will be
   too big for exact checking → statistical model checking (SMC), as in the FQ-CoDel/incast
   studies. Confirming the effect persists at realistic ratios is what rules out an artifact.

> Note: scaling `max_num_seqs` beyond 2–3 slots requires generating the PRISM slots
> programmatically (PRISM has no arrays/loops) — via module renaming or a small generator
> script. That generator is part of the validation-config work.

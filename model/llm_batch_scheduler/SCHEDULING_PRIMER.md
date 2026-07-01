# How Scheduling Works in Modern LLM Serving — A Primer

*A ground-up walkthrough for readers who don't work in this space. Written to
motivate the third case study (a probabilistic model of the batch scheduler in a
GPU worker). Every load-bearing claim is cited; see [References](#references).*

---

## 0. The one-sentence version

An LLM inference server is a **queueing system with two unusual twists**: (1) each
request is not one unit of work but a *long sequence* of tiny steps whose length is
**unknown in advance**, and (2) the requests all **share a fixed pool of GPU memory**
(the "KV cache") that fills up as they run. The **scheduler** decides, on every single
step, which requests share the GPU and which wait — and almost all the interesting
failure modes (latency spikes, stalls, evictions) come from how it resolves
**contention** for compute and for that shared memory pool.

If you know networking: it is almost exactly a **shared-buffer switch with
round-robin service**, except the "packets" are token-generation steps and the "buffer"
is GPU KV-cache memory.

---

## 1. What one LLM request actually looks like

When you send a prompt to an LLM, the server does the work in **two phases** with
completely different performance characteristics. This split is the single most
important thing to understand.

### Phase 1 — Prefill (processing your prompt)

The model reads your entire prompt at once and produces the **first** output token.
Because it processes all prompt tokens together, this is one big matrix–matrix
multiply. It is **compute-bound**: the GPU's arithmetic units are the bottleneck, and
the cost scales with prompt length. A 2,000-token prompt does ~2,000× the prefill work
of a 1-token prompt. [Orca OSDI'22; Sarathi-Serve OSDI'24]

### Phase 2 — Decode (generating the answer, one token at a time)

After the first token, the model generates the rest **one token per step**,
autoregressively — each new token depends on all previous ones. Each decode step is a
matrix–*vector* multiply (one token wide). It is **memory-bandwidth-bound**: the
bottleneck is *reading the model's weights and the stored context out of GPU memory*,
not doing arithmetic. The GPU is mostly idle waiting for memory. [TensorRT-LLM docs;
"Roofline" survey arXiv:2402.16363]

> **Worked example.** A request with a 500-token prompt and a 200-token answer does:
> - **1 prefill step** that crunches 500 tokens (expensive, compute-bound), then
> - **199 decode steps**, each generating 1 token (cheap individually, but memory-bound
>   and there are many of them).
>
> The prefill is a short, heavy burst; the decode is a long, thin tail. **A server is
> almost always juggling a few requests in their heavy prefill burst against many more
> in their long decode tail.** That tension is where scheduling lives.

### Why decode is the expensive part overall — the KV cache

To generate token #200 the model needs the "keys and values" (an internal
representation) of all 199 previous tokens. Rather than recompute them every step, the
server **caches** them in GPU memory. This is the **KV cache**, and it is the resource
everything fights over.

- The KV cache **grows by one token's worth of data on every decode step**, for every
  active request.
- It is **big**. For a 13-billion-parameter model, one token of KV cache is ~800 KB, so
  a single 2,048-token request can hold **~1.6 GB** of KV cache. On a 40 GB A100, model
  weights take ~65% of memory and KV cache takes most of the rest (~30%) — which is what
  caps how many requests can run at once. [PagedAttention SOSP'23]

**Key takeaway for scheduling:** every running request is *slowly consuming a shared,
finite memory pool*, and you don't know when it will stop (you don't know how long its
answer will be until it emits a stop token).

---

## 2. Batching: why you can't serve requests one at a time

A GPU running one decode step for one request is almost entirely idle — it reads the
whole model from memory to produce a single token. The fix is **batching**: run the
same decode step for *many* requests at once, so you pay the memory read once and
amortize it across the batch. Throughput can rise by more than an order of magnitude.

### Naive approach: static batching (the strawman)

Collect N requests, run them as a fixed batch until **all** are done, then take the next
N. The problem: request lengths vary wildly. If 7 requests finish in 20 tokens and 1
keeps going for 500, the 7 finished slots sit **idle** for 480 steps waiting for the
straggler. Under high length-variance this wastes most of the GPU. [Anyscale 2023]

```
Static batching (fixed batch of 4). '=' generating, '.' idle-but-locked, '|' done.
  req A  ====|. . . . . . . . . . . . . . .        <- finished early, slot wasted
  req B  ====|. . . . . . . . . . . . . . .
  req C  ==========================|. . . .
  req D  =======================================|   <- everyone waits for D
         ^ new requests can't start until the WHOLE batch is done
```

### The real mechanism: continuous (iteration-level) batching

Modern servers schedule at the granularity of **one iteration = one decode step across
the batch**, not one whole request. This is **iteration-level scheduling**, introduced by
**Orca (OSDI 2022)** and marketed by NVIDIA as "in-flight batching." After every single
step the scheduler regains control: it **evicts requests that just finished** and
**admits waiting requests into the freed slots**, then runs the next step. No slot is
ever stuck waiting for a straggler. [Orca OSDI'22; Anyscale 2023]

```
Continuous batching — the batch is recomposed EVERY step.
  step:   1 2 3 4 5 6 7 8 9 ...
  slot 1  A A A A|E E E E E ...   A finishes at step 4, request E starts at step 5
  slot 2  B B B B B B|F F F ...   B finishes, F slides in immediately
  slot 3  C C C C C C C C C ...   long request keeps running, no one waits on it
  slot 4  D D|G G G G G|H H ...   short requests churn through quickly
         ^ the GPU is kept full; finished slots are refilled at once
```

This is the foundational trick. Reported gains: up to **36.9×** throughput vs. a
strong baseline (FasterTransformer, GPT-3 175B) [Orca]; up to **23×** vs. static
batching in a public benchmark [Anyscale].

> One subtlety, "selective batching" [Orca]: the cheap position-agnostic layers of the
> model are batched across all requests, but the *attention* step is computed per
> request (because each request is at a different point in its sequence). You don't need
> this detail for the scheduling story — just know that "a batch" is real and effective.

---

## 3. The two things requests contend for

With continuous batching in place, on each iteration the scheduler faces two hard
limits:

### (a) A per-iteration compute/token budget

Each iteration can only process so many tokens of work before it becomes too slow.
Servers expose this as a **token budget per iteration** (in vLLM, `max_num_batched_tokens`;
also a cap on concurrent sequences, `max_num_seqs`). A batch of 30 decodes is 30 tokens
of work; a single 2,000-token prefill is 2,000 tokens of work and blows the budget by
itself. [vLLM docs]

### (b) The shared KV-cache memory pool

There are a fixed number of KV-cache "blocks." Every running request holds some, and
the count **grows every step**. When a new request's prefill needs blocks, or a running
request needs one more block to continue, and none are free — the server is **out of
memory** and must do something drastic (Section 5). [PagedAttention SOSP'23]

**PagedAttention** (vLLM, SOSP 2023 best paper) is how modern servers manage (b)
efficiently. Older systems pre-reserved a contiguous chunk of memory for each request's
*maximum possible* length, wasting 60–80% of it. PagedAttention instead chops KV cache
into fixed **16-token blocks** stored anywhere in memory, tracked by a per-request
"block table" (exactly like an operating system paging virtual memory to physical
frames). Waste drops below 4%, so **2–4× more requests** fit at once. [PagedAttention]

> This is the direct analog of a **shared packet buffer** in a network switch: a common
> pool that all flows draw from, managed in fixed-size blocks, where the danger is
> *aggregate* occupancy, not any single flow's behavior.

---

## 4. The core tension: prefill vs. decode interference

Here is the pathology that most modern scheduling work is about.

Prefill is a big compute burst; decode is a stream of cheap steps. **What happens when a
long prompt arrives while other requests are happily decoding?**

If the scheduler eagerly runs the newcomer's prefill (the default, FCFS behavior), that
one prefill can **consume the entire iteration's compute budget**. For that iteration —
and, for a very long prompt, for *several seconds* — **none of the decoding requests
produce a token**. Every user mid-answer sees their output **freeze**. This is a
**generation stall**, and it is a **head-of-line blocking** problem: one heavy item at
the front stalls everyone behind it. [Sarathi-Serve OSDI'24 §1, §3.2]

> **Worked example.** Ten users are streaming answers (decoding, one token every ~30 ms
> — smooth). An eleventh user submits a 4,000-token document to summarize. Under naive
> FCFS the server spends the next several iterations doing only that prefill. The ten
> streaming users' text **stops** for that whole window. Measured impact: naively mixing
> a full prefill into a decode batch inflated the time-between-tokens by up to **28.3×**
> vs. a decode-only batch. [Sarathi-Serve §4.2]

### The fix in today's default stack: chunked prefill

**Sarathi-Serve (OSDI 2024)** splits a long prompt into **chunks** and, on each
iteration, admits only enough prefill tokens to *fill the leftover budget* alongside the
running decodes. The decodes keep making progress every step; the big prefill is spread
over several iterations. Decodes "never experience a generation stall due to a co-running
prefill chunk." This is now **on by default in vLLM's V1 engine** (since ~v0.8.0,
March 2025). Reported serving-capacity gains: **2.6×–5.6×**. [Sarathi-Serve;
vLLM V1 docs]

```
Naive FCFS prefill (stall):            Chunked prefill (stall-free):
  iter 1: [PPPP PPPP PPPP]  <- only      iter 1: [PP dddddddddd]  decodes keep
  iter 2: [PPPP PPPP PPPP]     prefill,   iter 2: [PP dddddddddd]  flowing while
  iter 3: [PPPP PPPP PPPP]     decodes    iter 3: [PP dddddddddd]  the prefill is
  iter 4: [dddd dddd dddd]     frozen     iter 4: [PP dddddddddd]  fed in small
          ^ users' text froze                     ^ big prompt spread over iters
```

> **Why this matters for our case study:** chunked prefill *solves the stall problem* but
> does **nothing** about the shared KV-memory pool. A bad event that survives the
> state-of-the-art mitigation — e.g., a request getting **evicted** because aggregate KV
> filled up — is a much stronger result than "naive FCFS is bad."

### Going further: prefill/decode disaggregation

Because the two phases stress *different* hardware resources (prefill = compute, decode =
memory bandwidth), some systems run them on **separate GPU pools**: **DistServe
(OSDI'24)** and **Splitwise (ISCA'24)**. This removes interference entirely at the cost of
shipping the KV cache between pools. Powerful, but a bigger architecture; we model the
single-worker case, which is still the common deployment. [DistServe; Splitwise]

---

## 5. What happens when the KV cache fills up: preemption

Because answer lengths are unknown, the server can admit "too many" requests and later
discover it has no free KV blocks for them all. It must then **preempt** a running
request — evict its KV cache to free memory — and resume it later. [PagedAttention §4.5;
vLLM docs]

Two ways to recover the evicted request:
- **Recomputation**: throw away its KV cache and redo it as a fresh prefill on resume.
  Cost grows ~*quadratically* with the request's length (O(s²)).
- **Swapping**: copy its KV cache to CPU RAM and back. Cost grows ~*linearly* (O(s)).

Recompute wins for short requests, swap for long ones (crossover ~4,000 tokens). vLLM's
V1 engine defaults to **recompute**. And critically, **which request is evicted** depends
on the scheduling policy (Section 6): under FCFS, vLLM evicts the **most recently
admitted** running request (LIFO). [vLLM V1 scheduler source]

> **The nasty feedback loop.** A preempted long request, on resume, re-runs its (long)
> prefill, which *re-pressures* the very memory pool that was already tight — potentially
> forcing *another* preemption. Under load this can **cascade**. This is a natural "bad
> event" to reason about probabilistically. [FastServe arXiv:2305.05920; vLLM issues]

---

## 6. Scheduling policies: what order do requests run in?

Everything above is *mechanism*. The **policy** is: given the waiting queue and the
running batch, who gets admitted, and who gets evicted under pressure? Here is the
honest state of the art.

### FCFS — first-come-first-served — is the production default

- **vLLM**: default `scheduling-policy` is **`fcfs`**; requests handled in arrival order.
- **TensorRT-LLM**: FCFS admission ("in-flight batching") with a capacity policy that
  decides *how many* fit (`GUARANTEED_NO_EVICT`, the default, never evicts a started
  request; `MAX_UTILIZATION` packs more but may evict).
- **Orca** itself used "simple first-come-first-served."
- **SGLang**: has cache-aware reordering (`lpm`, below) but the current source defaults
  to `fcfs` (docs say `lpm` — this is version-dependent; verify for your build).

FCFS is simple and starvation-free, but it has a well-known weakness: **head-of-line
blocking**. A short interactive request stuck behind long jobs waits for all of them.
Under FCFS, as much as **90% of a request's end-to-end latency can be pure queueing**,
not compute. [FastServe]

> **This is the crucial framing for the paper:** in production, the *sophistication is
> not in the ordering policy* — it's in the batching (Orca), memory paging
> (PagedAttention), and chunked prefill (Sarathi-Serve) wrapped around a plain FCFS
> order. Modeling **"FCFS admission on top of continuous batching + PagedAttention +
> chunked prefill"** *is* modeling the real, state-of-the-art default. Modeling naive
> static-batch FCFS would be the strawman.

### Smarter policies exist — and each buys a *new* failure mode

This table is itself a paper argument: there is no free lunch, which is *why* FCFS
persists as the default. [statuses as of 2025–2026]

| Policy / system | Idea | The new pathology it introduces |
|---|---|---|
| **Priority** (vLLM `priority`, TRT-LLM per-request priority) | run high-priority first | **starvation** of low-priority / long requests (needs aging) |
| **SJF / SRPT via length prediction** (learning-to-rank NeurIPS'24; S3; TRAIL) | run shortest job first | **starvation** of long requests; **mispredicted** length → tail-latency blowups |
| **FastServe** (skip-join MLFQ ≈ preemptive SRPT) | multi-level feedback queue | starves long requests; heavy **KV swap/offload** overhead from token-level preemption |
| **VTC** (fair scheduling, OSDI'24) | fair share by token count | **ignores KV-cache locality**; fairness ≠ efficiency |
| **SCORPIO** (SLO-aware, 2025) | least-deadline-first + admission control | **rejects requests** (a new denial mode); starves best-effort traffic |
| **Chunked prefill** (Sarathi-Serve, OSDI'24) | spread prefill over iterations | residual **prefill-decode interference** degrades per-token time; chunk-size tuning is delicate |
| **Llumnix** (OSDI'24) | migrate requests across GPU instances | KV-**migration thrashing**; central-scheduler bottleneck |

**Only chunked prefill and (in alpha) Llumnix have really crossed into production;** the
rest are research prototypes. The recurring lesson — *every clever ordering trades
FCFS's simplicity for a new way to starve, mispredict, reject, or thrash* — is exactly
the kind of non-obvious, input-pattern-dependent risk our tool is meant to quantify.

---

## 7. The metrics that define "bad"

Latency in LLM serving is not one number. The SLOs (service-level objectives) that
matter:

- **TTFT — Time To First Token.** From request arrival to the first output token. Covers
  *queueing + prefill*. This is "how long until the answer starts appearing."
- **TBT / ITL — Time Between Tokens / Inter-Token Latency.** The gap between consecutive
  output tokens *within* one request. This is "how smoothly the answer streams." A
  generation stall is a big TBT spike.
- **TPOT — Time Per Output Token.** The *average* per-token time over a request (≈ mean
  of its TBTs). (Note: some vendors use TPOT and ITL interchangeably; strictly, TBT is
  per-interval and TPOT is the average.)
- **Goodput.** The max request rate that still meets the SLOs for, say, 90% of requests.
  This — not raw throughput — is what capacity planning targets. [DistServe]

> **Concrete targets (MLPerf Inference v5.0, Llama-2-70B):** *Server* scenario allows
> P99 TTFT = 2 s and P99 TPOT = 200 ms; the *Interactive* scenario tightens these to
> **450 ms** TTFT and **40 ms** TPOT (≈ 25 tokens/sec/user). Sarathi-Serve defines its
> TBT SLO as a multiple (5× strict, 25× relaxed) of a contention-free decode step.
> [MLPerf v5.0; Sarathi-Serve]

A "bad event" in our model will be one of: a **TBT/TTFT SLO violation** (a stall), a
**KV-exhaustion preemption**, or a **preemption cascade**.

---

## 8. The inputs: what real request traffic looks like

The scheduler doesn't control its input — the *request pattern* does. From production
traces, three facts stand out (these are the "knobs" our conditions will range over):

1. **Prompt lengths are heavy-tailed.** ~4× spread from median to P99; code prompts run
   ~2× longer than chat at the median. [Azure LLM trace 2023]
2. **Output lengths have extreme variability** — much more than inputs. Coefficient of
   variation ≈ **3.3** for code (most answers tiny, a few huge), ≈ 1.5 for chat. And the
   output length is **unknown when the request is admitted** — this is precisely what
   breaks shortest-job-first scheduling. [BurstGPT; SCORPIO]
3. **Arrivals are bursty**, not smooth — modeled with a Gamma concurrency distribution
   (smaller shape = burstier); bursts are when resource exhaustion actually happens.
   [BurstGPT arXiv:2401.17644]

And a genuinely non-obvious one, ripe for our analysis:

4. **Length correlations don't generalize across workloads.** Prompt and answer length are
   *positively* correlated for ChatGPT-style traffic but *inversely* correlated for
   Llama-style traffic — so "an optimization tuned on one workload can regress on
   another." [BurstGPT] A scheduler assumption that is safe for one traffic shape can be
   dangerous for another.

---

## 9. Putting it together: the mental model for the case study

```
        REQUESTS ARRIVE                    ONE GPU WORKER (the contention point)
   (prompt len, output len,        ┌─────────────────────────────────────────────┐
    arrival timing — all random)   │  scheduler, every iteration (= 1 DTMC step): │
        │                          │   1. admit waiting reqs (FCFS/priority)       │
        │   heavy-tailed,          │   2. run prefill chunks within token budget   │
        ▼   bursty, correlated     │   3. run one decode step for the batch        │
   [ waiting queue ] ───────────►  │   4. if KV pool full -> PREEMPT (evict, LIFO) │
                                   │      contended resources:                     │
                                   │        • per-iteration token/compute budget   │
                                   │        • shared KV-cache block pool  ◄── the  │
                                   │                                     "buffer"  │
                                   └─────────────────────────────────────────────┘
                                          │
                                          ▼
                                   BAD EVENTS (what we ask about):
                                     • generation stall  -> TBT SLO violation
                                     • TTFT SLO violation (queued too long)
                                     • KV exhaustion -> request preempted/evicted
                                     • preemption cascade
```

The research question our tool answers: **given a bad event and a condition on the
request pattern, how probable is that bad event under that condition?** — and, as in the
FQ-CoDel and incast case studies, the prize is a **non-obvious, "mild" assumption about
the input** (a traffic *shape* or *correlation*, not just "high load") that makes an
undesirable event surprisingly likely, even on today's state-of-the-art scheduler.

---

## 10. Glossary (quick reference)

- **Prefill** — processing the whole prompt in one pass to produce the first token
  (compute-bound).
- **Decode** — generating output one token at a time (memory-bandwidth-bound).
- **KV cache** — per-request stored context in GPU memory; grows every decode step; the
  shared, finite resource.
- **PagedAttention** — 16-token-block memory management for the KV cache (vLLM).
- **Continuous / iteration-level batching** — recomposing the batch every step so no slot
  idles (Orca; NVIDIA "in-flight batching").
- **Chunked prefill** — splitting a long prompt across iterations to avoid stalling
  decodes (Sarathi-Serve; default in vLLM V1).
- **Preemption** — evicting a running request's KV cache when memory is exhausted;
  recovered by recompute or swap.
- **Head-of-line (HOL) blocking** — a heavy item at the front of the queue delaying
  everything behind it.
- **TTFT / TBT / TPOT / goodput** — time to first token / time between tokens / time per
  output token / rate meeting SLO (see §7).
- **FCFS** — first-come-first-served; the production-default request order.

---

## References

Peer-reviewed systems papers:
- **Orca: A Distributed Serving System for Transformer-Based Generative Models.** Yu et
  al., OSDI 2022. (Iteration-level / continuous batching, selective batching, FCFS pool.)
  https://www.usenix.org/system/files/osdi22-yu.pdf
- **Efficient Memory Management for LLM Serving with PagedAttention.** Kwon et al.,
  SOSP 2023 (Best Paper). (KV-cache paging, preemption.) https://arxiv.org/abs/2309.06180
- **Taming Throughput-Latency Tradeoff in LLM Inference with Sarathi-Serve.** Agrawal et
  al., OSDI 2024. (Chunked prefill, prefill-decode interference, TBT SLO.)
  https://arxiv.org/abs/2403.02310
- **DistServe: Disaggregating Prefill and Decoding.** Zhong et al., OSDI 2024.
  https://arxiv.org/abs/2401.09670
- **Splitwise: Efficient Generative LLM Inference Using Phase Splitting.** Patel et al.,
  ISCA 2024. https://arxiv.org/abs/2311.18677
- **Fast Distributed Inference Serving for LLMs (FastServe).** Wu et al.,
  arXiv:2305.05920. (Skip-join MLFQ; 90%-queueing finding.)
- **Efficient LLM Scheduling by Learning to Rank.** Fu et al., NeurIPS 2024.
  https://arxiv.org/abs/2408.15792
- **Fairness in Serving Large Language Models (VTC).** Sheng et al., OSDI 2024.
  https://arxiv.org/abs/2401.00588
- **Llumnix: Dynamic Scheduling for LLM Serving.** Sun et al., OSDI 2024.
  https://arxiv.org/abs/2406.03243
- **BurstGPT: workload trace study.** arXiv:2401.17644. (Burstiness; output CV; length
  correlations differ by workload.)

Docs, benchmarks, and engineering sources:
- vLLM scheduler config & V1 engine (FCFS default, chunked prefill, preemption):
  https://docs.vllm.ai (SchedulerConfig, `--scheduling-policy`, V1 guide) and
  https://github.com/vllm-project/vllm/blob/main/vllm/v1/core/sched/scheduler.py
- NVIDIA TensorRT-LLM in-flight batching & capacity policies:
  https://nvidia.github.io/TensorRT-LLM/advanced/executor.html
- SGLang scheduling policies (RadixAttention, `lpm`/`fcfs`):
  https://github.com/sgl-project/sglang and https://arxiv.org/abs/2312.07104
- Anyscale, "How Continuous Batching Enables 23x Throughput," 2023.
- MLPerf Inference v5.0 results & SLO definitions (MLCommons, 2025).
- "LLM Inference Unveiled: Survey and Roofline Model Insights," arXiv:2402.16363.

*Note on version-sensitive facts: vLLM's chunked-prefill-by-default anchors to the V1
engine becoming default in ~v0.8.0 (March 2025); SGLang's default policy (`fcfs` in
current source vs. `lpm` in some docs) is version-dependent — verify against your build.*

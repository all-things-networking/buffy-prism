# Case study notes — the LLM inference batch scheduler

*Third motivating case study for conditional probabilistic reasoning about a
contention point. See [SCHEDULING_PRIMER.md](SCHEDULING_PRIMER.md) for the domain
background and [`../../README.md`](../../README.md) for the shared methodology.*

## The contention point

One GPU worker running the realistic **vLLM-V1 default stack**: continuous
(iteration-level) batching [Orca, OSDI'22], a shared finite **KV-cache block
pool** [PagedAttention, SOSP'23], **chunked prefill** (default on) [Sarathi-Serve,
OSDI'24], and **FCFS admission**. The model (`scheduler.pm`) is a DTMC in which one
step = one scheduler iteration; it is small enough for **exact** model checking
(12,699 states) — no statistical-model-checking noise, unlike the FQ-CoDel and
incast studies.

We watch one interactive **victim** request (short prompt, tight latency needs)
sharing the worker with 2 background slots into which requests of random shape
(short / long) arrive. Bad events, all monotone counters read at the horizon:

- **BE1 `v_preempts>=1`** — the victim is evicted from the KV pool (preemption).
- **BE2 `v_maxgap>=SLO_TBT`** — the victim's inter-token gap violates its TBT SLO.
- **BE3 `preempts>=K_CASC`** — a system-wide preemption cascade.

## The headline finding — *shape and timing, not volume*

Regime `p_arr=0.5, p_long=0.4`, scheduler `fcfs + chunked` (the production default).
Exact results (`./run_case_study.sh`):

| condition C on the request pattern | P(BE1) | P(BE1 \| C) | P(C) | lift |
|---|---|---|---|---|
| — (baseline) | 0.143 | — | — | — |
| **a long request arrived *before* the victim, none after** | 0.143 | **0.397** | **0.20** | **2.8×** |
| the same longs arrived *after* the victim, none before | 0.143 | **0.000** | 0.36 | 0 |
| *volume*: `n_long>=2` (≥2 long requests arrived at all) | 0.143 | 0.273 | 0.50 | 1.9× |

**The non-obvious assumption:** the interactive request is evicted not because the
load is high, nor because many long requests arrive, but because a long-context
request happens to arrive **just before it**. Under FCFS the KV-exhaustion
preemption order is **LIFO** (evict the most-recently-admitted running request), so
an early long prompt makes the *later* interactive request the "newest" — and
therefore the eviction target. The **identical** long requests arriving *after* the
victim are completely harmless (P = 0): they become the newest and shield the
victim.

This is:
- **mild** — the triggering condition holds only ~20% of the time;
- **informative** — it nearly triples the bad-event probability;
- **invisible per component** — every request is individually well-formed and every
  per-request metric looks fine; the harm is in the *arrival order relative to the
  victim* interacting with LIFO eviction;
- **stronger than the obvious knob** — conditioning on the *volume* of long requests
  (`n_long>=2`) lifts P only to 0.27, and is a much more common (0.50) condition. The
  *timing* is the real driver, and it is what a single counterexample trace could
  never reveal.

Mirrors the other two case studies: FQ-CoDel ("*shape not volume*" — a light
idle-then-active flow starves others) and incast ("moderate fan-out regardless of
temporal spread, invisible at any single buffer").

## Scheduler-knob comparison (same input, baseline probabilities)

| variant | P(preempt) | P(stall) | P(cascade) |
|---|---|---|---|
| `fcfs + chunked` (vLLM default) | 0.143 | 0.143 | 0.084 |
| `priority + chunked` | **0.000** | **0.000** | 0.032 |
| `fcfs + eager` (pre-Sarathi) | 0.155 | **0.389** | 0.408 |

Reads:
- **Chunked prefill earns its keep:** turning it off (`eager`) more than doubles the
  victim stall probability (0.14 → 0.39) and multiplies cascades (0.08 → 0.41),
  because a whole-prompt prefill hogs the iteration and stalls every decode — the
  exact pathology chunked prefill was designed to remove.
- **Priority protects the victim** (P → 0) — but note the literature caveat: priority
  merely *moves* the harm onto the low-priority background requests (starvation), the
  new pathology every non-FCFS policy introduces. A natural follow-up query is
  "P(a background request starves | priority)".
- Under the realistic default (`fcfs + chunked`), BE1 and BE2 **coincide** — with
  chunked prefill the *only* way the victim stalls is via KV-exhaustion preemption
  and recompute. That is itself a finding: chunked prefill removes prefill-induced
  stalls, leaving KV exhaustion as the residual, and non-obvious, risk.

## Model structure (see `scheduler.pm`, heavily commented)

Per iteration (7 stages): `VINJECT` (victim arrives at `T_V`) → `ARRIVE` (≤1
probabilistic background arrival, class short/long = the input pattern) → `SETUP`
(freeze the per-iteration prefill-hog flag, update peak) → `SVC_V` / `SVC_B1` /
`SVC_B2` (advance each request one token, growing its KV blocks) → `PREEMPT` (while
`kv > KV_CAP`, evict by policy score; recovery = recompute, so the evicted request
must rebuild all its blocks). KV blocks per request = current sequence length.

Sweepable constants: `POLICY` (fcfs/priority), `CHUNKED` (chunked/eager), `p_arr`,
`p_long` (the input pattern) — all left undefined, supplied via `-const`.

## Reproduce

```bash
source ~/buffy-prism-tools/env.sh
./run_case_study.sh                 # baseline regime + knob table
PA=0.7 PL=0.4 ./run_case_study.sh   # sweep the load (lift grows to ~2.4×)
```

## Honest caveats / next steps

- **Abstractions** (documented in `scheduler.pm`): ≤1 arrival/iteration; no waiting
  queue (arrivals to a full worker are dropped, so TTFT/queueing delay is not
  modelled — the primary bad event is KV contention among concurrent requests);
  prompt and output length are bundled into a class (baked-in positive
  prompt↔output correlation); recompute cost is a coarse "rebuild all held blocks."
- **Independent cross-check pending.** Both prior studies shipped a Python oracle
  reimplementing the exact dynamics; that is the next task here (PRISM is exact, so
  the oracle guards against *modeling* bugs rather than SMC noise).
- **Further conditions to probe:** decouple prompt/output correlation (an
  independent draw) to test the "length-correlation" hypothesis from the literature;
  add a small waiting queue to bring TTFT-SLO violations into scope; sweep `T_V`
  (when the victim arrives) and `KV_CAP`.

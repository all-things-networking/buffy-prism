# Case study notes — CHUNKED-prefill batch scheduler

*The chunked-prefill variant (vLLM-V1 default). The eager/no-chunking variant is
in [`../no_chunking/`](../no_chunking/); domain background is in
[`../SCHEDULING_PRIMER.md`](../SCHEDULING_PRIMER.md).*

## Model

`scheduler.pm` is a DTMC; one step = one scheduler sub-stage, one iteration spans
`VINJECT→ARRIVE→SETUP→SVC_V→SVC_B1→SVC_B2→PREEMPT`. Chunked prefill is always on
(`chunk = min(pre, CHUNK_BLK)`), so a prefill never stalls a decode — the victim's
**only** stall source is KV-exhaustion preemption + recompute. Small enough for
**exact** model checking (~13k states). Sweepable undefined consts: `POLICY`
(0 fcfs / 1 priority), `p_arr`, `p_long` (the request-mix input pattern).

Bad events (monotone counters, read at the horizon): `v_preempts>=1` (BE1, victim
evicted), `v_maxgap>=SLO_TBT` (BE2, victim TBT-SLO violation), `preempts>=K_CASC`
(BE3, cascade).

## Headline finding — *shape and timing, not volume*

Regime `p_arr=0.5, p_long=0.4`, `POLICY=fcfs`. Exact results (`./run_case_study.sh`):

| condition C on the request pattern | P(BE1) | P(BE1 \| C) | P(C) | lift |
|---|---|---|---|---|
| — (baseline) | 0.143 | — | — | — |
| **a long request arrived *before* the victim, none after** | 0.143 | **0.397** | **0.20** | **2.8×** |
| the same longs arrived *after* the victim, none before | 0.143 | **0.000** | 0.36 | 0 |
| *volume*: `n_long>=2` (≥2 long requests arrived at all) | 0.143 | 0.273 | 0.50 | 1.9× |

**The non-obvious assumption:** the interactive request is evicted not because load
is high, nor because many long requests arrive, but because a long-context request
arrives **just before it**. Under FCFS the KV-exhaustion eviction order is **LIFO**
(most-recently-admitted first), so an early long prompt makes the *later* interactive
request the "newest" → the eviction target. The identical longs arriving *after* the
victim are harmless (P = 0): they become the newest and shield it.

This is **mild** (holds ~20% of the time), **informative** (nearly triples the risk),
**invisible per component** (every request is individually fine — the harm is in the
arrival order relative to the victim × LIFO eviction), and **stronger than the obvious
knob** (volume `n_long>=2` lifts P only to 0.27 and is far more common). Mirrors
FQ-CoDel ("shape not volume") and incast ("timing matters, invisible per buffer").

## Policy comparison (chunked, same input)

| policy | P(preempt) | P(stall) | P(cascade) |
|---|---|---|---|
| fcfs | 0.143 | 0.143 | 0.084 |
| priority | **0.000** | **0.000** | 0.032 |

- `priority` protects the victim (P → 0) — but the literature caveat applies: priority
  merely *moves* the harm onto the low-priority background requests (starvation). A
  natural follow-up query: "P(a background request starves | priority)."
- Under `fcfs`, BE1 and BE2 **coincide** — with chunked prefill the only way the victim
  stalls is via preemption + recompute. That is itself the point of this variant:
  chunked prefill removes prefill-induced stalls, leaving KV exhaustion as the residual,
  non-obvious risk. (Compare `../no_chunking/`, where P(stall) is much higher because a
  whole-prompt prefill freezes decodes.)

## Reproduce

```bash
source ~/buffy-prism-tools/env.sh
./run_case_study.sh                 # baseline regime + policy table
PA=0.7 PL=0.4 ./run_case_study.sh   # heavier load (lift grows)
```

## Honest caveats / next steps (from the design review)

- **Toy magnitudes, faithful ratios.** 3 slots (vs ~256 real `max_num_seqs`), KV_CAP=8
  blocks, chunk 1 block, T=10 — none are real magnitudes; only the *ratios*
  (oversubscribed KV ~2.3×, long≈3×short, chunk≪prompt, arrivals>slots) are meant to be
  faithful. This is a mechanism model, not a calibrated one. Sweep to check robustness.
- **No queue** (two senses): background arrivals to a full worker are *dropped* (no
  admission queue → TTFT/queueing not modelled); an evicted request recomputes *in place*
  in its slot (no preempted-request waiting queue, unlike real vLLM). Adding a small
  waiting queue is the biggest fidelity upgrade and would bring TTFT bad events into scope.
- **Bundled prompt/output length** bakes in a fixed *positive* correlation, which
  precludes studying the prompt↔output-correlation hypothesis. Decoupling them (with a
  tunable correlation) is a priority enhancement.
- **Fixed victim arrival `T_V=3`.** Sweep `T_V` to confirm the finding isn't specific to
  one arrival time.
- **Independent cross-check pending.** A Python oracle re-implementing the exact dynamics
  (as in the FQ-CoDel/incast studies) is the next task; guards against modeling bugs.

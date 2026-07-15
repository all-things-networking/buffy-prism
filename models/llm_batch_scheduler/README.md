# LLM inference batch-scheduler case study

A case study in conditional probabilistic reasoning about a contention point: the
**batch scheduler of a GPU worker in LLM inference serving**.

Start with **[`HANDOFF.md`](HANDOFF.md)** — it explains the model, how to run it,
the property checked, and the results.

## Contents

- **[`HANDOFF.md`](HANDOFF.md)** — entry point: what this is, how to run, results, open work.
- **[`SCHEDULING_PRIMER.md`](SCHEDULING_PRIMER.md)** — domain background (prefill/decode,
  KV cache, continuous batching, chunked prefill, preemption, scheduling policies, SLOs).
  Read this if the terms above are unfamiliar.
- **[`PARAMETERS.md`](PARAMETERS.md)** — model values vs. real-system values, and which
  ratios are meant to be faithful.

## Models

- **[`chunked/`](chunked/)** — the main model. Chunked-prefill continuous batching (the
  vLLM-V1 default), with a real waiting queue. All current results come from here.
- **[`no_chunking/`](no_chunking/)** — eager whole-prompt prefill, for comparison: it shows
  the interactive-latency cost that chunked prefill removes.
- **[`chunked_dedicated_slot/`](chunked_dedicated_slot/)** — an earlier, simpler chunked
  model where the tracked request has its own batch slot. Kept for reference; not used for
  current results.

Run with the persistent toolchain:

```bash
source ~/buffy-prism-tools/env.sh
cd chunked && ./run_study.sh
```

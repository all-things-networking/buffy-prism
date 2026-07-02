# LLM inference batch-scheduler case study

Third motivating case study for conditional probabilistic reasoning about a contention
point — here, the **batch scheduler of a GPU worker in LLM inference serving**.

- **[`SCHEDULING_PRIMER.md`](SCHEDULING_PRIMER.md)** — ground-up, cited domain primer
  (prefill/decode, continuous batching, PagedAttention KV, chunked prefill, preemption,
  FCFS vs. sophisticated policies, SLO metrics, request-pattern inputs). Read first.

Two scheduler variants share the same DTMC structure, victim, resources, and eviction
policy; they differ only in how prefill is scheduled:

- **[`chunked/`](chunked/)** — chunked prefill (the vLLM-V1 default). A prefill never
  stalls a decode, so the victim's only stall source is KV-exhaustion preemption. **This
  is the focus.** See [`chunked/NOTES.md`](chunked/NOTES.md) for the headline finding.
- **[`no_chunking/`](no_chunking/)** — eager whole-prompt prefill (pre-Sarathi FCFS): a
  prompt monopolizes an iteration and freezes all decodes (the generation-stall
  pathology). Kept for the chunked-vs-eager comparison.

Each variant: `scheduler.pm` (model), `scheduler.props` (grouped conditional queries),
`run_case_study.sh` (exact PRISM reproduction). Run with the persistent toolchain:

```bash
source ~/buffy-prism-tools/env.sh
cd chunked && ./run_case_study.sh
```

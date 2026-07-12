# Handoff — LLM batch-scheduler case study

This is the third case study for the paper on conditional probabilistic reasoning
about contention points. It has the same structure as the FQ-CoDel example: a
contention point, a tracked "victim" whose input may differ from the rest but which
gets no special treatment, a bad event, and conditional probabilities
`P(bad | condition)` over the input pattern. The contention point here is the
**batch scheduler of a GPU worker in LLM inference serving**.

Branch: `llm-batch-scheduler-case-study`.

## Where to start

1. This file — orientation, how to run, current status, open work.
2. `SCHEDULING_PRIMER.md` — the domain, from the ground up. Read it if prefill/decode,
   KV cache, continuous batching, chunked prefill, or preemption are unfamiliar. The
   key fact for this case study: the scheduler knows a request's prompt length at
   admission but not its output length.
3. `chunked/NOTES.md` — the results.
4. `chunked/VALIDATION.md` — the same result confirmed at realistic scale by simulation.
5. `PARAMETERS.md` — which numbers are realistic and which are not.

## Folder layout

```
model/llm_batch_scheduler/
  SCHEDULING_PRIMER.md        domain background
  PARAMETERS.md               model values vs. real-system values
  README.md                   short index
  HANDOFF.md                  this file
  chunked/                    the main model (chunked prefill + real queue)
    scheduler.pm                the model
    scheduler.props            the conditional queries
    run_study.sh               one-regime table (exact)
    sweep.sh                   regime sweep for the parameter box (exact)
    NOTES.md                   results
    gen_scheduler.py           generates the model for any number of records
    scheduler_big.pm           a large generated model (rebuilt by the SMC runner)
    run_smc_validation.sh      simulation at realistic scale
    VALIDATION.md              simulation results
  no_chunking/                eager whole-prompt prefill, for comparison
  chunked_dedicated_slot/     earlier simpler chunked model; not used for results
```

The main model is `chunked/`. `no_chunking/` is a comparison that shows the cost
chunked prefill removes. `chunked_dedicated_slot/` is an earlier variant kept for
reference only.

## The model: `chunked/scheduler.pm`

A DTMC. Time advances in scheduler **iterations** (one forward pass over the running
batch). The horizon is `T`.

PRISM has no arrays, so the model spells out a fixed number of **request records**.
Each record holds a status `st` (`0` empty, `1` waiting, `2` running) plus its
remaining prompt blocks `pp`, remaining output blocks `oo`, KV blocks held `bk`, and
arrival time `ad`. Record 1 is the tracked request; it carries gap counters for its
inter-token latency but has no scheduler privilege. Records 2 and 3 are background.

One iteration runs through stages (the `stage` variable):

1. `VINJECT` — at iteration `T_V`, the tracked request appears as a waiting record.
2. `ARRIVE` — with probability `p_arr`, one background request arrives into an empty
   record. Its prompt is long with probability `p_lp`; its output is long with
   probability `p_ol_sp` or `p_ol_lp` depending on prompt class.
3. `ADMIT` — promote waiting records to running while fewer than `N_SLOTS` are
   running, in FCFS order (`ADM_POLICY=0`) or shortest-prompt-first order
   (`ADM_POLICY=1`). Waiting records are the queue.
4. `SVC_k` (one stage per record) — each running record does one iteration of work:
   prefill up to `CHUNK_BLK` blocks, otherwise decode one output block, otherwise
   finish and free its slot and KV. The tracked request's stages update its
   inter-token gap; `v_maxgap` is the worst gap seen.
5. `PREEMPT` — if total KV exceeds `KV_CAP`, evict running records back to waiting
   (LIFO, or protect the tracked request if `POLICY=1`) until KV fits.

Constants you set at run time with `-const` (left undefined in the file):
`T_V, N_SLOTS, KV_CAP, CHUNK_BLK, POLICY, ADM_POLICY, p_arr, p_lp, p_ol_sp, p_ol_lp`.
Request sizes (`SP/LP` prompt, `SO/LO` output, `VP/VO` tracked request) are defined
in the file; edit them to change the ratios.

Bad-event labels at the bottom of the file: `v_stalled` (`v_maxgap >= SLO_TBT`, the
main one), `v_preempted`, `cascade`, and `done` (`t = T`).

## The property

Bad event: the tracked request suffers an interactive-latency stall
(`v_maxgap >= SLO_TBT`). For a condition `C` on the request pattern, the queries in
`scheduler.props` compute `P(bad)`, `P(bad & C)`, and `P(C)`; the conditional
`P(bad | C)` is the ratio. `scheduler.props` groups these into conditions A–F
(request arriving before vs. after the tracked request, request volume, and
correlation between long prompt and long output).

## How to run

```bash
source ~/buffy-prism-tools/env.sh          # Java 21 + PRISM
cd model/llm_batch_scheduler/chunked

./run_study.sh          # conditional-probability table for one regime (exact)
./sweep.sh              # sweep regimes and rank candidate assumptions (exact)
./run_smc_validation.sh # rebuild the large model and validate by simulation

# a single query by hand:
PRISM=~/buffy-prism-tools/prism-4.10.1-linux64-x86/bin/prism
$PRISM scheduler.pm scheduler.props \
   -const T_V=3,N_SLOTS=2,KV_CAP=8,CHUNK_BLK=3,POLICY=0,ADM_POLICY=0,p_arr=0.5,p_lp=0.4,p_ol_sp=0.4,p_ol_lp=0.4
```

## Main result

Under chunked prefill, when a prompt fits in one prefill chunk, `P(stall)` does not
depend on the fraction of long-**prompt** requests. It is driven by the fraction of
long-**output** requests.

The reason: chunked prefill reduces any prompt to about one iteration, so prompt
length no longer changes how long a request holds a slot. Output length does — one
decode iteration per output token — so it sets the queueing delay the tracked
request sees.

This is the useful part: output length is the one feature the scheduler cannot
observe at admission. Scheduling by prompt length (the visible feature) does not
control the stall.

`P(stall)` is monotone increasing in `p_lp`, `p_ol`, and `p_arr`, which lets the
result be stated as a certified parameter box (a range of inputs, not a single
point). The full tables and the two candidate boxes are in `chunked/NOTES.md`.

## Status

- Model built and exact-checked at small sizes (`chunked/`).
- Result confirmed at realistic scale by simulation (`chunked/VALIDATION.md`): with
  wide size ratios and an oversubscribed batch, `P(stall)` stays flat across the
  long-prompt fraction (0.47–0.48) and swings from 0.02 to 0.95 across the
  long-output fraction.
- `gen_scheduler.py` reproduces the hand-written `scheduler.pm` exactly at
  `M=3, N_SLOTS=2`, which cross-checks the generator against the model.

## Open work

1. **Independent oracle.** The other two case studies each have a from-scratch
   simulator (not PRISM) that reproduces a few probability values. This one does not
   yet. This is the main missing piece.
2. **Time-to-first-token bad event.** The queue is modeled, but only the inter-token
   stall is scored. A TTFT SLO label would add the admission-latency metric.
3. **Robustness sweeps** over `T_V`, `KV_CAP`, `N_SLOTS`, and the horizon. In
   particular, `T_V` is currently non-monotone (a finite-horizon effect) and is kept
   out of the parameter box; a longer horizon may fix this.
4. **Prompt/output correlation at scale.** The correlation knob (`p_ol_sp` vs.
   `p_ol_lp`) has only been exercised at small sizes.
5. **Write the case-study narrative** from `NOTES.md` and `VALIDATION.md`.

## Gotchas

- `W` is a reserved word in PCTL (weak-until); the window constant is named `WIN`.
- `-const` returns nothing if you try to override a constant that is defined in the
  file. The sweepable constants are left undefined on purpose.
- The clamp `t' = min(T, t+1)` in the `PREEMPT` stage is needed so the symbolic
  engine does not reach a state where probabilities sum to less than one. Keep it.
- Sweep with PRISM experiment mode (`-const x=lo:step:hi`, one JVM start), not a bash
  loop that starts a new JVM per point.

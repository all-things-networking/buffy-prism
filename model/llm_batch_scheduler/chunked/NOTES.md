# Findings — chunked scheduler (`scheduler.pm`)

## What the model computes

`scheduler.pm` is a DTMC of a GPU worker running chunked-prefill continuous
batching. One tracked request (record 1, the "victim": short prompt, modest
output) competes for `N_SLOTS` batch slots against background requests. Background
requests arrive with probability `p_arr` per iteration; each has a long prompt
with probability `p_lp` and a long output with probability `p_ol_sp` / `p_ol_lp`
(conditioned on prompt class). The tracked request has no scheduler privilege.

Bad event: the tracked request's inter-token gap reaches the SLO threshold
(`v_maxgap >= SLO_TBT`), i.e. an interactive-latency stall. Queries in
`scheduler.props` report `P(bad)`, `P(bad & C)`, and `P(C)` for several
conditions `C` on the request pattern; the conditional is the ratio.

Run: `source ~/buffy-prism-tools/env.sh && ./run_study.sh`.

## Main result: output length dominates; prompt length is the weaker, and visible, factor

> **Correction (see `REGIONS.md`).** An earlier phrasing said prompt length is
> *irrelevant*. That is true only in the **single-chunk** special case below
> (`CHUNK_BLK >= LP`, i.e. a prompt that fits in one prefill chunk). For **realistic
> multi-chunk** long-context prompts (a prompt spanning several 512-token chunks), prompt
> length is **not** irrelevant — but a long **output** request still harms interactive
> latency **~2–4× more** than a long-context prompt request (it holds its slot ~33 vs. ~5
> iterations), and output is the half the scheduler cannot see at admission. The corrected,
> realistic analysis and the mild/obvious regions are in `REGIONS.md`.

### Single-chunk special case (exact invariance)

Set `CHUNK_BLK >= LP` so a long prompt prefills in about one iteration (true only for
short prompts, ≲ one 512-token chunk).
Sweep `P(stall)` over the long-prompt fraction `p_lp` and the long-output
fraction `p_ol` (`N_SLOTS=1`, `p_arr=0.8`):

|            | p_ol=0.0 | p_ol=0.5 | p_ol=1.0 |
|------------|----------|----------|----------|
| p_lp=0.0   | 0.640    | 0.864    | 0.960    |
| p_lp=0.5   | 0.640    | 0.864    | 0.960    |
| p_lp=1.0   | 0.640    | 0.864    | 0.960    |

`P(stall)` does not change with `p_lp` (spread 0.000) and rises monotonically with
`p_ol`. It holds at `N_SLOTS=2` as well (`p_lp` 0.2→0.8: 0.017→0.017;
`p_ol` 0.2→0.8: 0.017→0.138).

**Mechanism.** Chunked prefill reduces any prompt to about one iteration, so prompt
length no longer changes how long a request holds a slot. Output length does: a
request occupies its slot for one decode iteration per output token. The tracked
request's queueing delay is set by how long incumbents hold their slots, which is
their output length, not their prompt length.

**Why this matters.** The common expectation is that long-context (long-prompt)
requests are the main threat to interactive latency. Under chunked prefill that threat is
much smaller than expected: a long **output** request is the ~2–4× larger driver, and it
is the one feature the scheduler cannot observe at admission (see `../SCHEDULING_PRIMER.md`).
So admission, routing, or prioritization based on prompt length (the visible feature)
targets the weaker factor; controlling the stall requires predicting output length.

For **realistic multi-chunk** prompts the per-request comparison, the sharp-vs-gradual
structure, and the certified mild/obvious **regions** (in the `example3` style) are in
`REGIONS.md`, on the realistic model `scheduler_mc.pm`. The single-chunk invariance above
is the limiting case; `VALIDATION.md` covers the multi-chunk scaling.

## Paper assumption (monotone parameter box)

`P(stall)` is monotone increasing in `p_lp`, `p_ol`, and `p_arr` (checked on the
sweep grid: 0/72, 0/48, 1/64 violations). A box over these parameters is therefore
certified at its lower corner.

**Primary box (output dominance):**
> Under chunked prefill, for prompts within one prefill chunk, `P(stall)` is
> invariant to `p_lp` in [0,1] and monotone increasing in the long-output fraction.
> For `p_ol >= 0.5` (at this load), `P(stall) >= 0.86`, independent of prompt lengths.

**Secondary box (composition beats load):** at `A = { p_arr in [0.6,0.8],
p_lp in [0.6,0.8], p_ol = 0.6 }`, `P(stall) >= 0.19` at the worst corner (typically
0.36–0.48). By contrast `{ p_lp <= 0.4, p_ol = 0.3 }` gives `P(stall) <= 0.12` even
at higher load. A moderately loaded worker with a long-heavy mix stalls the tracked
request more than a heavily loaded worker with short requests:

| regime | P(stall) |
|--------|----------|
| moderate load, long-heavy (p_arr=0.6, p_lp=0.8, p_ol=0.6) | 0.359 |
| high load, short mix (p_arr=0.8, p_lp=0.2, p_ol=0.3)      | 0.101 |

The composition box is the paper-ready form. `T_V` (arrival time) is non-monotone
under a finite horizon and is kept out of the box as a fixed input assumption.

## Secondary results

**Queueing delay is timing-sensitive.** With `CHUNK_BLK=3`, `p_arr=0.5`,
`p_lp=p_ol=0.4`, baseline `P(stall)=0.108`:

| condition C | P(stall \| C) | P(C) | vs baseline |
|-------------|--------------|------|-------------|
| a long-prompt request arrived before the tracked request, none after | 0.221 | 0.19 | 2.0× |
| the same longs arrived after, none before | 0.018 | 0.34 | 0.17× |
| >= 2 long requests arrived (volume) | 0.163 | 0.50 | 1.5× |
| long in both prompt and output | 0.236 | 0.24 | 2.2× |

A long request arriving before the tracked request holds a slot and delays it;
the same request arriving after is harmless. Timing matters more than volume.
This conditional does not form a clean parameter box (`T_V` is non-monotone), so it
supports the mechanism but is not the paper assumption.

**Three scheduling levers, tested:**
1. SJF admission by prompt length helps the short tracked request (0.857→0.380). It
   does not backfire on it.
2. Adding KV capacity reduces stalls. But raising `N_SLOTS` at fixed `KV_CAP`
   increases preemption (`KV_CAP=8`: `N_SLOTS` 1→2→3 gives `P(preempt)` 0→0.11→0.27).
   Adding batch slots trades queueing delay for preemption unless KV scales too.
3. Eviction priority for the tracked request gives the same `P(stall)` as FCFS
   (0.335) in the queueing regime: protecting it from eviction does nothing for its
   queueing delay.

Prompt/output correlation, at equal marginals, barely moves `P(stall)`
(independent 0.231, positive 0.236, negative 0.198).

## Caveats

- At these small sizes the tracked request is never preempted (`P(preempted)=0`) and
  the preemption cascade never fires. Preemption bad events need the larger SMC
  config (`run_smc_validation.sh`), where they reappear.
- Magnitudes are small; only the ratios are meant to be realistic. See
  `../PARAMETERS.md`.
- `T_V` (arrival time) is fixed, not random.
- The dedicated-slot model in `../chunked_dedicated_slot/` gives the tracked request
  its own slot; it is an earlier, simpler variant and is not used for the results
  above.

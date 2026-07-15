# State-space sizes of the PRISM models

This note estimates, for the case-study models, two different quantities:

1. **Declared (syntactic) state space** — the Cartesian product of every module
   variable's declared range. This is the upper bound PRISM/Storm would start
   from *before* reachability analysis. It is obtained purely by multiplying the
   variable ranges.
2. **Reachable state space** — the number of states actually visited by some
   run. This is far smaller, because most variable combinations are dynamically
   impossible. For the large models (`incast`, `fqcodel`) these are structural
   order-of-magnitude estimates, not exact counts: they are used as black-box
   simulators (for statistical model checking / LCRL), never built explicitly,
   precisely because both numbers are far past what an explicit engine can
   enumerate. The smaller `llm_batch_scheduler/` models *are* exact-model-checked
   (PRISM), so their reachable counts are — or can be — computed directly.

| model | declared (range product) | reachable estimate | main collapse mechanism |
|---|---|---|---|
| `example2_desync_short_bursts/incast.pm` (cert. corner) | ~10⁶⁸ | ~2×10³⁵ | DTMC: buffers are a deterministic function of the `97¹⁶` start-time vectors |
| `example3_fqcodel/fqcodel.pm` | ~3×10²⁴ | ~10¹² | FQ-CoDel list-validity + `contents>0 ⟺ in-list` invariants |
| `llm_batch_scheduler/chunked` | ~1.1×10²⁰ | ~2×10⁵ | DTMC deterministic in arrivals; queue/shape/counter invariants |
| `llm_batch_scheduler/chunked_dedicated_slot` | ~4.2×10¹⁷ | ~1.3×10⁴ | same, no admission queue (**documented ~13k**) |
| `llm_batch_scheduler/no_chunking` | ~8.4×10¹⁷ | ~2×10⁴ | same skeleton + `hog` bit; eager prefill |

For context, explicit engines (Storm/PRISM sparse) top out around 10⁷–10⁹
states, so neither `incast` nor `fqcodel` is explicitly constructible at these
settings — which is why the repo simulates them rather than model-checking them.
The `llm_batch_scheduler/` variants are far smaller and *are* exact-model-checked
(see that section).

---

## `example2_desync_short_bursts/incast.pm`

`incast.pm` leaves its constants (`M, WIN, SLEN, BUF, THRESH`) undefined — it is a
swept "box". The numbers below use the canonical **least-favorable certification
corner** from `incast.props` / `NOTES.md`:

```
M = 16,  WIN = 96,  SLEN = 8,  BUF = 32,  THRESH = 8
```

which fixes the derived ranges `TWIN = max(WIN,1) = 96`,
`HORIZON = WIN + M·SLEN + SLEN = 96 + 128 + 8 = 232`, and `NSTAGE = MMAX+1 = 21`.

### Declared state space ≈ 1 × 10⁶⁸

Product of the 55 declared variable ranges:

| variable group | # vars | range | values/var | subtotal |
|---|---|---|---|---|
| `on1..on20` (started?)      | 20 | `[0..1]`            | 2   | 2²⁰ ≈ 1.0×10⁶  |
| `t1..t20` (start slot)      | 20 | `[0..TWIN]=[0..96]` | 97  | 97²⁰ ≈ 5.4×10³⁹ |
| `q1..q10`, `qo` (buffers)   | 11 | `[0..BUF]=[0..32]`  | 33  | 33¹¹ ≈ 5.0×10¹⁶ |
| `odrops`, `idrops`          | 2  | `[0..THRESH]=[0..8]`| 9   | 81 |
| `slot`                      | 1  | `[0..HORIZON]=[0..232]` | 233 | 233 |
| `stage`                     | 1  | `[1..21]`           | 21  | 21 |

Product ≈ **1.1 × 10⁶⁸**. The 20 per-sender **start-time** variables
(`97²⁰ ≈ 10⁴⁰`) dominate; the 11 buffers add another ~10¹⁷.

Because `WIN` sets the `t_k` ranges, the estimate is very sensitive to it. Across
the full assumption box (`WIN ∈ [48,96]`) the declared space runs from
~10⁶² (`WIN=48`) to ~10⁶⁸ (`WIN=96`); `M` and `SLEN` barely matter (they only
move the `slot` factor).

### Reachable state space ≈ 2 × 10³⁵

`incast.pm` is a **DTMC whose only randomness is *when each sender starts***.
Everything else is deterministic given the start times, which collapses the
reachable set enormously.

**Step 1 — only 16 senders, and all of them start.** Senders `k > M=16` are
guarded off, so `on17..20`, `t17..20` are frozen at 0. For the 16 active senders
the per-slot hazard `hz = 1/(WIN+1−slot)` equals **1 at `slot=WIN=96`**, so any
sender still off is *forced* on at the last window slot. Hence in every completed
run `on_k ≡ 1` and each start time `t_k` is uniform on `[0..96]` (97 values):

```
distinct start-time vectors = 97¹⁶ ≈ 6.1 × 10³¹
```

**Step 2 — the buffers are slaved, not free.** Once `(t₁..t₁₆)` is fixed, the
per-slot arrivals `arr_i`, forwarding, draining, and every
`q1..q10, qo, odrops, idrops` are a **deterministic function** of
`(start vector, slot, stage)`. So the `33¹¹·81 ≈ 4×10¹⁸` buffer combinations from
the declared product contribute *nothing* — they do not multiply the count.

**Step 3 — the start vector persists in state, so configurations never merge.**
`t_k` is never reset, so two different start-time vectors are distinct states at
*every* `(slot, stage)` they pass through — even when their buffers coincide.
Each path traverses the ~136-slot drain phase (`slot 97..232`) plus the window,
× 21 stages ≈ **~3 000 `(slot,stage)` pairs**:

```
97¹⁶ × ~3000 ≈ 2 × 10³⁵
```

Symmetry gives no relief: swapping the two senders on one uplink yields identical
queues but a *different* stored `t`-vector, so it remains a distinct state. This
is a firm order-of-magnitude estimate — the `97¹⁶` core is exact; only the
~3 000 `(slot,stage)` multiplier is loose.

---

## `example3_fqcodel/fqcodel.pm`

All constants are defined in the file (`TIME_STEPS = 14`,
`STAGES_PER_TIME_STEP = 16`, `IQS = 5`, `SZ = 8`), so both numbers are
unambiguous.

### Declared state space ≈ 3 × 10²⁴

Product of the 27 declared variable ranges:

| variable group | # vars | range | values/var | subtotal |
|---|---|---|---|---|
| `iq1..iq5_contents`          | 5 | `[0..SZ]=[0..8]`          | 9  | 9⁵ ≈ 5.9×10⁴ |
| `iq1..iq5_new_rank`          | 5 | `[0..IQS]=[0..5]`         | 6  | 6⁵ = 7 776 |
| `iq1..iq5_old_rank`          | 5 | `[0..5]`                  | 6  | 6⁵ = 7 776 |
| `iq1..iq5_arrivals`          | 5 | `[0..5]`                  | 6  | 6⁵ = 7 776 |
| `new_list_len`, `old_list_len` | 2 | `[0..5]`                | 6  | 36 |
| `iq5_cenq`                   | 1 | `[0..(14·4+1)]=[0..57]`   | 58 | 58 |
| `iq5_aipg`                   | 1 | `[0..14]`                 | 15 | 15 |
| `time`                       | 1 | `[0..14]`                 | 15 | 15 |
| `iq5_deqs_bl`                | 1 | `[0..14]`                 | 15 | 15 |
| `stage`                      | 1 | `[1..16]`                 | 16 | 16 |

Product ≈ **3.1 × 10²⁴**. The five per-queue groups (contents + two rank lists +
arrivals) dominate: `9⁵·6¹⁵ ≈ 2.8×10¹⁶` on their own.

### Reachable state space ≈ 10¹² (roughly 10¹¹–10¹³)

`fqcodel.pm` is an MDP whose nondeterminism is the traffic (~70 free 0–4 arrival
choices over the run), so buffers are **not** slaved. The collapse instead comes
from **structural invariants on the FQ-CoDel new/old list bookkeeping**.

**Contents + list arrangement (dominant block).** The naive
`9⁵·6¹² ≈ 1.3×10¹⁴` for 5 contents + 10 ranks + 2 lengths is almost entirely
illegal: valid `new`/`old` lists must assign ranks `{1..len}` injectively, a
queue sits in **at most one** list, and the dynamics enforce the invariant
**`contents_k > 0 ⟺ queue k is in a list`**. Counting only legal configurations
(each queue is either empty & listless, or has contents ∈ 1..8 and exactly one
list slot):

```
Σ_{b=0..5} C(5,b) · (b+1)! · 8ᵇ = 26 177 361 ≈ 2.6 × 10⁷
```

(vs. 1.3×10¹⁴ naive — a ~5-million-fold cut, dominated by the all-5-backlogged
term `720·8⁵`).

**iq5 history counters + clock.** `time` (0–14), `iq5_cenq` (≤ 4·time),
`iq5_aipg` (≤ time), `iq5_deqs_bl` (≤ time) are strongly range-correlated;
summing reachable tuples over `time` gives **~5×10⁴**, not the naive
`58·15·15·15 ≈ 2×10⁵`.

**Micro-stage / arrivals.** The five `arrivals` variables are 0 except
transiently mid-cycle, so `6⁵` collapses to a small per-stage factor; together
with `stage` (1–16) this adds only **~×10**.

```
2.6×10⁷ × ~5×10⁴ × ~10 ≈ 10¹³  →(residual cross-block correlations)→  ~10¹²
```

The ~1-order haircut accounts for overlap between blocks (`iq5_cenq` is partly
redundant with `iq5_contents`; `iq5_deqs_bl` is tied to backlog). This estimate
is softer than the incast one — call it **10¹² within ±1 order** — because the
MDP's arrival freedom leaves the buffers genuinely free, unlike the incast DTMC.

---

## `llm_batch_scheduler/` — three scheduler variants

Three DTMC variants of one GPU inference-batch scheduler run for `T=10`
iterations (7 sub-stages each), each tracking 3 request records (victim `v` +
backgrounds `b1, b2`), victim-latency counters, and arrival-history "feature"
variables. The **only randomness is the background arrivals** (the `ARRIVE`
commands); given the arrival sequence, the entire trajectory is deterministic.

Variable *ranges* are fixed literals keyed to `T=10, GAPMAX=10, NL=4, PT=6`. The
sweepable consts (`N_SLOTS, KV_CAP, CHUNK_BLK, POLICY, ADM_POLICY, T_V, p_*`)
never appear in a range, so the **declared space is independent of them** — they
affect only reachability.

| variant | declared | reachable estimate |
|---|---|---|
| `chunked/scheduler.pm`                | ~1.1×10²⁰ | ~2×10⁵ (10⁵–10⁶) |
| `chunked_dedicated_slot/scheduler.pm` | ~4.2×10¹⁷ | ~1.3×10⁴ (documented exact) |
| `no_chunking/scheduler.pm`            | ~8.4×10¹⁷ | ~2×10⁴ |

### Declared state space (exact range products)

The variants share a skeleton and differ only in which per-record and
instrumentation variables exist.

**`chunked`** (28 variables) — richest: it adds a real admission queue
(`st ∈ {empty,waiting,running}` per record) and dual arrival instrumentation.

| group | # vars | values/var | subtotal |
|---|---|---|---|
| `t`, `ad_v/b1/b2`, `v_gap`, `v_maxgap`     | 6 | 11 | 11⁶ |
| `stage`, `pp_·`, `bk_·`, `preempts`         | 8 | 7  | 7⁸  |
| `oo_·`, `v_preempts`, `peak_conc`           | 5 | 4  | 4⁵  |
| `st_v/b1/b2`                                | 3 | 3  | 3³  |
| `n_lp`, `n_lo`                              | 2 | 5  | 5²  |
| `lp_before/after_v`, `both_before/after_v`  | 4 | 2  | 2⁴  |

Product = `11⁶·7⁸·4⁵·3³·5²·2⁴` ≈ **1.1 × 10²⁰**.

**`chunked_dedicated_slot`** (23 variables) — no queue (`st` absent; an evicted
request recomputes in place), a single `n_long` counter + 3 timing bools:
`11⁶·7⁸·4⁵·5·2³` ≈ **4.2 × 10¹⁷**.

**`no_chunking`** (24 variables) — identical to `chunked_dedicated_slot` plus the
one `hog` bit (decodes stall while a whole-prompt prefill hogs the iteration), so
exactly **2×** ≈ **8.4 × 10¹⁷**.

### Reachable state space

Declared → reachable collapses by ~10¹³–10¹⁵, from four structural facts:

1. **Determinism in the arrivals.** Each iteration has only 3 arrival outcomes
   (`none / short / long`) for the two dedicated-slot variants, 5 for `chunked`
   (`none` + prompt∈{S,L} × output∈{S,L}), over 10 iterations; everything
   downstream is deterministic.
2. **Only 2–3 request shapes.** Prompts `pre ∈ {1,3}`, outputs `dec ∈ {2,3}`
   (victim `1/3`), so a record's reachable `(pre,dec,blk)` is a few dozen
   lifecycle configs, not the declared `7·4·7 = 196`.
3. **Correlated / capped counters.** `adm ≤ t`, `blk` tracks sequence progress,
   gap counters advance only on a stall, feature counters are monotone and
   saturating.
4. **Bounded concurrency** (≤3 occupied records) caps how much history the
   records can hold at once.

**`chunked_dedicated_slot` ≈ 1.3 × 10⁴** — documented in its `NOTES.md` ("Small
enough for exact model checking (~13k states)") at `POLICY ∈ {0,1}, KV_CAP=8,
CHUNK_BLK=1, T_V=3`. This is the anchor for the other two.

**`no_chunking` ≈ 2 × 10⁴** — same skeleton as the anchor, adjusted by: the `hog`
bit (≲ ×1.4, one frozen bit of history through the service stages); eager prefill
collapses a whole prompt in one step, *removing* intermediate `pre=2,1` configs
(× ~0.7); but the resulting decode stalls spread `v_gap/v_maxgap` over more values
(× ~1.5). Net ≈ ×1.5.

**`chunked` ≈ 2 × 10⁵ (10⁵–10⁶)** — larger than the anchor at its exact-checking
config (`N_SLOTS=2, KV_CAP=8, CHUNK_BLK=3, ADM_POLICY=0, T_V=3`): a live waiting
queue + `N_SLOTS` admission add `st` states (× ~3); four arrival shapes vs two
enrich per-record `(pp,oo,bk)` (× ~1.7); dual `n_lp × n_lo` + four timing bools vs
one counter + three bools multiplies the feature block (× ~6 after correlation);
`CHUNK_BLK=3` prefills a long prompt in one iteration, partly offsetting
(× ~0.7). Net ≈ ×15–20 over 13k.

Unlike `incast`/`fqcodel`, these three are **exact-model-checked** by the repo's
own scripts (PRISM, e.g. `chunked/run_study.sh`,
`chunked_dedicated_slot/run_case_study.sh`), so their reachable counts are
directly computable — `chunked_dedicated_slot`'s is already confirmed at ~13k,
and the `chunked`/`no_chunking` figures (structural extrapolations from that
anchor) could be pinned down exactly by building them. They carry more
uncertainty than the exact declared products.

---

## Method notes

- **Declared** numbers are exact products of the declared ranges; only rounding
  is approximate.
- **Reachable** numbers are structural estimates from the model dynamics (forced
  starts + determinism for incast; list invariants for fqcodel; arrival
  determinism + shape/counter invariants for the schedulers). For `incast` and
  `fqcodel` an explicit build is intractable at these sizes, which is why the
  study uses simulation / reinforcement learning rather than exact model
  checking. The `llm_batch_scheduler/` variants are small enough to build, so
  those reachable figures are confirmable (and `chunked_dedicated_slot`'s ~13k is
  already reported by the repo).
- For `incast.pm`, all figures assume the certification corner
  `M=16, WIN=96, SLEN=8, BUF=32, THRESH=8`; other points in the assumption box
  scale as described above (driven mainly by `WIN`).
- For the `llm_batch_scheduler/` variants, reachable figures assume the
  exact-checking configs from the repo's run scripts (`T=10`, `T_V=3`, `KV_CAP=8`;
  `CHUNK_BLK=1` dedicated / `3` chunked / eager for no-chunking; `N_SLOTS=2` for
  chunked). The probability constants (`p_arr`, `p_long`, …) do not change *which*
  states are reachable, so the reachable count is the same for any values in
  `(0,1)`.

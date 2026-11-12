<!-- Independent audit by a separate agent, 2026-11-11, of commit 4850ee9 plus the doc edits made before it. The corrections it supports are applied in docs/notes/case-study-fabric-scaling.md. Its scratch scripts (pilot_check.py, restart_check.py, loomlike.py) were in /private/tmp and are not kept. Line numbers refer to the note before the corrections. -->

# Audit: fabric scaling case study (`docs/notes/case-study-fabric-scaling.md`, commit 4850ee9 + uncommitted doc edits)

Paths are relative to `/Users/jkai/buffy-prism/.claude/worktrees/gallant-wiles-3cd56c` unless absolute.
"Note" = `docs/notes/case-study-fabric-scaling.md`. Scratch scripts and logs of every rerun are in
`/private/tmp/claude-501/fabric-audit/`.

## 1. Overall verdict

The study's core scaling claims hold: the tables match the raw `jsonl` files, the model implements what
the note describes, an independent oracle agrees with the simulator (also at the study's own base
configuration, which I added), simulation cost is close to linear, and the RNG fix is correct. Three
conclusions do not follow from the evidence and should be changed before the note is cited:

1. **The RESTART "blow-up" is a defect in `expected_success`, not a property of the refined importance.**
   The pilot estimator is biased low at upper levels, which inflated the factor product by 9 orders of
   magnitude. With a consistent estimator RESTART on the refined importance runs normally (I ran it).
2. **Compiler memory at 4,096 hosts is 18.6 GB, not 3.4 GB.** 3.4 GB is the resident set while paging;
   the study's own log records the peak footprint. Memory is not "about linear", and the "175k variables
   in 8 GB" limit is wrong.
3. **The Loom caveat is overstated in mechanism.** On Loom-like sources (hundreds of rare Bernoullis) the
   pre-fix sampler shows no measurable suppression of arrivals; the collapse needs exactly representable
   (power-of-two) probabilities, as in the fabric's ECMP draws. Re-running Loom is still cheap and
   prudent, but "suppresses arrivals in about 1% of steps" is not supported.

Smaller points: the SPRT reading mislabels two floors of the test as findings, the splitting intervals
rest on a handful of runs, and "the answer changes with size" is true only between 16 and 64 hosts.

## 2. Per-conclusion verdicts

| # | Claim (note line) | Verdict | Evidence |
|---|---|---|---|
| 1 | Size table, all 10 rows (102–113) | agree | Every cell recomputed from `experiments/buffy_fabric/results/size_sweep.jsonl`; all match. Reran 16×16×4: P[victim] 0.9973 [0.9948, 0.9988], 2.98 ms/run (note: 0.997, 3.0 ms). Recompiled 8×16×4 and 16×16×4: 0.61 s / 146 MB and 1.53 s / 311 MB (note: 0.6 s / 146 MB, 1.6 s / 287 MB). Default model has 180 variables. |
| 2 | "The answer changes with size, unlike Loom" (130–134, 270–272) | qualify | True from 16 to 64 hosts (NL 2→8 at H=8, NS=2). Beyond that the answer is saturated (P ≥ 0.976) and predictable: lost share ≈ 1 − 56/(4M) gives 0.9931 at M = 2,015 against the measured 0.9927. P[victim] tracks NL, not hosts: 8×8×2 → 8×16×4 doubles the hosts and leaves P at 0.976 → 0.978. So 64 hosts does predict 4,096, and "the ability to analyse the large instance directly is what matters" is not shown by this model. |
| 3 | "Simulation scales linearly" (135–136) | agree, qualified | 158 → 256 ns per host-step over 128× hosts is +62%, about hosts^1.1. "Cache effects" is unverified. 4,096 hosts at 232 ns is in line. |
| 4 | "Compile time grows faster than the model: ×3.4" (138) | agree | 50.78 / 15.06 = 3.37. |
| 5 | "Compiler memory grows about linearly ... Memory, not time, limits size" (139–140); "3.4 GB" (120, 253, 268); "to about 175k variables in 8 GB" (253) | **disagree** | `results/largest_compile.log:25` reports `18592971272 peak memory footprint`; line 9 is the 3.43 GB resident set. I checked that the two agree when nothing pages (16×16×4: RSS 311 MB, footprint 306 MB). DAG nodes grow as about vars^1.4 (20,302 / 103,298 / 279,162 / 666,690 at 692 / 2,732 / 5,452 / 10,892 variables, 34.9 M at 174,092); at 460 B per node (306 MB / 666,690) the 4,096-host DAG needs about 16 GB, which matches the footprint. The 4,096 compile used `--stats`, which adds about 20% at 256 hosts. |
| 6 | "doubling once more would not fit in memory without the change of decision 56" (127) | disagree (wording) | The change of decision 56 is already in. What is meant is the *next step* named there (skip the DAG). And 4,096 hosts already did not fit. |
| 7 | "Far from the threshold, SPRT decides in 12–16 runs ... Near the threshold it needs more (104 runs at 16 hosts)" (146–147) | **disagree with the reading** | 12 is the minimum possible for H+ (ln 99 / ln 1.5 = 11.3) and 104 the minimum for H− (ln 99 / ln(0.92/0.88) = 103.4). At 16 hosts P = 0.0024, the point *farthest* from the threshold; 104 is 104 consecutive zeros. No size-sweep point lies near the indifference region (closest: P = 0.23, 63 runs). |
| 8 | "against 1,203 for the fixed-sample test" (100, 146) | agree, qualified | `size_sweep.py:65` formula reproduces 1,203 (normal approximation). The exact binomial plan needs 1,211. The comparison is one-sided: Wald's approximation gives an expected 1,170 runs at P = 0.10 and about 500 at the edges of the indifference region, so near the threshold SPRT has no advantage. |
| 9 | "At 2,048 hosts the whole test took 6.6 s" (149); "12 runs, in 11 s" (125) | qualify | The time is one batch of 200 runs (`BATCH = 200`), not 12 runs. 12 runs cost 0.4 s and 0.7 s. |
| 10 | Horizon table (160–165) | agree | All cells match `horizon_sweep.jsonl`; 1 − (1 − 0.0192)^rounds column recomputed. |
| 11 | "rounds are nearly independent ... P_T matches 1 − (1 − p)^rounds" (172–173) | agree | From the saved data: per-run variance of the rate over the binomial variance is 1.00, 1.01, 0.96, 0.99, 0.93, 0.96 (se 0.04–0.10); P_T against the independent value has z = 0.0, 0.2, 0.2, −0.3, 1.5, 1.1. |
| 12 | "the fabric drains between rounds" (172) | disagree (wording) | Rerun at 256 hosts, 3,000 runs: at step 60 the aggregator's port is non-empty in 96% of runs (mean 2.9 packets); the spine ports to leaf 0 are back at their steady state (mean 1.3) by about step 50. The victim's path drains; the fabric does not. This is why incast loss per round rises from 898.68 to 898.92 with more rounds. |
| 13 | "For rates, the work stays constant" (170) | agree | Follows from independence: 1.96²(1−p)/(0.01p) ≈ 19,600 rounds ≈ 1.18 M steps. The spread 1.08–1.19 M is the sampling error of the variance. |
| 14 | SPRT at T = 1,800 needs most runs (175–176) | agree | 23 runs at T = 60 is again the floor (ln 99 / ln(0.55/0.45) = 22.9). |
| 15 | Rare-event table arithmetic (195–199) | agree | 62 M runs, 10,636 s, 6,280 s, 3,910 s, 14,476 s, ratios 1.7 / 2.7 / 0.7 all reproduce from `rare_event.jsonl`. |
| 16 | "The three splitting estimates agree with each other and with Monte Carlo's interval" (203) | agree | Pooled estimate of the note's four: 5.76·10⁻⁶ ± 0.41·10⁻⁶, homogeneity χ² = 3.3 on 3 df (p = 0.35). Monte Carlo against fixed effort: z = −1.4. With my four reruns: 5.78·10⁻⁶ ± 0.35·10⁻⁶, χ² = 7.2 on 7 df. |
| 17 | Splitting intervals are "normal intervals from per-run estimates" (201) | qualify | They are, but RESTART's per-run estimates are extremely heavy-tailed. In my 200 s reruns the single largest run carried 14–19% of the sum, the top 5 carried 39–51%, the top 20 carried 76–83% (per-run CV 123). The note's 794,000 runs had 556 non-zero. Nominal 95% coverage cannot be assumed. |
| 18 | "fixed effort about 2.7× faster than Monte Carlo, RESTART about 1.7×" (219–220) | qualify | Point values are right; the ordering is not established. Each uses a half-width squared from heavy-tailed data. Monte Carlo's time uses RESTART's estimate for P (`rare_event.py:127`) and the first run's 172 µs per run; the second run measured 147 µs. With 147 µs the ratios are 2.3 and 1.5. My RESTART rerun with the note's factors extrapolates to 5,900 s (note: 6,280 s). "About 2×, uncertain by a factor of 1.5" is what the data supports. |
| 19 | "The pilot's level probabilities are 0.0075, 0.27, 0.23, 0.14, 0.085 and 0.039 ... Each further level cuts the probability by 4 to 25 times" (222–224) | **disagree** | Their product is 2.1·10⁻⁷, 28 times below the note's own estimate of P. The last three are artefacts of the pilot estimator (see error 1). The consistent values from my 256 pilots are 0.0073, 0.29, 0.28, 0.24, 0.23, 0.18 (product 5.96·10⁻⁶): each level cuts by 3.4 to 5.5 times. |
| 20 | "the estimate's variance comes from the spread over entrance states" (226–227) | agree | Supported indirectly: pilot weight and pilot success fraction are strongly correlated, which is exactly what biases the unweighted mean. |
| 21 | "Refining the importance made things worse, and broke RESTART"; "RESTART's cost per run is unbounded unless the importance is close to monotone" (228–237, 257) | **disagree** | See error 1. With the refined importance and weighted pilot estimates the factor product is 4.9·10⁴ (14 thresholds). RESTART then ran 582,000 runs in 240 s at 167 steps per run and gave 8.2·10⁻⁶ [5.3, 11.1]·10⁻⁶, extrapolating to about 2,950 s for ±10%: faster than every row of the note's table. Killing retrials on down-crossing is what RESTART is designed for. |
| 22 | Fixed effort with the refined importance is slower than Monte Carlo (238–240) | qualify | 0.7× is within the noise of 1×; one run of 800 estimates. The thresholds came from the biased pilot (36 of 102); the consistent one picks 12–14. |
| 23 | Pilot averaging "now averages only over pilots that reached the level" as a fix (207–210) | **disagree** | It is less biased than before, not unbiased. See error 1. `min_pilots` makes it worse in one respect: more pilots do not converge to the right value. |
| 24 | RNG fix is "exact" (77–79) | agree | Exact up to the 2⁻⁴⁵ grid, like any double-based inverse CDF. Reran `tests/test_native_precision.py`: |z| = 1.89, arrivals z = 1.29. My independence check (200,000 steps, 64 uniform(0,3) + 64 Bernoulli): sum variance 79.91 (expect 80), 8 pairwise χ²(15) between 11.2 and 19.3, including pairs across refresh points. |
| 25 | "|z| = 1.9 with the fix and 346 without it" (80–81) | agree | Reproduced both (patched copy in scratch: the last draw is 0 in every run, z = 346). |
| 26 | "Loom ... suppresses arrivals at the later cores in about 1% of steps" (82–85); "should be re-run before they are cited" (279–281) | **disagree with the mechanism**, agree re-running is cheap | See error 3. |
| 27 | Oracle agreement, 12 configurations, |z| ≤ 2.25 (56–61) | agree, qualified | Log parsed: 108 comparisons, 13 degenerate (both sides identical), the other 95 have mean z² = 1.07 and 4% above 2. None of the 12 uses B = 16 or 4:1 oversubscription. I ran the oracle there: 3×8×2 gives victim 0.2314, loss 0.555, oLost 9.64 (table 0.2302, 0.5548, 9.62); 2×8×2 gives P(odrops ≥ 1) = 0.00752 (pilot 0.0075) and victim 0.0028 (table 0.0024 [0.0015, 0.0036]). In the tail, the oracle gives P(odrops ≥ 4) = 1.20·10⁻⁴ (84 hits in 700,000 runs, 95% interval about [0.96, 1.49]·10⁻⁴) against the note's 1.38·10⁻⁴ and 1.42·10⁻⁴ and my weighted pilots' 1.43·10⁻⁴. |
| 28 | Structured vs unrolled, "identical successors on 960 random-walk states each" (62–65) | qualify | For steps too large to enumerate, `tests/test_native_structured.py:77-79` compares via `step(s, e, u)`, the single-uniform path that the fix does not cover. On the 4×4×4 variant (about 95 bits per step) the later sources are compared almost only on their first outcome. |
| 29 | Model matches its description (17–52) | agree | Read `fabric.buffy` against the note and the oracle: ECMP per packet / per flow, fan-in (NL−1)·H−1, H = 4·NS in every sweep row, rotation as two guarded passes, drop accounting at all three stages, per-round reset. One rotation draw is shared by all ports of a stage (harmless, undocumented). Victim arrivals refused by a full NIC are not counted as losses (both in model and oracle). |
| 30 | Infeasibility bounds (258–260) | agree | 11⁷ = 1.95·10⁷, 11²³ = 8.95·10²³; 18,436 sources at 4,096 hosts matches 4 per host + 2 per leaf-spine pair + 4. These are arguments, not measurements; "no" for exact conditioning should read "no (not attempted)". |
| 31 | Build (clang) scales: "yes" (254) | qualify | 31 s for 12.8 MB at 2,048 hosts, 113 s for 28 MB at 4,096: 3.7× the time for 2.2× the C. |
| 32 | Conclusion "What scales" (264–269) | agree up to 2,048 hosts | The 4,096-host compile needed more than twice the machine's memory. |
| 33 | Conclusion "The limits are elsewhere": rare events (275–276) | qualify | The measured limit was the level-selection code. With it corrected, the refined importance is the best configuration I measured, on thin evidence (one 240 s run). |

## 3. Errors found, ranked

### 1. `expected_success` is biased; the RESTART diagnosis is wrong (high)

`src/netmdp/sim/splitting.py:47-54` averages each level's success fraction over the pilots that reached
the level, each pilot weighted equally. A fixed-effort pilot that reaches level l through one "cold"
entrance state counts as much as one that reaches it with hundreds of "hot" ones. Since a pilot's weight
(product of its earlier fractions) and its next fraction are positively correlated, the unweighted mean
underestimates every upper level, and the error compounds per level.

The identity that exposes it: the level probabilities must multiply to P. They do not.

| importance | ∏ p_up (note's pilot) | 1/∏ | factor product | 1/P |
|---|---|---|---|---|
| derived, 6 levels | 2.1·10⁻⁷ | 4.7·10⁶ | 4.19·10⁶ | 1.7·10⁵ |
| refined, 102 levels | 3.1·10⁻¹⁵ | 3.2·10¹⁴ | 5.3·10¹³ | 1.7·10⁵ |

Confirmed by rerun (`pilot_check.py`, 2×8×2, THRESH = 6):

| estimator | derived (256 pilots × 1,024): p_up | ∏ | factor product | refined (64 × 256): factor product |
|---|---|---|---|---|
| in the code (unweighted over reaching pilots) | 0.0073, 0.29, 0.25, 0.18, 0.11, 0.064 | 6.9·10⁻⁷ | 1.6·10⁶ | 4.3·10¹⁰ |
| before the study (zeros for dead pilots) | 0.0073, 0.29, 0.25, 0.17, 0.10, 0.049 | 2.6·10⁻⁷ | 2.2·10⁶ | 3.2·10⁸⁷ |
| weighted by the pilot's fixed-effort weight | 0.0073, 0.29, 0.28, 0.24, 0.23, 0.18 | 5.96·10⁻⁶ | 1.6·10⁵ | 1.8·10⁴ |

The weighted estimator is p_l = Σᵢ Wᵢ,l fᵢ,l / Σᵢ Wᵢ,l with Wᵢ,l = ∏_{j<l} fᵢ,j; its product equals the
mean fixed-effort estimate by construction.

Consequences:
- RESTART with the refined importance expected 5.3·10¹³ × 7·10⁻⁶ ≈ 4·10⁸ goal hits *per run*. That, not
  non-monotonicity, is why no batch of 2,000 finished. With the weighted design (`restart_check.py hand
  512 256 240 2000`): thresholds [11, 12, 13, 14, 15, 24, 28, 42, 57, 60, 74, 89, 91, 93], product
  4.9·10⁴, 582,000 runs in 240 s, estimate 8.2·10⁻⁶ ± 35%.
- RESTART with the derived importance was over-split 25× (26 goal hits per root run on average). The
  effect on efficiency is modest: my 200 s reruns extrapolate to 5,900 s with the note's factors and
  3,650 s with [134, 4, 4, 4, 5, 7]; the difference is within noise.
- Fixed-effort rows are unaffected by the factors, but the refined row's 36 thresholds came from the
  biased pilot.
- Is it the importance function, the factor rule, or a bug? A bug in the estimator. The rounding rule
  with additive carry is secondary: it moves the product by −12% (derived) and by a factor of 5–6 down
  (refined), against 9 orders of magnitude from the estimator. Factor placement (factor at a threshold =
  1 / probability of reaching it from the level below) matches the published description (Budde et al.:
  effort ⌈N/K⌉ so that one run advances per level on average, RESTART spawning f(l) − 1 retrials on
  entering level l). The published method uses one sequential pass, not an average over pilots; the
  averaging is this repository's extension and is where the bias enters. The same literature reports
  expected-success efforts for RESTART that were too small or too large in practice.

### 2. Compiler memory at 4,096 hosts (high)

Stated in three places: note lines 120, 139, 253, 268; `docs/notes/buffy-compiler-design-decisions.md:460`;
`buffy/docs/compilation/sections/backends.tex:142`. See verdict 5. In addition, the watchdog in
`experiments/buffy_fabric/try_largest.sh:14-16` polls `ps -o rss`, which cannot exceed physical memory
minus what is compressed, so the 6 GB limit could never fire for the right reason. Whether the 2.4 GB at
2,048 hosts is a true footprint I could not rerun; it fits the 26–34 KB per variable of the smaller
sizes, so it probably is. That makes the last doubling about 7.6× in memory, not 2×.

### 3. The Loom caveat's mechanism (medium)

The note derives "about 1% of steps" by counting bits (4–5 arrivals at 9–10 bits exhaust 45). I measured
it instead (`loomlike.py`: K Bernoulli(λ/K) sources in one step, patched pre-fix copy against the fixed
runtime):

| sources, rate | P(N ≥ 5), P(N ≥ 6), P(N ≥ 7) exact | fixed | pre-fix |
|---|---|---|---|
| 512, λ = 1.3 (400,000 steps) | 0.01055, 0.00219, 0.00039 | 0.01063, 0.00225, 0.00047 | 0.01062, 0.00219, 0.00042 |
| 512, λ = 1.7 (400,000) | 0.02937, 0.00788, 0.00183 | 0.02929, 0.00787, 0.00177 | 0.02959, 0.00795, 0.00179 |
| 512, λ = 1.0, p = 2⁻⁹ (2,000,000) | 0.00362, 0.00058, 0.00008 | 0.00363, 0.00059, 0.00009 | 0.00353, 0.00055, 0.00008 |
| 512, λ = 2.0, p = 2⁻⁸ (2,000,000) | 0.05230, 0.01635, 0.00444 | 0.05240, 0.01635, 0.00441 | 0.05233, 0.01633, 0.00449 |

Steps with 9–12 arrivals occur pre-fix, and the first and last quarters of the sources have the same
mean. No suppression. The reason: dividing the residual by a non-dyadic 1 − p rounds to 53 bits each time
and refills the low bits with deterministic but well-mixed digits, whereas dividing by 1/4 is exact and
shifts real bits out. The collapse therefore needs power-of-two probabilities (the fabric's uniform draws
over 2, 4, 8, 16 spines and hosts). The largest deviation I saw is −2.1σ on P(N ≥ 5) in the p = 2⁻⁹ row,
i.e. at most a few percent of a tail probability.

This is a proxy, not the Loom model. For Loom's Family A (P ≈ 0.38 against 0.29/0.31) an effect of this
size cannot change a decision. Family B (H−, zero starved windows in 206,528 runs) is the direction in
which a suppression of bursts would be anti-conservative, so that is the family worth re-running; the
64- and 128-core rows are essentially unexposed either way.

Related: the Bernoulli half of `tests/test_native_precision.py` (line 65) has no power. Pre-fix, the
arrivals are drawn before the uniforms and stay correct (mean 0.6419 per step against 0.64); only the
uniform half fails.

### 4. SPRT reading (medium)

Verdict 7. The size sweep contains no test near its threshold, so "runs depend on the distance from the
threshold, not on the model's size" is shown only for the two floors and one intermediate point.

### 5. Heavy-tailed splitting estimates (medium)

Verdicts 17–18. Per-run estimates are not saved, so the note's intervals cannot be re-examined.

### 6. Smaller items (low)

- "the fabric drains between rounds" (verdict 12).
- `results/largest.jsonl` was edited by hand (`largest_run.py` writes no `defines`, compile or RSS
  fields) and records THRESH = 2, not the sweep's 10. P[victim] and the loss share do not depend on
  THRESH.
- The note's header for axis 3 says P ≈ 5·10⁻⁶ (line 182); everything else says 6·10⁻⁶. Pooled: 5.8·10⁻⁶.
- "102 importance values" (229): the refined importance ranges over 0..118; 102 is the goal's value.
- `rare_event.jsonl` line 1 carries `speedup_time: 11.3`, which compares Monte Carlo's time for ±10% with
  RESTART's time for ±26%. Not used in the note, but it is in the raw results.
- `JaniModel.step(s, e, u)` (`jani_native.py:1054`, `1216`) still collapses on dyadic many-source steps.
- TeX, `backends.tex`: "The two forms agree ... of every enumerable destination, on every example" is
  accurate as worded, but for the fabric no step is enumerable (verdict 28).
- TeX, `elaboration.tex` new paragraph and decision 56's first two bullets: consistent with the note and
  with what I could check (byte-identical output and the 43 s → 5.5 s figure I could not check).

## 4. Refinements (quoted so they can be applied)

Note, line 120: replace "the compiler's peak resident memory was 3.4 GB on an 8 GB machine" with "the
compiler's peak memory footprint was 18.6 GB (with `--stats`), of which 3.4 GB was resident on this 8 GB
machine".

Note, lines 126–127: replace with "Compilation is what stops it: at 4,096 hosts the compiler already
needs more than twice this machine's memory. Larger sizes need the next step of decision 56 (not
building the unrolled DAG)."

Note, lines 139–140: replace with "Compiler memory grows about linearly up to 2,048 hosts (2.4 GB at
87,000 variables) and then jumps to 18.6 GB at 174,000: the step DAG grows roughly as variables^1.4
(0.67 M nodes at 256 hosts, 34.9 M at 4,096)."

Note, line 253, first cell: "to about 87k variables in 8 GB; 174k compiles only by paging (18.6 GB
footprint); superlinear". Same number in line 268 ("at 18.6 GB and 21 minutes, is beyond this machine's
memory").

Decision 56 (line 460) and `backends.tex:142-143`: "At 4,096 hosts it needs 18.6 GB (3.4 GB resident on
an 8 GB machine, hence 21 min of wall time for 4.5 min of CPU)."

Note, lines 146–148: replace with "At every size from 48 hosts up the test stops at its minimum of 12
runs (P ≈ 1); at 16 hosts it stops at the minimum for H−, 104 runs without a loss. Only 3×8×2 (P = 0.23,
63 runs) is an intermediate case. None of these sizes puts P near the threshold, where the SPRT's expected
run count (about 1,170 at P = 0.10) equals the fixed-sample test's 1,203."

Note, lines 130–134 and 270–272: add "Above 64 hosts the answer is saturated and follows from the port's
capacity (lost share ≈ 1 − 56/(4M)). The model shows that small sizes can mislead, not that the largest
size holds a surprise."

Note, lines 171–173: replace "the fabric drains between rounds" with "the victim's path is back at its
steady state about 10 steps before the next round (the aggregator's own port is not: it is non-empty at
the boundary in 96% of rounds)".

Note, lines 207–210 (pilot averaging): replace the claim of a fix with "This is still biased low at the
upper levels: pilots are weighted equally, whatever their weight. The level probabilities must multiply
to P; here they multiply to 2·10⁻⁷."

Note, lines 222–224: "The level probabilities are about 0.0075, 0.29, 0.28, 0.24, 0.23 and 0.18 ...
Each further level cuts the probability by 3.4 to 5.5 times".

Note, lines 228–237 and table row 198: replace the RESTART diagnosis with "RESTART did not finish
because the factors were wrong: the pilot estimator's bias compounds over 102 levels and gave a factor
product of 5.3·10¹³ against 1/P ≈ 1.7·10⁵, i.e. about 4·10⁸ goal hits per run. With factors from
weighted pilot estimates (product 4.9·10⁴) RESTART runs at 167 steps per run." Delete "So RESTART's cost
per run is unbounded unless the importance is close to monotone along trajectories."

Table row "Rare events" (257) and conclusion bullet (275–276): drop "RESTART's effort unbounded"; the
supported statement is "about 2× over Monte Carlo with the derived importance; the refined importance has
not been measured with correct factors beyond one short run".

Note, lines 82–85: replace with "Who else is affected: models whose steps make many draws with
power-of-two probabilities. On Loom-like steps (512 Bernoulli sources, rate 1.0–2.0) the pre-fix sampler
reproduces the distribution of the number of arrivals to within sampling error over 2 million steps. The
Loom SPRT results are being re-run for completeness." Soften line 279–281 accordingly.

Note, line 201–204: add "RESTART's per-run estimates are heavy-tailed (a few runs carry most of the
sum), so its interval and the extrapolated times are indicative only."

## 5. Follow-up work, ranked

1. **Fix `expected_success` and redo axis 3** (about 10 lines; 1–2 h of compute). Use the weighted
   estimator, assert that the factor product is within, say, 10× of 1/P̂ from the same pilots, and check
   the time budget inside a batch. Then rerun all four splitting rows. It decides whether the refined
   importance helps, which the note currently answers the wrong way round.
2. **Measure compiler memory by footprint at every size and fix the watchdog** (minutes; the 4,096 point
   needs a 32 GB machine or the DAG change). Without it the size limit in the note, decision 56 and the
   TeX is wrong by a factor of two in hosts.
3. **Replicate the rare-event comparison** over 5–10 seeds, save per-run estimates, and report an interval
   on each speed-up (half a day of compute). One run per method cannot order 1.7× and 2.7×.
4. **A size sweep whose answer is not saturated at scale** (hours). Hold the per-port load near critical
   as the fabric grows (for example WIN proportional to the fan-in), so that P stays between 0.05 and
   0.95 at 2,048 hosts and the SPRT is exercised near its threshold on a large model. That is the claim
   reviewers will actually test.
5. **Loom**: re-run Family B at 256 and 512 cores, and compare pre-fix and fixed runtimes on the real
   model at one size (about 1 h). Replaces an estimate with a measurement.
6. **Tests** (1–2 h): draw the Bernoulli sources after the dyadic uniforms in
   `test_native_precision.py`; add a pairwise-independence check; make `test_native_structured.py` use the
   refreshed path or several uniforms; either fix or document `JaniModel.step`.
7. **Oracle**: add the base configuration (B = 16, 4:1) and a mid-tail quantity such as P(odrops ≥ 4)
   (minutes).
8. **Other users of `expected_success`** (`tests/native_splitting_experiment.py`,
   `native_policy_experiment.py`, `native_crossover_experiment.py`): their estimates stay unbiased, but
   any efficiency figures taken from them should be re-measured after item 1.
9. Exact binomial fixed-sample size (1,211) in place of the normal approximation; report SPRT time for
   the runs used, not for the batch.

## 6. What I could not check

- The 2,048- and 4,096-host compiles and runs (by constraint). In particular whether 2.4 GB at 2,048 hosts
  is a full footprint.
- The actual Loom models; the pre-fix test used a synthetic step with the same kind of sources.
- "The note in the shared folder" on affected earlier results.
- Decision 56's byte-identical output and the 43 s → 5.5 s figure; the first, fixed-order arbitration
  model; the pre-fix uplink occupancies 17.5 / 5.5 / 9.1 / 5.5.
- The original expected-success pseudo-code (SETTA 2017 / Sci. Comput. Program. 2019): no open copy was
  reachable. I relied on the description in Budde et al.'s fault-tree paper (arXiv 1910.11672) and the
  RESTART definition in Budde & Hartmanns (TACAS 2021).
- Coverage of the note's own splitting intervals (per-run estimates were not saved).
- The built PDF `buffy-compilation.pdf`; I read the TeX sources and their diff.
- Chen 2009, Chen & Xu 2013, Ji et al. 2013 and the HotNets related-work PDFs: nothing in this note
  depends on them, so I did not review them.

Side effects of the audit: nothing in the repository or `buffy/` was modified. My first simulator builds
went to the default cache `~/.cache/netmdp-jani`; later ones to
`/private/tmp/claude-501/fabric-audit/cache`.

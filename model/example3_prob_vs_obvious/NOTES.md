# Example 3 — probabilistic assumptions vs "100%-only"

Same contention point and dynamics as `example2_desync_short_bursts/` (all
uplinks, `MPP=2` flows each, short flows, shallow buffer `BUF=32`, bad event
`Q = odrops ≥ THRESH` with `THRESH=8`). The model here is generated with
`MMAX=24` (12 uplinks) so the extreme box below (up to 12 uplinks) fits; for
`M=16` it gives identical results to example 2's `MMAX=20` model (idle uplinks
never start).

Purpose: make the paper's methodological point precise — a **probabilistic**
tool finds *mild, non-obvious* assumptions under which loss is likely-but-not-
certain, whereas restricting to **100% (certainty)** forces you onto *obvious,
extreme* assumptions. Concretely we give three boxes.

## The key structural observation: the risk is 0/1 in load, gradual only in sync
Hold the box's other parameters and nudge one:

```
              P[Q] at M=16, WIN=96, SLEN=8  =  0.54
  fan-in:     M=14 -> 0.14      M=16 -> 0.54      M=18 -> 0.99     (±one uplink)
  burst:      SLEN=7 -> 0.11    SLEN=8 -> 0.54    SLEN=9 -> 0.99   (±one packet)
  sync window: WIN=96 -> 0.54   WIN=112 -> 0.22   WIN=120 -> 0.14  (gradual)
```

`P[Q]` is **sharp in the load parameters** `M` and `SLEN` (change either by one
step and it snaps to ~0 or ~1) but **gradual in the synchronisation window**
`WIN`. So the region where `Q` is *genuinely uncertain* (neither rare nor
certain) is a thin shell **along the synchronisation axis** — which is exactly
the parameter an operator does *not* control. That is why the probabilistic
boxes below range `WIN` (and `SLEN`), not `M`.

## Box P1 — probabilistic, 1-D (the sync window)
```
A_P1 ≡ (M = 16) ∧ (SLEN = 8) ∧ (96 ≤ WIN ≤ 120)
```
8 uplinks, 8-packet flows, spread over 12–15× the flow length. Every point in
the uncertain band:

| WIN | WIN/SLEN | P[Q] (oracle) |
|---|---|---|
| 96  | 12× | 0.536 |
| 104 | 13× | 0.345 |
| 112 | 14× | 0.220 |
| 120 | 15× | 0.142 |

box range: **`P[Q] ∈ [0.14, 0.54]`** — no point certain, no point rare.

## Box P2 — probabilistic, 2-D (burst length AND sync window)  ← preferred
```
A_P2 ≡ (M = 16) ∧ (8 ≤ SLEN ≤ 9) ∧ (116 ≤ WIN ≤ 124)
```
Ranges **both** `SLEN` and `WIN` — the two things an operator controls *least*
(application response size and how synchronised the responders happen to be),
holding only the fan-in fixed.

| P[Q] (oracle) | WIN=116 | WIN=120 | WIN=124 |
|---|---|---|---|
| **SLEN=8** | 0.176 | 0.142 | 0.115 |
| **SLEN=9** | 0.550 | 0.469 | 0.399 |

box range: **`P[Q] ∈ [0.12, 0.55]`** — least-favorable corner `(SLEN=8, WIN=124)`
= 0.115, most-severe corner `(SLEN=9, WIN=116)` = 0.550. Every one of the six
points is a genuine coin-flip-ish risk. (This box is narrow in `WIN`, and holds
only two `SLEN` values at this fan-in, precisely because of the 0/1 observation
above. Boxes P3/P4 below trade fan-in for a wider `SLEN` range.)

## Box P3 — like P2 but THREE SLEN values (same fan-in, more de-sync)
```
A_P3 ≡ (M = 16) ∧ (10 ≤ SLEN ≤ 12) ∧ (184 ≤ WIN ≤ 192)
```
Same 8-uplink fan-in as P1/P2, but **three** burst lengths in-band and an even
larger de-sync (15–19× the flow length). SLEN 10–12 ≈ 15–18 KB (query/SRU).

| P[Q] (oracle) | WIN=184 | WIN=192 |
|---|---|---|
| **SLEN=10** | 0.138 | 0.110 |
| **SLEN=11** | 0.316 | 0.262 |
| **SLEN=12** | 0.559 | 0.483 |

box range: **`P[Q] ∈ [0.11, 0.56]`** — corner `(SLEN=10, WIN=192)` = 0.110,
corner `(SLEN=12, WIN=184)` = 0.559.

## Box P4 — FOUR SLEN values (lower fan-in)
```
A_P4 ≡ (M = 12) ∧ (13 ≤ SLEN ≤ 16) ∧ (196 ≤ WIN ≤ 204)
```
Drops to 6 uplinks, which softens the SLEN transition enough to hold **four**
burst lengths in-band (de-sync 12–16×). SLEN 13–16 ≈ 20–24 KB (storage SRU).

| P[Q] (oracle) | WIN=196 | WIN=204 |
|---|---|---|
| **SLEN=13** | 0.137 | 0.116 |
| **SLEN=14** | 0.244 | 0.210 |
| **SLEN=15** | 0.379 | 0.333 |
| **SLEN=16** | 0.532 | 0.477 |

box range: **`P[Q] ∈ [0.12, 0.53]`** — corner `(SLEN=13, WIN=204)` = 0.116,
corner `(SLEN=16, WIN=196)` = 0.532. (A 5th value, SLEN=17, only fits if the
band is widened to ~[0.08, 0.63].)

**How many SLEN values fit is set by the fan-in.** The 0/1 sharpness scales with
`M` (more senders → sharper transition), so the width of the in-band `SLEN`
range trades directly against fan-in: `M=16` → 3 values (P3), `M=12` → 4 (P4),
`M=10`/`M=8` → 5 — at the cost of fewer uplinks and a larger `WIN` for the same
de-sync. This is the same sharpness observation, quantified.

## Box E — extreme / obvious (certain incast)
```
A_E ≡ (20 ≤ M ≤ 24) ∧ (0 ≤ WIN ≤ 24) ∧ (8 ≤ SLEN ≤ 12)
```
10–12 uplinks whose flows arrive within ~2–3 flow-lengths (nearly synchronised).
Both corners `P[Q] = 1.0000` → **certain overflow everywhere.** This is textbook
incast: many senders, synchronised → the receiver drowns. Provable — and
obvious.

## The contrast (the paper's point)
| | `A_E` (extreme / obvious) | `A_P1` / `A_P2` (mild / non-obvious) |
|---|---|---|
| in words | 10–12 uplinks, nearly synchronised | 8 uplinks, short flows, de-synchronised 12–15× |
| `P[Q]` | `= 1` everywhere | `∈ [0.12, 0.55]` everywhere |
| certify `A ⟹ Q` (∀ / verification) | **succeeds** — but the assumption is the obvious one | **fails** — no point is certain |
| find a counterexample (∃) | trivially yes | yes, but same verdict as a 12%-risk point → can't rank |
| `P[Q \| A]` (probabilistic) | 1 (uninteresting) | **12–55% — the only actionable answer** |

The only assumptions a 100%-method can certify are `A_E`-shaped extremes; the
realistic de-synchronised regime `A_P` is invisible to it and is exactly where a
quantified `P[Q|A]` earns its keep.

## Running it
`M` even; use `-simpathlen 8500` (this model is `MMAX=24`). Exact checking is
intractable; use simulation, cross-checked by `python3 incast_sim.py`.
```
# Box P1:
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=16,SLEN=8,WIN=96:8:120 \
      -sim -simmethod ci -simwidth 0.01 -simconf 0.01 -simpathlen 8500
# Box P2:
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=16,SLEN=8:1:9,WIN=116:4:124 ...
# Box P3 (3 SLEN values):
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=16,SLEN=10:1:12,WIN=184:4:192 ...
# Box P4 (4 SLEN values):
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=12,SLEN=13:1:16,WIN=196:4:204 ...
# Box E:
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=20:2:24,WIN=0:8:24,SLEN=8:2:12 ...
```
Note: a `±1e-4` CI is only feasible for the near-0/1 points (e.g. box E); the
mid-probability box-P points need ~10^8 samples for that width, so use
`simwidth ≈ 0.01` there.

## Validation (PRISM simulation vs oracle)
Corners, `BUF=32, THRESH=8`. Oracle values (n=120k, ±~0.004); PRISM at
`simwidth=0.01` (box E at `0.001`), 99% confidence. They agree within CI.

| box corner | point | oracle | PRISM (±CI) |
|---|---|---|---|
| P1 max | `M=16, WIN=96, SLEN=8`  | 0.536 | 0.541 ± 0.01 |
| P1 min | `M=16, WIN=120, SLEN=8` | 0.142 | 0.145 ± 0.01 |
| P2 max | `M=16, WIN=116, SLEN=9` | 0.550 | 0.545 ± 0.01 |
| P2 min | `M=16, WIN=124, SLEN=8` | 0.115 | 0.120 ± 0.01 |
| P3 max | `M=16, WIN=184, SLEN=12`| 0.559 | _pending_ |
| P3 min | `M=16, WIN=192, SLEN=10`| 0.110 | _pending_ |
| P4 max | `M=12, WIN=196, SLEN=16`| 0.532 | _pending_ |
| P4 min | `M=12, WIN=204, SLEN=13`| 0.116 | _pending_ |
| E  min | `M=20, WIN=24, SLEN=8`  | 1.000 | 1.000 ± 0.001 |

These are the box corners; by monotonicity (increasing in `M`, `SLEN`,
decreasing in `WIN`) they bound every interior point, so each box is certified
as a whole: P1/P2 lie entirely in `[0.12, 0.55]`, E is `1.0` throughout.

# No-chunking (eager whole-prompt prefill) variant

The pre-Sarathi FCFS behavior: a newly admitted prompt is prefilled in one shot,
monopolizing the iteration and **freezing all decodes** that iteration (the
generation-stall / head-of-line-blocking pathology). Identical to
[`../chunked/`](../chunked/) except:

- prefill computes the whole remaining prompt in one iteration (no chunk cap), and
- a `hog` flag stalls every decode while any prefill is in progress.

Purpose: the chunked-vs-eager comparison. Turning chunking off should sharply raise
`P(victim stall)` — the value chunked prefill delivers.

```bash
source ~/buffy-prism-tools/env.sh
PRISM=~/buffy-prism-tools/prism-4.10.1-linux64-x86/bin/prism
# baseline stall probability under eager prefill (compare with ../chunked)
$PRISM scheduler.pm -const POLICY=0,p_arr=0.5,p_long=0.4 \
       -pf 'P=? [ F ("done" & v_maxgap>=SLO_TBT) ]'
```

The focus of the current work is the chunked variant; this variant is intentionally
left as the comparison point and does not yet have its own query suite / notes.

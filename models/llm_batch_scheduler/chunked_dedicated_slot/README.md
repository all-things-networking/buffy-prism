# Chunked scheduler — dedicated-slot variant

An earlier, simpler chunked-prefill model. Here the tracked request runs in its own
batch slot rather than competing for a shared pool of slots through a waiting queue.

This variant is kept for reference. The current model is in
[`../chunked/`](../chunked/), which removes the dedicated slot and adds a real queue;
all current results and the paper assumption come from there. Use this folder only if
you want to compare against the dedicated-slot setup.

Files: `scheduler.pm` (model), `scheduler.props` (queries), `run_case_study.sh`
(runner), `NOTES.md` (its own findings).

Run: `source ~/buffy-prism-tools/env.sh && ./run_case_study.sh`.

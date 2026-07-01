// ============================================================================
//  LLM inference batch scheduler — a GPU worker running continuous batching
//  ---------------------------------------------------------------------------
//  Contention point: one GPU worker serving LLM requests with the realistic
//  vLLM-V1 default stack:
//    * continuous (iteration-level) batching  [Orca, OSDI'22]
//    * a shared, finite KV-cache block pool    [PagedAttention, SOSP'23]
//    * chunked prefill (a knob, default on)     [Sarathi-Serve, OSDI'24]
//    * FCFS admission, with a policy knob for the eviction order (fcfs|priority)
//
//  One DTMC step models the scheduler regaining control; one *iteration* of the
//  engine spans a fixed sequence of stages (see `stage` below). Within an
//  iteration, continuous batching advances ALL running requests by one token
//  simultaneously, so we service them in successive stages (order is
//  immaterial — decode is independent per request; KV pressure is checked once
//  at the end).
//
//  We track one interactive "victim" request (slot v) whose latency we care
//  about, plus 2 background slots (b1,b2). The unit of KV memory is a *block*
//  (PagedAttention's 16-token block). A request's block count `*_blk` equals its
//  current sequence length (prompt loaded + tokens generated so far), so it
//  grows during both prefill and decode.
//
//  Abstractions (kept deliberately small & readable; see NOTES.md):
//    - <=1 background arrival per iteration; if no slot is free it is dropped
//      (bounded concurrency = 3 slots), so queueing/TTFT delay is not modelled.
//    - prompt/output lengths are bundled into a request "class" (short|long),
//      which bakes in a positive prompt<->output length correlation.
//    - preemption recovery = recomputation: the victim/bg must rebuild ALL of
//      its current blocks (`*_pre := *_blk`), so the stall cost grows with how
//      far along the request was (a coarse stand-in for the O(s^2) recompute).
// ============================================================================

dtmc

// ---- horizon & structure --------------------------------------------------
const int T        = 10;   // number of engine iterations (the time horizon)
const int T_V      = 3;    // iteration at which the victim request arrives

// ---- the contended resources ----------------------------------------------
const int KV_CAP   = 8;    // shared KV-cache capacity, in blocks
const int CHUNK_BLK= 1;    // prefill blocks loaded per iteration when chunking

// ---- scheduler knobs (design parameters, not input) -----------------------
const int CHUNKED;         // 1 = chunked prefill (stall-free, vLLM default)
                           // 0 = eager whole-prompt prefill (pre-Sarathi FCFS):
                           //     a prefill hogs the whole iteration -> decodes stall
const int POLICY;          // 0 = fcfs   (evict most-recently-admitted, LIFO)
                           // 1 = priority(victim is high-priority: evict bg first)
                           // (left undefined; supply with -const, default fcfs/chunked)

// ---- request shapes (blocks) ----------------------------------------------
const int VPRE     = 1;    // victim prompt (blocks)   — a short interactive req
const int VDEC     = 3;    // victim output (blocks)
// background short: prompt 1, output 2 ; background long: prompt 3, output 3
// (encoded directly in the arrival commands below)

// ---- input pattern (the request-mix "condition" knobs; sweepable) ---------
const double p_arr;        // P(a background request arrives in an iteration)
const double p_long;       // P(an arriving background request is "long")
                           // (input pattern; left undefined, supply with -const)

// ---- bad-event thresholds (SLOs) & counter caps ---------------------------
const int SLO_TBT  = 3;    // TBT SLO: a victim inter-token gap >= this = stall
const int K_CASC   = 2;    // "preemption cascade" = this many total preemptions
const int WIN        = 2;    // window (iters) around T_V for "long arrived near victim"
const int GAPMAX   = T;    // cap for gap counters
const int NL       = 4;    // cap for long-arrival counter
const int PT       = 6;    // cap for total-preemption counter

// ---- stages within one iteration ------------------------------------------
const int VINJECT = 1;     // inject victim at t=T_V
const int ARRIVE  = 2;     // probabilistic background arrival
const int SETUP   = 3;     // freeze per-iteration flags (hog, peak)
const int SVC_V   = 4;     // service victim
const int SVC_B1  = 5;     // service background slot 1
const int SVC_B2  = 6;     // service background slot 2
const int PREEMPT = 7;     // evict until KV pool fits, then advance the clock

// ===========================================================================
//  Derived state (formulas)
// ===========================================================================
// "in system" = occupying a slot (prefilling, decoding, or holding KV)
formula v_in  = (v_pre>0 | v_dec>0 | v_blk>0);
formula b1_in = (b1_pre>0 | b1_dec>0 | b1_blk>0);
formula b2_in = (b2_pre>0 | b2_dec>0 | b2_blk>0);

// concurrent occupancy and total KV in use
formula occ = (v_in?1:0) + (b1_in?1:0) + (b2_in?1:0);
formula kv  = v_blk + b1_blk + b2_blk;

// which background slot a new arrival takes (lowest free index; 0 = none free)
formula tgt = !b1_in ? 1 : (!b2_in ? 2 : 0);

// prefill chunk each request loads this iteration (whole prompt if not chunked)
formula chunk_v  = CHUNKED=1 ? min(v_pre,  CHUNK_BLK) : v_pre;
formula chunk_b1 = CHUNKED=1 ? min(b1_pre, CHUNK_BLK) : b1_pre;
formula chunk_b2 = CHUNKED=1 ? min(b2_pre, CHUNK_BLK) : b2_pre;

// eviction "score": highest score is evicted first. FCFS => newest (max adm).
// priority => backgrounds get +100 so the victim is only evicted as a last
// resort. A slot holding no KV (blk=0) is never a candidate (score -1).
formula v_score  = v_blk>0  ? v_adm  : -1;
formula b1_score = b1_blk>0 ? (b1_adm + (POLICY=1 ? 100 : 0)) : -1;
formula b2_score = b2_blk>0 ? (b2_adm + (POLICY=1 ? 100 : 0)) : -1;

// convenience for the victim gap update (next gap value, capped)
formula v_gap1 = min(GAPMAX, v_gap+1);

module worker

    // ---- clock & stage ----
    t     : [0..T] init 0;
    stage : [1..7] init VINJECT;

    // ---- victim (slot v) ----
    v_pre : [0..6] init 0;   // remaining prefill blocks to load
    v_dec : [0..3] init 0;   // remaining decode blocks (output) to generate
    v_blk : [0..6] init 0;   // KV blocks currently held (= current seq length)
    v_adm : [0..T] init 0;   // admission iteration (for eviction ordering)

    // ---- background slots ----
    b1_pre: [0..6] init 0; b1_dec: [0..3] init 0; b1_blk: [0..6] init 0; b1_adm: [0..T] init 0;
    b2_pre: [0..6] init 0; b2_dec: [0..3] init 0; b2_blk: [0..6] init 0; b2_adm: [0..T] init 0;

    // ---- per-iteration flag ----
    hog   : bool init false; // true when an eager prefill hogs this iteration

    // ---- bad-event counters (monotone) ----
    v_gap      : [0..GAPMAX] init 0;  // current consecutive iters victim made no progress
    v_maxgap   : [0..GAPMAX] init 0;  // worst victim gap so far  (TBT bad event)
    v_preempts : [0..3]      init 0;  // times the victim was evicted (BE1)
    preempts   : [0..PT]     init 0;  // total evictions, all requests (BE3 cascade)

    // ---- input-feature variables (for conditions C) ----
    n_long      : [0..NL] init 0;     // # long background requests that arrived
    long_near_v : bool    init false; // a long bg arrived within WIN of the victim
    long_before_v: bool   init false; // a long bg arrived BEFORE the victim (t<T_V)
    long_after_v: bool    init false; // a long bg arrived AFTER  the victim (t>T_V)
    peak_conc   : [0..3]  init 0;     // peak concurrent occupancy

    // == terminal (absorbing) ================================================
    [] stage=VINJECT & t=T -> true;

    // == stage VINJECT: inject the victim at its arrival time ================
    [] stage=VINJECT & t<T & t=T_V & !v_in ->
        (v_pre'=VPRE) & (v_dec'=VDEC) & (v_adm'=t) & (stage'=ARRIVE);
    [] stage=VINJECT & t<T & !(t=T_V & !v_in) ->
        (stage'=ARRIVE);

    // == stage ARRIVE: <=1 background arrival into the first free slot ========
    // slot 1 free
    [] stage=ARRIVE & tgt=1 ->
          (1-p_arr)          : (stage'=SETUP)
        + p_arr*(1-p_long)   : (b1_pre'=1) & (b1_dec'=2) & (b1_adm'=t) & (stage'=SETUP)
        + p_arr*p_long       : (b1_pre'=3) & (b1_dec'=3) & (b1_adm'=t)
                               & (n_long'=min(NL,n_long+1))
                               & (long_near_v'=(long_near_v | (t>=T_V-WIN & t<=T_V+WIN)))
                               & (long_before_v'=(long_before_v | t<T_V))
                               & (long_after_v'=(long_after_v | t>T_V))
                               & (stage'=SETUP);
    // slot 2 free (slot 1 busy)
    [] stage=ARRIVE & tgt=2 ->
          (1-p_arr)          : (stage'=SETUP)
        + p_arr*(1-p_long)   : (b2_pre'=1) & (b2_dec'=2) & (b2_adm'=t) & (stage'=SETUP)
        + p_arr*p_long       : (b2_pre'=3) & (b2_dec'=3) & (b2_adm'=t)
                               & (n_long'=min(NL,n_long+1))
                               & (long_near_v'=(long_near_v | (t>=T_V-WIN & t<=T_V+WIN)))
                               & (long_before_v'=(long_before_v | t<T_V))
                               & (long_after_v'=(long_after_v | t>T_V))
                               & (stage'=SETUP);
    // no slot free -> arrival dropped
    [] stage=ARRIVE & tgt=0 -> (stage'=SETUP);

    // == stage SETUP: freeze this iteration's hog flag and update peak =======
    [] stage=SETUP ->
        (hog'=(CHUNKED=0 & (v_pre>0 | b1_pre>0 | b2_pre>0)))
        & (peak_conc'=max(peak_conc,occ))
        & (stage'=SVC_V);

    // == stage SVC_V: service the victim =====================================
    [] stage=SVC_V & !v_in -> (stage'=SVC_B1);                                  // idle
    [] stage=SVC_V & v_in & v_pre>0 ->                                          // prefill (no token)
        (v_blk'=min(6,v_blk+chunk_v)) & (v_pre'=v_pre-chunk_v)
        & (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1)) & (stage'=SVC_B1);
    [] stage=SVC_V & v_pre=0 & v_dec>0 & hog ->                                 // decode stalled by hog
        (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1)) & (stage'=SVC_B1);
    [] stage=SVC_V & v_pre=0 & v_dec>0 & !hog ->                                // decode: emit a token
        (v_dec'=v_dec-1) & (v_blk'=(v_dec-1=0 ? 0 : min(6,v_blk+1)))
        & (v_gap'=0) & (stage'=SVC_B1);
    [] stage=SVC_V & v_in & v_pre=0 & v_dec=0 -> (v_blk'=0) & (stage'=SVC_B1);  // cleanup (finished)

    // == stage SVC_B1: service background slot 1 =============================
    [] stage=SVC_B1 & !b1_in -> (stage'=SVC_B2);
    [] stage=SVC_B1 & b1_in & b1_pre>0 ->
        (b1_blk'=min(6,b1_blk+chunk_b1)) & (b1_pre'=b1_pre-chunk_b1) & (stage'=SVC_B2);
    [] stage=SVC_B1 & b1_pre=0 & b1_dec>0 & hog -> (stage'=SVC_B2);
    [] stage=SVC_B1 & b1_pre=0 & b1_dec>0 & !hog ->
        (b1_dec'=b1_dec-1) & (b1_blk'=(b1_dec-1=0 ? 0 : min(6,b1_blk+1))) & (stage'=SVC_B2);
    [] stage=SVC_B1 & b1_in & b1_pre=0 & b1_dec=0 -> (b1_blk'=0) & (stage'=SVC_B2);

    // == stage SVC_B2: service background slot 2 =============================
    [] stage=SVC_B2 & !b2_in -> (stage'=PREEMPT);
    [] stage=SVC_B2 & b2_in & b2_pre>0 ->
        (b2_blk'=min(6,b2_blk+chunk_b2)) & (b2_pre'=b2_pre-chunk_b2) & (stage'=PREEMPT);
    [] stage=SVC_B2 & b2_pre=0 & b2_dec>0 & hog -> (stage'=PREEMPT);
    [] stage=SVC_B2 & b2_pre=0 & b2_dec>0 & !hog ->
        (b2_dec'=b2_dec-1) & (b2_blk'=(b2_dec-1=0 ? 0 : min(6,b2_blk+1))) & (stage'=PREEMPT);
    [] stage=SVC_B2 & b2_in & b2_pre=0 & b2_dec=0 -> (b2_blk'=0) & (stage'=PREEMPT);

    // == stage PREEMPT: evict (recompute) until the KV pool fits =============
    // exit: pool fits -> advance the clock, start next iteration
    [] stage=PREEMPT & kv<=KV_CAP -> (t'=min(T,t+1)) & (stage'=VINJECT) & (hog'=false);
    // evict victim (only when it has the top score: FCFS newest, or forced)
    [] stage=PREEMPT & kv>KV_CAP & v_score>=b1_score & v_score>=b2_score & v_score>=0 ->
        (v_blk'=0) & (v_pre'=v_blk)                       // recompute: rebuild all held blocks
        & (v_preempts'=min(3,v_preempts+1)) & (preempts'=min(PT,preempts+1))
        & (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1));
    // evict background slot 1
    [] stage=PREEMPT & kv>KV_CAP & b1_score>v_score & b1_score>=b2_score ->
        (b1_blk'=0) & (b1_pre'=b1_blk) & (preempts'=min(PT,preempts+1));
    // evict background slot 2
    [] stage=PREEMPT & kv>KV_CAP & b2_score>v_score & b2_score>b1_score ->
        (b2_blk'=0) & (b2_pre'=b2_blk) & (preempts'=min(PT,preempts+1));

endmodule

// ===========================================================================
//  Labels — the "bad events", all read at the terminal state (t=T)
// ===========================================================================
label "done"          = (t=T);
label "v_preempted"   = (v_preempts>=1);       // BE1: victim was evicted
label "v_stalled"     = (v_maxgap>=SLO_TBT);   // BE2: victim TBT-SLO violation
label "cascade"       = (preempts>=K_CASC);    // BE3: preemption cascade

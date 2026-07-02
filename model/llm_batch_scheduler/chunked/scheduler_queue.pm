// ============================================================================
//  LLM batch scheduler — CHUNKED, with a REAL QUEUE (v2, realistic redesign)
//  ---------------------------------------------------------------------------
//  Addresses the design review of v1 (scheduler.pm):
//    Q3  no special SCHEDULER rule for the victim: it is an ordinary request
//        that competes for batch slots and can be queued / evicted by the SAME
//        FCFS-admit / LIFO-evict rules as any other request. (Its INPUT -- a
//        short shape, an arrival time -- may still be its own; that is the
//        assumption under study, not a privilege, exactly as q5 in FQ-CoDel.)
//    Q6  prompt and output length are drawn INDEPENDENTLY (a correlation knob
//        can be added by conditioning p_ol on the prompt class).
//    Q8  a real waiting queue: a request waits when all N_SLOTS are busy;
//        on KV exhaustion a running request is evicted BACK TO THE QUEUE
//        (returns to `waiting`, must recompute its lost blocks).
//
//  Unified request records: each of 3 records is  empty | waiting | running
//  (st = 0 | 1 | 2). Arrival fills an empty record; admission flips
//  waiting->running (at most N_SLOTS running); preemption flips running->waiting.
//  The "queue" is simply the set of waiting records, so eviction can never
//  overflow it (a record just changes status). Record v is the victim (tracked
//  with gap counters -- instrumentation only, NOT a scheduler privilege);
//  records b1,b2 are background. Chunked prefill: <=CHUNK_BLK prefill blocks/iter,
//  so a prefill never stalls a decode -> the victim's only stall source is
//  queueing + KV-exhaustion preemption + recompute.
//
//  Realistic magnitudes are out of reach for exact checking with a queue;
//  this model is intended for STATISTICAL model checking (simulation). See
//  ../PARAMETERS.md. The exact, privileged-victim v1 (scheduler.pm) remains for
//  the initial exploration.
// ============================================================================

dtmc

const int T        = 10;   // horizon (iterations)
const int T_V      = 3;    // victim arrival iteration (its input assumption)
const int N_SLOTS  = 2;    // batch width (max concurrently running)  [max_num_seqs]
const int KV_CAP   = 8;    // shared KV pool, blocks                  [PagedAttention]
const int CHUNK_BLK= 1;    // prefill blocks computed per iteration   [chunked prefill]

const int POLICY;          // 0 = fcfs (LIFO evict) ; 1 = priority (protect victim)

// request shapes (blocks) -- prompt and output are INDEPENDENT (Q6)
const int SP = 1;  const int LP = 3;   // prompt: short / long
const int SO = 1;  const int LO = 3;   // output: short / long
const int VP = 1;  const int VO = 2;   // victim: short prompt, modest output

// input pattern (sweepable; left undefined)
const double p_arr;        // P(a background request arrives in an iteration)
const double p_lp;         // P(arriving bg has a LONG prompt)
const double p_ol;         // P(arriving bg has a LONG output)  (independent of p_lp)

const int SLO_TBT = 3;     // victim inter-token gap >= this = TBT-SLO violation
const int K_CASC  = 2;     // preemption cascade threshold
const int WIN     = 2;
const int GAPMAX  = T;
const int NL      = 4;
const int PT      = 6;

// stages
const int VINJECT=1; const int ARRIVE=2; const int ADMIT=3;
const int SVC_V=4;   const int SVC_B1=5; const int SVC_B2=6; const int PREEMPT=7;

// ---- status helpers --------------------------------------------------------
formula run_v  = st_v=2;  formula wait_v  = st_v=1;  formula emp_v  = st_v=0;
formula run_b1 = st_b1=2; formula wait_b1 = st_b1=1; formula emp_b1 = st_b1=0;
formula run_b2 = st_b2=2; formula wait_b2 = st_b2=1; formula emp_b2 = st_b2=0;

formula nrun = (run_v?1:0) + (run_b1?1:0) + (run_b2?1:0);
formula kv   = bk_v + bk_b1 + bk_b2;          // waiting/empty records hold 0 blocks
formula any_wait = wait_v | wait_b1 | wait_b2;

// chunked prefill chunk per record
formula ch_v  = min(pp_v,  CHUNK_BLK);
formula ch_b1 = min(pp_b1, CHUNK_BLK);
formula ch_b2 = min(pp_b2, CHUNK_BLK);

// FCFS admission: promote the waiting record with the smallest arrival order
// (ties broken v < b1 < b2). Only when a slot is free.
formula adm_v  = wait_v  & nrun<N_SLOTS & (!wait_b1 | ad_v<=ad_b1) & (!wait_b2 | ad_v<=ad_b2);
formula adm_b1 = wait_b1 & nrun<N_SLOTS & (!wait_v | ad_b1<ad_v)  & (!wait_b2 | ad_b1<=ad_b2);
formula adm_b2 = wait_b2 & nrun<N_SLOTS & (!wait_v | ad_b2<ad_v)  & (!wait_b1 | ad_b2<ad_b1);

// LIFO eviction score (highest evicted first). priority => victim protected.
formula sc_v  = run_v  ? (ad_v  + (POLICY=1 ? -100 : 0)) : -1;
formula sc_b1 = run_b1 ? ad_b1 : -1;
formula sc_b2 = run_b2 ? ad_b2 : -1;

formula v_gap1 = min(GAPMAX, v_gap+1);

module worker

    t     : [0..T] init 0;
    stage : [1..7] init VINJECT;

    // records: st (0 empty,1 waiting,2 running), pp prefill-left, oo output-left,
    //          bk blocks held, ad arrival order
    st_v : [0..2] init 0; pp_v : [0..6] init 0; oo_v : [0..3] init 0; bk_v : [0..6] init 0; ad_v : [0..T] init 0;
    st_b1: [0..2] init 0; pp_b1: [0..6] init 0; oo_b1: [0..3] init 0; bk_b1: [0..6] init 0; ad_b1: [0..T] init 0;
    st_b2: [0..2] init 0; pp_b2: [0..6] init 0; oo_b2: [0..3] init 0; bk_b2: [0..6] init 0; ad_b2: [0..T] init 0;

    // victim instrumentation (NOT a scheduler privilege) + bad-event counters
    v_gap      : [0..GAPMAX] init 0;
    v_maxgap   : [0..GAPMAX] init 0;
    v_preempts : [0..3]      init 0;
    preempts   : [0..PT]     init 0;

    // input-feature variables for conditions C
    n_lp        : [0..NL] init 0;   // # long-PROMPT bg arrivals
    n_lo        : [0..NL] init 0;   // # long-OUTPUT bg arrivals
    lp_before_v : bool    init false;  // a long-prompt bg arrived BEFORE the victim
    lp_after_v  : bool    init false;  // a long-prompt bg arrived AFTER  the victim
    peak_conc   : [0..3]  init 0;

    // ---- terminal ----
    [] stage=VINJECT & t=T -> true;

    // ---- VINJECT: victim enters the QUEUE (waiting) at T_V, competes normally
    [] stage=VINJECT & t<T & t=T_V & emp_v ->
        (st_v'=1) & (pp_v'=VP) & (oo_v'=VO) & (ad_v'=t) & (stage'=ARRIVE);
    [] stage=VINJECT & t<T & !(t=T_V & emp_v) -> (stage'=ARRIVE);

    // ---- ARRIVE: <=1 bg request into an empty bg record; prompt & output
    //      drawn INDEPENDENTLY (4 shape combos). Target: b1 if empty else b2.
    [] stage=ARRIVE & emp_b1 ->
          (1-p_arr)                : (stage'=ADMIT)
        + p_arr*(1-p_lp)*(1-p_ol)  : (st_b1'=1)&(pp_b1'=SP)&(oo_b1'=SO)&(ad_b1'=t)&(stage'=ADMIT)
        + p_arr*(1-p_lp)*p_ol      : (st_b1'=1)&(pp_b1'=SP)&(oo_b1'=LO)&(ad_b1'=t)&(n_lo'=min(NL,n_lo+1))&(stage'=ADMIT)
        + p_arr*p_lp*(1-p_ol)      : (st_b1'=1)&(pp_b1'=LP)&(oo_b1'=SO)&(ad_b1'=t)&(n_lp'=min(NL,n_lp+1))
                                     &(lp_before_v'=(lp_before_v|t<T_V))&(lp_after_v'=(lp_after_v|t>T_V))&(stage'=ADMIT)
        + p_arr*p_lp*p_ol          : (st_b1'=1)&(pp_b1'=LP)&(oo_b1'=LO)&(ad_b1'=t)&(n_lp'=min(NL,n_lp+1))&(n_lo'=min(NL,n_lo+1))
                                     &(lp_before_v'=(lp_before_v|t<T_V))&(lp_after_v'=(lp_after_v|t>T_V))&(stage'=ADMIT);
    [] stage=ARRIVE & !emp_b1 & emp_b2 ->
          (1-p_arr)                : (stage'=ADMIT)
        + p_arr*(1-p_lp)*(1-p_ol)  : (st_b2'=1)&(pp_b2'=SP)&(oo_b2'=SO)&(ad_b2'=t)&(stage'=ADMIT)
        + p_arr*(1-p_lp)*p_ol      : (st_b2'=1)&(pp_b2'=SP)&(oo_b2'=LO)&(ad_b2'=t)&(n_lo'=min(NL,n_lo+1))&(stage'=ADMIT)
        + p_arr*p_lp*(1-p_ol)      : (st_b2'=1)&(pp_b2'=LP)&(oo_b2'=SO)&(ad_b2'=t)&(n_lp'=min(NL,n_lp+1))
                                     &(lp_before_v'=(lp_before_v|t<T_V))&(lp_after_v'=(lp_after_v|t>T_V))&(stage'=ADMIT)
        + p_arr*p_lp*p_ol          : (st_b2'=1)&(pp_b2'=LP)&(oo_b2'=LO)&(ad_b2'=t)&(n_lp'=min(NL,n_lp+1))&(n_lo'=min(NL,n_lo+1))
                                     &(lp_before_v'=(lp_before_v|t<T_V))&(lp_after_v'=(lp_after_v|t>T_V))&(stage'=ADMIT);
    [] stage=ARRIVE & !emp_b1 & !emp_b2 -> (stage'=ADMIT);   // no room -> dropped

    // ---- ADMIT: FCFS promote waiting->running while a slot is free (loops) --
    [] stage=ADMIT & adm_v  -> (st_v'=2)  & (peak_conc'=max(peak_conc,nrun+1));
    [] stage=ADMIT & adm_b1 -> (st_b1'=2) & (peak_conc'=max(peak_conc,nrun+1));
    [] stage=ADMIT & adm_b2 -> (st_b2'=2) & (peak_conc'=max(peak_conc,nrun+1));
    [] stage=ADMIT & !adm_v & !adm_b1 & !adm_b2 -> (stage'=SVC_V);

    // ---- SVC_V: service victim if running; maintain gap (waiting also stalls)
    [] stage=SVC_V & emp_v -> (stage'=SVC_B1);
    [] stage=SVC_V & wait_v ->                                                   // queued/evicted -> no progress
        (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1)) & (stage'=SVC_B1);
    [] stage=SVC_V & run_v & pp_v>0 ->                                           // prefill chunk -> no token
        (bk_v'=min(6,bk_v+ch_v)) & (pp_v'=pp_v-ch_v)
        & (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1)) & (stage'=SVC_B1);
    [] stage=SVC_V & run_v & pp_v=0 & oo_v>0 ->                                  // decode -> emit token
        (oo_v'=oo_v-1) & (bk_v'=(oo_v-1=0 ? 0 : min(6,bk_v+1)))
        & (st_v'=(oo_v-1=0 ? 0 : 2)) & (v_gap'=0) & (stage'=SVC_B1);
    [] stage=SVC_V & run_v & pp_v=0 & oo_v=0 -> (st_v'=0) & (bk_v'=0) & (stage'=SVC_B1); // cleanup

    // ---- SVC_B1 ----
    [] stage=SVC_B1 & !run_b1 -> (stage'=SVC_B2);
    [] stage=SVC_B1 & run_b1 & pp_b1>0 ->
        (bk_b1'=min(6,bk_b1+ch_b1)) & (pp_b1'=pp_b1-ch_b1) & (stage'=SVC_B2);
    [] stage=SVC_B1 & run_b1 & pp_b1=0 & oo_b1>0 ->
        (oo_b1'=oo_b1-1) & (bk_b1'=(oo_b1-1=0 ? 0 : min(6,bk_b1+1))) & (st_b1'=(oo_b1-1=0 ? 0 : 2)) & (stage'=SVC_B2);
    [] stage=SVC_B1 & run_b1 & pp_b1=0 & oo_b1=0 -> (st_b1'=0) & (bk_b1'=0) & (stage'=SVC_B2);

    // ---- SVC_B2 ----
    [] stage=SVC_B2 & !run_b2 -> (stage'=PREEMPT);
    [] stage=SVC_B2 & run_b2 & pp_b2>0 ->
        (bk_b2'=min(6,bk_b2+ch_b2)) & (pp_b2'=pp_b2-ch_b2) & (stage'=PREEMPT);
    [] stage=SVC_B2 & run_b2 & pp_b2=0 & oo_b2>0 ->
        (oo_b2'=oo_b2-1) & (bk_b2'=(oo_b2-1=0 ? 0 : min(6,bk_b2+1))) & (st_b2'=(oo_b2-1=0 ? 0 : 2)) & (stage'=PREEMPT);
    [] stage=SVC_B2 & run_b2 & pp_b2=0 & oo_b2=0 -> (st_b2'=0) & (bk_b2'=0) & (stage'=PREEMPT);

    // ---- PREEMPT: evict running->waiting (LIFO) until KV pool fits (loops) --
    [] stage=PREEMPT & kv<=KV_CAP -> (t'=min(T,t+1)) & (stage'=VINJECT);
    [] stage=PREEMPT & kv>KV_CAP & sc_v>=sc_b1 & sc_v>=sc_b2 & sc_v>=0 ->        // evict victim -> queue
        (st_v'=1) & (pp_v'=bk_v) & (bk_v'=0)
        & (v_preempts'=min(3,v_preempts+1)) & (preempts'=min(PT,preempts+1))
        & (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1));
    [] stage=PREEMPT & kv>KV_CAP & sc_b1>sc_v & sc_b1>=sc_b2 ->
        (st_b1'=1) & (pp_b1'=bk_b1) & (bk_b1'=0) & (preempts'=min(PT,preempts+1));
    [] stage=PREEMPT & kv>KV_CAP & sc_b2>sc_v & sc_b2>sc_b1 ->
        (st_b2'=1) & (pp_b2'=bk_b2) & (bk_b2'=0) & (preempts'=min(PT,preempts+1));

endmodule

// ---- bad events (read at terminal "done") ---------------------------------
label "done"        = (t=T);
label "v_preempted" = (v_preempts>=1);       // BE1 (victim framing)
label "v_stalled"   = (v_maxgap>=SLO_TBT);   // BE2 (victim framing)
label "cascade"     = (preempts>=K_CASC);    // BE3 (system-level framing)

// ============================================================================
//  LLM inference batch scheduler — NO-CHUNKING (eager whole-prompt) variant
//  ---------------------------------------------------------------------------
//  The pre-Sarathi FCFS behavior: a newly admitted prompt is prefilled in ONE
//  shot, monopolizing the iteration. While a prefill is in progress this
//  iteration (`hog`), every DECODE is stalled (produces no token) -- the
//  generation-stall / head-of-line-blocking pathology that chunked prefill
//  (../chunked/) was designed to remove.
//
//  Same structure, resources, victim, and eviction policy as the chunked
//  variant; the ONLY differences are:
//    * prefill loads the WHOLE remaining prompt in one iteration (no chunk cap)
//    * a `hog` flag: if any request is prefilling this iteration, decodes stall
//  Compare P(victim stall) here vs. ../chunked to see chunked prefill's value.
//
//  Stages per iteration: VINJECT -> ARRIVE -> SETUP (freeze hog) -> SVC_V ->
//  SVC_B1 -> SVC_B2 -> PREEMPT -> (t++). See ../chunked/scheduler.pm and
//  ../NOTES.md for the full commentary on variables and abstractions.
// ============================================================================

dtmc

const int T        = 10;
const int T_V      = 3;
const int KV_CAP   = 8;

const int POLICY;          // 0 = fcfs (LIFO evict) ; 1 = priority (protect victim)

const int VPRE     = 1;
const int VDEC     = 3;

const double p_arr;
const double p_long;

const int SLO_TBT  = 3;
const int K_CASC   = 2;
const int WIN      = 2;
const int GAPMAX   = T;
const int NL       = 4;
const int PT       = 6;

const int VINJECT = 1;
const int ARRIVE  = 2;
const int SETUP   = 3;
const int SVC_V   = 4;
const int SVC_B1  = 5;
const int SVC_B2  = 6;
const int PREEMPT = 7;

formula v_in  = (v_pre>0 | v_dec>0 | v_blk>0);
formula b1_in = (b1_pre>0 | b1_dec>0 | b1_blk>0);
formula b2_in = (b2_pre>0 | b2_dec>0 | b2_blk>0);

formula occ = (v_in?1:0) + (b1_in?1:0) + (b2_in?1:0);
formula kv  = v_blk + b1_blk + b2_blk;

formula tgt = !b1_in ? 1 : (!b2_in ? 2 : 0);

// eager: a prefill computes the WHOLE remaining prompt in one iteration
formula chunk_v  = v_pre;
formula chunk_b1 = b1_pre;
formula chunk_b2 = b2_pre;

formula v_score  = v_blk>0  ? v_adm  : -1;
formula b1_score = b1_blk>0 ? (b1_adm + (POLICY=1 ? 100 : 0)) : -1;
formula b2_score = b2_blk>0 ? (b2_adm + (POLICY=1 ? 100 : 0)) : -1;

formula v_gap1 = min(GAPMAX, v_gap+1);

module worker

    t     : [0..T] init 0;
    stage : [1..7] init VINJECT;

    v_pre : [0..6] init 0; v_dec : [0..3] init 0; v_blk : [0..6] init 0; v_adm : [0..T] init 0;
    b1_pre: [0..6] init 0; b1_dec: [0..3] init 0; b1_blk: [0..6] init 0; b1_adm: [0..T] init 0;
    b2_pre: [0..6] init 0; b2_dec: [0..3] init 0; b2_blk: [0..6] init 0; b2_adm: [0..T] init 0;

    hog   : bool init false; // true when a prefill hogs this iteration -> decodes stall

    v_gap      : [0..GAPMAX] init 0;
    v_maxgap   : [0..GAPMAX] init 0;
    v_preempts : [0..3]      init 0;
    preempts   : [0..PT]     init 0;

    n_long      : [0..NL] init 0;
    long_near_v : bool    init false;
    long_before_v: bool   init false;
    long_after_v: bool    init false;
    peak_conc   : [0..3]  init 0;

    [] stage=VINJECT & t=T -> true;

    [] stage=VINJECT & t<T & t=T_V & !v_in ->
        (v_pre'=VPRE) & (v_dec'=VDEC) & (v_adm'=t) & (stage'=ARRIVE);
    [] stage=VINJECT & t<T & !(t=T_V & !v_in) ->
        (stage'=ARRIVE);

    [] stage=ARRIVE & tgt=1 ->
          (1-p_arr)          : (stage'=SETUP)
        + p_arr*(1-p_long)   : (b1_pre'=1) & (b1_dec'=2) & (b1_adm'=t) & (stage'=SETUP)
        + p_arr*p_long       : (b1_pre'=3) & (b1_dec'=3) & (b1_adm'=t)
                               & (n_long'=min(NL,n_long+1))
                               & (long_near_v'=(long_near_v | (t>=T_V-WIN & t<=T_V+WIN)))
                               & (long_before_v'=(long_before_v | t<T_V))
                               & (long_after_v'=(long_after_v | t>T_V))
                               & (stage'=SETUP);
    [] stage=ARRIVE & tgt=2 ->
          (1-p_arr)          : (stage'=SETUP)
        + p_arr*(1-p_long)   : (b2_pre'=1) & (b2_dec'=2) & (b2_adm'=t) & (stage'=SETUP)
        + p_arr*p_long       : (b2_pre'=3) & (b2_dec'=3) & (b2_adm'=t)
                               & (n_long'=min(NL,n_long+1))
                               & (long_near_v'=(long_near_v | (t>=T_V-WIN & t<=T_V+WIN)))
                               & (long_before_v'=(long_before_v | t<T_V))
                               & (long_after_v'=(long_after_v | t>T_V))
                               & (stage'=SETUP);
    [] stage=ARRIVE & tgt=0 -> (stage'=SETUP);

    // freeze the hog flag: with eager prefill, any prefill this iteration stalls decodes
    [] stage=SETUP ->
        (hog'=(v_pre>0 | b1_pre>0 | b2_pre>0))
        & (peak_conc'=max(peak_conc,occ)) & (stage'=SVC_V);

    // victim
    [] stage=SVC_V & !v_in -> (stage'=SVC_B1);
    [] stage=SVC_V & v_pre>0 ->                                                 // prefill whole prompt (no token)
        (v_blk'=min(6,v_blk+chunk_v)) & (v_pre'=v_pre-chunk_v)
        & (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1)) & (stage'=SVC_B1);
    [] stage=SVC_V & v_pre=0 & v_dec>0 & hog ->                                 // decode stalled by a co-running prefill
        (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1)) & (stage'=SVC_B1);
    [] stage=SVC_V & v_pre=0 & v_dec>0 & !hog ->                                // decode: emit a token
        (v_dec'=v_dec-1) & (v_blk'=(v_dec-1=0 ? 0 : min(6,v_blk+1)))
        & (v_gap'=0) & (stage'=SVC_B1);
    [] stage=SVC_V & v_in & v_pre=0 & v_dec=0 -> (v_blk'=0) & (stage'=SVC_B1);

    // background 1
    [] stage=SVC_B1 & !b1_in -> (stage'=SVC_B2);
    [] stage=SVC_B1 & b1_pre>0 ->
        (b1_blk'=min(6,b1_blk+chunk_b1)) & (b1_pre'=b1_pre-chunk_b1) & (stage'=SVC_B2);
    [] stage=SVC_B1 & b1_pre=0 & b1_dec>0 & hog -> (stage'=SVC_B2);
    [] stage=SVC_B1 & b1_pre=0 & b1_dec>0 & !hog ->
        (b1_dec'=b1_dec-1) & (b1_blk'=(b1_dec-1=0 ? 0 : min(6,b1_blk+1))) & (stage'=SVC_B2);
    [] stage=SVC_B1 & b1_in & b1_pre=0 & b1_dec=0 -> (b1_blk'=0) & (stage'=SVC_B2);

    // background 2
    [] stage=SVC_B2 & !b2_in -> (stage'=PREEMPT);
    [] stage=SVC_B2 & b2_pre>0 ->
        (b2_blk'=min(6,b2_blk+chunk_b2)) & (b2_pre'=b2_pre-chunk_b2) & (stage'=PREEMPT);
    [] stage=SVC_B2 & b2_pre=0 & b2_dec>0 & hog -> (stage'=PREEMPT);
    [] stage=SVC_B2 & b2_pre=0 & b2_dec>0 & !hog ->
        (b2_dec'=b2_dec-1) & (b2_blk'=(b2_dec-1=0 ? 0 : min(6,b2_blk+1))) & (stage'=PREEMPT);
    [] stage=SVC_B2 & b2_in & b2_pre=0 & b2_dec=0 -> (b2_blk'=0) & (stage'=PREEMPT);

    // preemption
    [] stage=PREEMPT & kv<=KV_CAP -> (t'=min(T,t+1)) & (stage'=VINJECT) & (hog'=false);
    [] stage=PREEMPT & kv>KV_CAP & v_score>=b1_score & v_score>=b2_score & v_score>=0 ->
        (v_blk'=0) & (v_pre'=v_blk)
        & (v_preempts'=min(3,v_preempts+1)) & (preempts'=min(PT,preempts+1))
        & (v_gap'=v_gap1) & (v_maxgap'=max(v_maxgap,v_gap1));
    [] stage=PREEMPT & kv>KV_CAP & b1_score>v_score & b1_score>=b2_score ->
        (b1_blk'=0) & (b1_pre'=b1_blk) & (preempts'=min(PT,preempts+1));
    [] stage=PREEMPT & kv>KV_CAP & b2_score>v_score & b2_score>b1_score ->
        (b2_blk'=0) & (b2_pre'=b2_blk) & (preempts'=min(PT,preempts+1));

endmodule

label "done"        = (t=T);
label "v_preempted" = (v_preempts>=1);
label "v_stalled"   = (v_maxgap>=SLO_TBT);
label "cascade"     = (preempts>=K_CASC);

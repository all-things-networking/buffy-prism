// =====================================================================
//  ToR incast  --  MDP variant for Pmin (each sender MUST start within WIN)
//  (auto-generated from incast_mdp.pm; MMAX=20 senders, 10 uplinks)
// =====================================================================
//
//  Difference vs incast_mdp.pm: instead of a per-slot start-vs-wait choice
//  (which lets a scheduler avoid loss by never sending), the start slot t_k of
//  every in-fan-out sender (k<=M) is chosen NONDETERMINISTICALLY in [0..WIN] in
//  an initial scheduling phase (mode=0), and the sender is forced to start
//  (on_k=1). The run (mode=1) is then a deterministic per-slot service, so the
//  only nondeterminism is the schedule. Pmax = worst-case schedule, Pmin =
//  best-case schedule -- but always with all M senders sending, so Pmin is
//  physically meaningful (no never-send escape).

mdp

const int M;       // TOTAL SENDERS (input-traffic knob); even, 2..20; fan-out = M/2
const int WIN;     // synchronization window: start slot chosen in [0..WIN]
const int SLEN;    // packets per sender (back-to-back, 1 per slot)
const int BUF;     // buffer capacity (same for every port; representative)
const int THRESH;  // bad event Q: at least THRESH packets dropped at the output

const int MPP  = 2;
const int MMAX = 20;           // sender slots modelled (= MPP * 10 uplink ports)
const int HORIZON = WIN + M*SLEN + SLEN;   // by here all packets arrived/drained
const int TWIN = max(WIN, 1);  // start-slot range bound (avoids [0..0] at WIN=0)

// active flows: scheduled (on=1), started (slot>=t), and < SLEN slots since start
formula a1 = (on1=1 & slot>=t1 & slot-t1<SLEN) ? 1 : 0;
formula a2 = (on2=1 & slot>=t2 & slot-t2<SLEN) ? 1 : 0;
formula a3 = (on3=1 & slot>=t3 & slot-t3<SLEN) ? 1 : 0;
formula a4 = (on4=1 & slot>=t4 & slot-t4<SLEN) ? 1 : 0;
formula a5 = (on5=1 & slot>=t5 & slot-t5<SLEN) ? 1 : 0;
formula a6 = (on6=1 & slot>=t6 & slot-t6<SLEN) ? 1 : 0;
formula a7 = (on7=1 & slot>=t7 & slot-t7<SLEN) ? 1 : 0;
formula a8 = (on8=1 & slot>=t8 & slot-t8<SLEN) ? 1 : 0;
formula a9 = (on9=1 & slot>=t9 & slot-t9<SLEN) ? 1 : 0;
formula a10 = (on10=1 & slot>=t10 & slot-t10<SLEN) ? 1 : 0;
formula a11 = (on11=1 & slot>=t11 & slot-t11<SLEN) ? 1 : 0;
formula a12 = (on12=1 & slot>=t12 & slot-t12<SLEN) ? 1 : 0;
formula a13 = (on13=1 & slot>=t13 & slot-t13<SLEN) ? 1 : 0;
formula a14 = (on14=1 & slot>=t14 & slot-t14<SLEN) ? 1 : 0;
formula a15 = (on15=1 & slot>=t15 & slot-t15<SLEN) ? 1 : 0;
formula a16 = (on16=1 & slot>=t16 & slot-t16<SLEN) ? 1 : 0;
formula a17 = (on17=1 & slot>=t17 & slot-t17<SLEN) ? 1 : 0;
formula a18 = (on18=1 & slot>=t18 & slot-t18<SLEN) ? 1 : 0;
formula a19 = (on19=1 & slot>=t19 & slot-t19<SLEN) ? 1 : 0;
formula a20 = (on20=1 & slot>=t20 & slot-t20<SLEN) ? 1 : 0;

formula arr1 = a1 + a2;
formula arr2 = a3 + a4;
formula arr3 = a5 + a6;
formula arr4 = a7 + a8;
formula arr5 = a9 + a10;
formula arr6 = a11 + a12;
formula arr7 = a13 + a14;
formula arr8 = a15 + a16;
formula arr9 = a17 + a18;
formula arr10 = a19 + a20;

// forwarding: a backlogged input port sends 1 to the output
formula f1 = (q1>0)?1:0;
formula f2 = (q2>0)?1:0;
formula f3 = (q3>0)?1:0;
formula f4 = (q4>0)?1:0;
formula f5 = (q5>0)?1:0;
formula f6 = (q6>0)?1:0;
formula f7 = (q7>0)?1:0;
formula f8 = (q8>0)?1:0;
formula f9 = (q9>0)?1:0;
formula f10 = (q10>0)?1:0;
formula Ftot = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9 + f10;

formula o_drained = max(qo - 1, 0);
formula o_room    = BUF - o_drained;
formula o_adm     = min(Ftot, o_room);
formula o_drop    = Ftot - o_adm;          // receiver-facing incast loss this slot
formula qo_next   = o_drained + o_adm;

formula q1_next = (q1 - f1) + min(arr1, BUF - (q1 - f1));
formula q2_next = (q2 - f2) + min(arr2, BUF - (q2 - f2));
formula q3_next = (q3 - f3) + min(arr3, BUF - (q3 - f3));
formula q4_next = (q4 - f4) + min(arr4, BUF - (q4 - f4));
formula q5_next = (q5 - f5) + min(arr5, BUF - (q5 - f5));
formula q6_next = (q6 - f6) + min(arr6, BUF - (q6 - f6));
formula q7_next = (q7 - f7) + min(arr7, BUF - (q7 - f7));
formula q8_next = (q8 - f8) + min(arr8, BUF - (q8 - f8));
formula q9_next = (q9 - f9) + min(arr9, BUF - (q9 - f9));
formula q10_next = (q10 - f10) + min(arr10, BUF - (q10 - f10));
formula i_drop = (arr1 - min(arr1, BUF - (q1 - f1))) + (arr2 - min(arr2, BUF - (q2 - f2))) + (arr3 - min(arr3, BUF - (q3 - f3))) + (arr4 - min(arr4, BUF - (q4 - f4))) + (arr5 - min(arr5, BUF - (q5 - f5))) + (arr6 - min(arr6, BUF - (q6 - f6))) + (arr7 - min(arr7, BUF - (q7 - f7))) + (arr8 - min(arr8, BUF - (q8 - f8))) + (arr9 - min(arr9, BUF - (q9 - f9))) + (arr10 - min(arr10, BUF - (q10 - f10)));

module tor

    // per-sender state: on_k = scheduled-to-send?, t_k = chosen start slot
    on1:[0..1] init 0; t1:[0..TWIN] init 0;
    on2:[0..1] init 0; t2:[0..TWIN] init 0;
    on3:[0..1] init 0; t3:[0..TWIN] init 0;
    on4:[0..1] init 0; t4:[0..TWIN] init 0;
    on5:[0..1] init 0; t5:[0..TWIN] init 0;
    on6:[0..1] init 0; t6:[0..TWIN] init 0;
    on7:[0..1] init 0; t7:[0..TWIN] init 0;
    on8:[0..1] init 0; t8:[0..TWIN] init 0;
    on9:[0..1] init 0; t9:[0..TWIN] init 0;
    on10:[0..1] init 0; t10:[0..TWIN] init 0;
    on11:[0..1] init 0; t11:[0..TWIN] init 0;
    on12:[0..1] init 0; t12:[0..TWIN] init 0;
    on13:[0..1] init 0; t13:[0..TWIN] init 0;
    on14:[0..1] init 0; t14:[0..TWIN] init 0;
    on15:[0..1] init 0; t15:[0..TWIN] init 0;
    on16:[0..1] init 0; t16:[0..TWIN] init 0;
    on17:[0..1] init 0; t17:[0..TWIN] init 0;
    on18:[0..1] init 0; t18:[0..TWIN] init 0;
    on19:[0..1] init 0; t19:[0..TWIN] init 0;
    on20:[0..1] init 0; t20:[0..TWIN] init 0;

    q1:[0..BUF] init 0;
    q2:[0..BUF] init 0;
    q3:[0..BUF] init 0;
    q4:[0..BUF] init 0;
    q5:[0..BUF] init 0;
    q6:[0..BUF] init 0;
    q7:[0..BUF] init 0;
    q8:[0..BUF] init 0;
    q9:[0..BUF] init 0;
    q10:[0..BUF] init 0;
    qo:[0..BUF] init 0;

    odrops:[0..THRESH] init 0;   // dropped at the output (the bad event)
    idrops:[0..THRESH] init 0;   // dropped at the input ports

    slot :[0..HORIZON] init 0;
    mode :[0..1] init 0;          // 0 = choose the schedule, 1 = run it
    istage:[1..21] init 1;  // which sender is being scheduled (mode=0)

    // ---- scheduling phase: fix every in-fan-out sender's start slot ----
    // sender 1: choose start slot t1 in [0..WIN], then commit
    [] mode=0 & istage=1 & 1<=M & t1<WIN -> (t1'=t1+1);
    [] mode=0 & istage=1 & 1<=M           -> (on1'=1) & (istage'=2);
    [] mode=0 & istage=1 & !(1<=M)         -> (istage'=2);
    // sender 2: choose start slot t2 in [0..WIN], then commit
    [] mode=0 & istage=2 & 2<=M & t2<WIN -> (t2'=t2+1);
    [] mode=0 & istage=2 & 2<=M           -> (on2'=1) & (istage'=3);
    [] mode=0 & istage=2 & !(2<=M)         -> (istage'=3);
    // sender 3: choose start slot t3 in [0..WIN], then commit
    [] mode=0 & istage=3 & 3<=M & t3<WIN -> (t3'=t3+1);
    [] mode=0 & istage=3 & 3<=M           -> (on3'=1) & (istage'=4);
    [] mode=0 & istage=3 & !(3<=M)         -> (istage'=4);
    // sender 4: choose start slot t4 in [0..WIN], then commit
    [] mode=0 & istage=4 & 4<=M & t4<WIN -> (t4'=t4+1);
    [] mode=0 & istage=4 & 4<=M           -> (on4'=1) & (istage'=5);
    [] mode=0 & istage=4 & !(4<=M)         -> (istage'=5);
    // sender 5: choose start slot t5 in [0..WIN], then commit
    [] mode=0 & istage=5 & 5<=M & t5<WIN -> (t5'=t5+1);
    [] mode=0 & istage=5 & 5<=M           -> (on5'=1) & (istage'=6);
    [] mode=0 & istage=5 & !(5<=M)         -> (istage'=6);
    // sender 6: choose start slot t6 in [0..WIN], then commit
    [] mode=0 & istage=6 & 6<=M & t6<WIN -> (t6'=t6+1);
    [] mode=0 & istage=6 & 6<=M           -> (on6'=1) & (istage'=7);
    [] mode=0 & istage=6 & !(6<=M)         -> (istage'=7);
    // sender 7: choose start slot t7 in [0..WIN], then commit
    [] mode=0 & istage=7 & 7<=M & t7<WIN -> (t7'=t7+1);
    [] mode=0 & istage=7 & 7<=M           -> (on7'=1) & (istage'=8);
    [] mode=0 & istage=7 & !(7<=M)         -> (istage'=8);
    // sender 8: choose start slot t8 in [0..WIN], then commit
    [] mode=0 & istage=8 & 8<=M & t8<WIN -> (t8'=t8+1);
    [] mode=0 & istage=8 & 8<=M           -> (on8'=1) & (istage'=9);
    [] mode=0 & istage=8 & !(8<=M)         -> (istage'=9);
    // sender 9: choose start slot t9 in [0..WIN], then commit
    [] mode=0 & istage=9 & 9<=M & t9<WIN -> (t9'=t9+1);
    [] mode=0 & istage=9 & 9<=M           -> (on9'=1) & (istage'=10);
    [] mode=0 & istage=9 & !(9<=M)         -> (istage'=10);
    // sender 10: choose start slot t10 in [0..WIN], then commit
    [] mode=0 & istage=10 & 10<=M & t10<WIN -> (t10'=t10+1);
    [] mode=0 & istage=10 & 10<=M           -> (on10'=1) & (istage'=11);
    [] mode=0 & istage=10 & !(10<=M)         -> (istage'=11);
    // sender 11: choose start slot t11 in [0..WIN], then commit
    [] mode=0 & istage=11 & 11<=M & t11<WIN -> (t11'=t11+1);
    [] mode=0 & istage=11 & 11<=M           -> (on11'=1) & (istage'=12);
    [] mode=0 & istage=11 & !(11<=M)         -> (istage'=12);
    // sender 12: choose start slot t12 in [0..WIN], then commit
    [] mode=0 & istage=12 & 12<=M & t12<WIN -> (t12'=t12+1);
    [] mode=0 & istage=12 & 12<=M           -> (on12'=1) & (istage'=13);
    [] mode=0 & istage=12 & !(12<=M)         -> (istage'=13);
    // sender 13: choose start slot t13 in [0..WIN], then commit
    [] mode=0 & istage=13 & 13<=M & t13<WIN -> (t13'=t13+1);
    [] mode=0 & istage=13 & 13<=M           -> (on13'=1) & (istage'=14);
    [] mode=0 & istage=13 & !(13<=M)         -> (istage'=14);
    // sender 14: choose start slot t14 in [0..WIN], then commit
    [] mode=0 & istage=14 & 14<=M & t14<WIN -> (t14'=t14+1);
    [] mode=0 & istage=14 & 14<=M           -> (on14'=1) & (istage'=15);
    [] mode=0 & istage=14 & !(14<=M)         -> (istage'=15);
    // sender 15: choose start slot t15 in [0..WIN], then commit
    [] mode=0 & istage=15 & 15<=M & t15<WIN -> (t15'=t15+1);
    [] mode=0 & istage=15 & 15<=M           -> (on15'=1) & (istage'=16);
    [] mode=0 & istage=15 & !(15<=M)         -> (istage'=16);
    // sender 16: choose start slot t16 in [0..WIN], then commit
    [] mode=0 & istage=16 & 16<=M & t16<WIN -> (t16'=t16+1);
    [] mode=0 & istage=16 & 16<=M           -> (on16'=1) & (istage'=17);
    [] mode=0 & istage=16 & !(16<=M)         -> (istage'=17);
    // sender 17: choose start slot t17 in [0..WIN], then commit
    [] mode=0 & istage=17 & 17<=M & t17<WIN -> (t17'=t17+1);
    [] mode=0 & istage=17 & 17<=M           -> (on17'=1) & (istage'=18);
    [] mode=0 & istage=17 & !(17<=M)         -> (istage'=18);
    // sender 18: choose start slot t18 in [0..WIN], then commit
    [] mode=0 & istage=18 & 18<=M & t18<WIN -> (t18'=t18+1);
    [] mode=0 & istage=18 & 18<=M           -> (on18'=1) & (istage'=19);
    [] mode=0 & istage=18 & !(18<=M)         -> (istage'=19);
    // sender 19: choose start slot t19 in [0..WIN], then commit
    [] mode=0 & istage=19 & 19<=M & t19<WIN -> (t19'=t19+1);
    [] mode=0 & istage=19 & 19<=M           -> (on19'=1) & (istage'=20);
    [] mode=0 & istage=19 & !(19<=M)         -> (istage'=20);
    // sender 20: choose start slot t20 in [0..WIN], then commit
    [] mode=0 & istage=20 & 20<=M & t20<WIN -> (t20'=t20+1);
    [] mode=0 & istage=20 & 20<=M           -> (on20'=1) & (istage'=21);
    [] mode=0 & istage=20 & !(20<=M)         -> (istage'=21);
    [] mode=0 & istage=21 -> (mode'=1);   // schedule fixed; begin the run

    // ---- run phase: one deterministic service step per slot ----
    [step] mode=1 & slot<HORIZON ->
          (q1'=q1_next) & (q2'=q2_next) & (q3'=q3_next) & (q4'=q4_next) & (q5'=q5_next) & (q6'=q6_next) & (q7'=q7_next) & (q8'=q8_next) & (q9'=q9_next) & (q10'=q10_next)
        & (qo'=qo_next)
        & (odrops'=min(THRESH, odrops + o_drop))
        & (idrops'=min(THRESH, idrops + i_drop))
        & (slot'=slot+1);

    [end] mode=1 & slot=HORIZON -> (slot'=slot);

endmodule

label "done" = (slot = HORIZON);

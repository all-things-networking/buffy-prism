// Buggy FQ-CoDel AQM algorithm
// discrete time, nondeterministic choice (traffic)
// 5 input, 1 output
// K=4 (max # of packets arriving at each queue)

dtmc

// number of time steps (to determine backlog proportion)
const int TIME_STEPS = 14;
const int STAGES_PER_TIME_STEP = 16;

// number of input queues
const int IQS = 5;

// size of each input queue
const int SZ = 8;

const int REC_PKT_GET_IQ1 = 1;
const int REC_PKT_ARR_IQ1 = 2;
const int REC_PKT_GET_IQ2 = 3;
const int REC_PKT_ARR_IQ2 = 4;
const int REC_PKT_GET_IQ3 = 5;
const int REC_PKT_ARR_IQ3 = 6;
const int REC_PKT_GET_IQ4 = 7;
const int REC_PKT_ARR_IQ4 = 8;
const int REC_PKT_GET_IQ5 = 9;
const int REC_PKT_ARR_IQ5 = 10;
const int REC_UPD_NEW_IQ1 = 11;
const int REC_UPD_NEW_IQ2 = 12;
const int REC_UPD_NEW_IQ3 = 13;
const int REC_UPD_NEW_IQ4 = 14;
const int REC_UPD_NEW_IQ5 = 15;
const int DEQ = 16;

formula iq1_backlogged = iq1_contents!=0;
formula iq2_backlogged = iq2_contents!=0;
formula iq3_backlogged = iq3_contents!=0;
formula iq4_backlogged = iq4_contents!=0;
formula iqs_bl = iq1_backlogged & iq2_backlogged & iq3_backlogged & iq4_backlogged;

formula iq1_full = iq1_contents=SZ;
formula iq2_full = iq2_contents=SZ;
formula iq3_full = iq3_contents=SZ;
formula iq4_full = iq4_contents=SZ;
formula iq5_full = iq5_contents=SZ;

formula iq1_not_in_new_list = iq1_new_rank=0;
formula iq1_not_in_old_list = iq1_old_rank=0;
formula iq1_add_to_new_list = iq1_not_in_new_list & iq1_not_in_old_list;

formula iq2_not_in_new_list = iq2_new_rank=0;
formula iq2_not_in_old_list = iq2_old_rank=0;
formula iq2_add_to_new_list = iq2_not_in_new_list & iq2_not_in_old_list;

formula iq3_not_in_new_list = iq3_new_rank=0;
formula iq3_not_in_old_list = iq3_old_rank=0;
formula iq3_add_to_new_list = iq3_not_in_new_list & iq3_not_in_old_list;

formula iq4_not_in_new_list = iq4_new_rank=0;
formula iq4_not_in_old_list = iq4_old_rank=0;
formula iq4_add_to_new_list = iq4_not_in_new_list & iq4_not_in_old_list;

formula iq5_not_in_new_list = iq5_new_rank=0;
formula iq5_not_in_old_list = iq5_old_rank=0;
formula iq5_add_to_new_list = iq5_not_in_new_list & iq5_not_in_old_list;

formula deq_iq1_from_new_list = new_list_len!=0 & iq1_new_rank=1;
formula deq_iq1_from_old_list = new_list_len=0 & old_list_len!=0 & iq1_old_rank=1;

formula deq_iq2_from_new_list = new_list_len!=0 & iq2_new_rank=1;
formula deq_iq2_from_old_list = new_list_len=0 & old_list_len!=0 & iq2_old_rank=1;

formula deq_iq3_from_new_list = new_list_len!=0 & iq3_new_rank=1;
formula deq_iq3_from_old_list = new_list_len=0 & old_list_len!=0 & iq3_old_rank=1;

formula deq_iq4_from_new_list = new_list_len!=0 & iq4_new_rank=1;
formula deq_iq4_from_old_list = new_list_len=0 & old_list_len!=0 & iq4_old_rank=1;

formula deq_iq5_from_new_list = new_list_len!=0 & iq5_new_rank=1;
formula deq_iq5_from_old_list = new_list_len=0 & old_list_len!=0 & iq5_old_rank=1;

formula lists_empty = new_list_len=0 & old_list_len=0;

module fqcodel
	iq1_contents : [0..SZ] init 0;
	iq2_contents : [0..SZ] init 0;
	iq3_contents : [0..SZ] init 0;
	iq4_contents : [0..SZ] init 0;
	iq5_contents : [0..SZ] init 0;

	// ranks of input queues in new and old queues lists; 0=not in list
	iq1_new_rank : [0..IQS] init 0;
	iq2_new_rank : [0..IQS] init 0;
	iq3_new_rank : [0..IQS] init 0;
	iq4_new_rank : [0..IQS] init 0;
	iq5_new_rank : [0..IQS] init 0;

	iq1_old_rank : [0..IQS] init 0;
	iq2_old_rank : [0..IQS] init 0;
	iq3_old_rank : [0..IQS] init 0;
	iq4_old_rank : [0..IQS] init 0;
	iq5_old_rank : [0..IQS] init 0;

	new_list_len : [0..IQS] init 0;
	old_list_len : [0..IQS] init 0;

	iq1_arrivals : [0..5] init 0;
	iq2_arrivals : [0..5] init 0;
	iq3_arrivals : [0..5] init 0;
	iq4_arrivals : [0..5] init 0;
	iq5_arrivals : [0..5] init 0;

	iq5_cenq : [0..((TIME_STEPS*4)+1)] init 0;
	iq5_aipg : [0..TIME_STEPS] init 0;

	// stage REC_PKT_GET_IQ1 = 1;
	// stage REC_PKT_ARR_IQ1 = 2;
	// stage REC_PKT_GET_IQ2 = 3;
	// stage REC_PKT_ARR_IQ2 = 4;
	// stage REC_PKT_GET_IQ3 = 5;
	// stage REC_PKT_ARR_IQ3 = 6;
	// stage REC_PKT_GET_IQ4 = 7;
	// stage REC_PKT_ARR_IQ4 = 8;
	// stage REC_PKT_GET_IQ5 = 9;
	// stage REC_PKT_ARR_IQ5 = 10;
	// stage REC_UPD_NEW_IQ1 = 11;
	// stage REC_UPD_NEW_IQ2 = 12;
	// stage REC_UPD_NEW_IQ3 = 13;
	// stage REC_UPD_NEW_IQ4 = 14;
	// stage REC_UPD_NEW_IQ5 = 15;
	// stage DEQ = 16;
	stage : [1..STAGES_PER_TIME_STEP] init 1; 

	time: [0..TIME_STEPS] init 0;

	iq5_deqs_bl: [0..TIME_STEPS] init 0;

	// Arrivals to input queue 1
	[REC_PKT_GET_IQ1] stage=REC_PKT_GET_IQ1 -> 0.2 : (stage'=REC_PKT_ARR_IQ1) & (iq1_arrivals'=0) + 0.2 : (stage'=REC_PKT_ARR_IQ1) & (iq1_arrivals'=1) + 0.2 : (stage'=REC_PKT_ARR_IQ1) & (iq1_arrivals'=2) + 0.2 : (stage'=REC_PKT_ARR_IQ1) & (iq1_arrivals'=3) + 0.2 : (stage'=REC_PKT_ARR_IQ1) & (iq1_arrivals'=4);
	[REC_PKT_ARR_IQ1_K0] stage=REC_PKT_ARR_IQ1 & iq1_arrivals=0 -> (stage'=REC_PKT_GET_IQ2);
	[REC_PKT_ARR_IQ1_K1] stage=REC_PKT_ARR_IQ1 & iq1_arrivals=1 -> (stage'=REC_UPD_NEW_IQ1) & (iq1_contents'=min(SZ,iq1_contents+1));
	[REC_PKT_ARR_IQ1_K2] stage=REC_PKT_ARR_IQ1 & iq1_arrivals=2 -> (stage'=REC_UPD_NEW_IQ1) & (iq1_contents'=min(SZ,iq1_contents+2));
	[REC_PKT_ARR_IQ1_K3] stage=REC_PKT_ARR_IQ1 & iq1_arrivals=3 -> (stage'=REC_UPD_NEW_IQ1) & (iq1_contents'=min(SZ,iq1_contents+3));
	[REC_PKT_ARR_IQ1_K4] stage=REC_PKT_ARR_IQ1 & iq1_arrivals=4 -> (stage'=REC_UPD_NEW_IQ1) & (iq1_contents'=min(SZ,iq1_contents+4));

	// If input queue 1 is not in new or old lists, then add to new list 
	[REC_UPD_NEW_IQ1_NOP] stage=REC_UPD_NEW_IQ1 & !iq1_add_to_new_list -> (stage'=REC_PKT_GET_IQ2);
	[REC_UPD_NEW_IQ1_ADD] stage=REC_UPD_NEW_IQ1 &  iq1_add_to_new_list -> (stage'=REC_PKT_GET_IQ2) & (iq1_new_rank'=min(IQS,new_list_len+1)) & (new_list_len'=min(IQS,new_list_len+1));

	// Arrivals to input queue 2
	[REC_PKT_GET_IQ2] stage=REC_PKT_GET_IQ2 -> 0.2 : (stage'=REC_PKT_ARR_IQ2) & (iq2_arrivals'=0) + 0.2 : (stage'=REC_PKT_ARR_IQ2) & (iq2_arrivals'=1) + 0.2 : (stage'=REC_PKT_ARR_IQ2) & (iq2_arrivals'=2) + 0.2 : (stage'=REC_PKT_ARR_IQ2) & (iq2_arrivals'=3) + 0.2 : (stage'=REC_PKT_ARR_IQ2) & (iq2_arrivals'=4);
	[REC_PKT_ARR_IQ2_K0] stage=REC_PKT_ARR_IQ2 & iq2_arrivals=0 -> (stage'=REC_PKT_GET_IQ3);
	[REC_PKT_ARR_IQ2_K1] stage=REC_PKT_ARR_IQ2 & iq2_arrivals=1 -> (stage'=REC_UPD_NEW_IQ2) & (iq2_contents'=min(SZ,iq2_contents+1));
	[REC_PKT_ARR_IQ2_K2] stage=REC_PKT_ARR_IQ2 & iq2_arrivals=2 -> (stage'=REC_UPD_NEW_IQ2) & (iq2_contents'=min(SZ,iq2_contents+2));
	[REC_PKT_ARR_IQ2_K3] stage=REC_PKT_ARR_IQ2 & iq2_arrivals=3 -> (stage'=REC_UPD_NEW_IQ2) & (iq2_contents'=min(SZ,iq2_contents+3));
	[REC_PKT_ARR_IQ2_K4] stage=REC_PKT_ARR_IQ2 & iq2_arrivals=4 -> (stage'=REC_UPD_NEW_IQ2) & (iq2_contents'=min(SZ,iq2_contents+4));

	// If input queue 2 is not in new or old lists, then add to new list 
	[REC_UPD_NEW_IQ2_NOP] stage=REC_UPD_NEW_IQ2 & !iq2_add_to_new_list -> (stage'=REC_PKT_GET_IQ3);
	[REC_UPD_NEW_IQ2_ADD] stage=REC_UPD_NEW_IQ2 &  iq2_add_to_new_list -> (stage'=REC_PKT_GET_IQ3) & (iq2_new_rank'=min(IQS,new_list_len+1)) & (new_list_len'=min(IQS,new_list_len+1));

	// Arrivals to input queue 3
	[REC_PKT_GET_IQ3] stage=REC_PKT_GET_IQ3 -> 0.2 : (stage'=REC_PKT_ARR_IQ3) & (iq3_arrivals'=0) + 0.2 : (stage'=REC_PKT_ARR_IQ3) & (iq3_arrivals'=1) + 0.2 : (stage'=REC_PKT_ARR_IQ3) & (iq3_arrivals'=2) + 0.2 : (stage'=REC_PKT_ARR_IQ3) & (iq3_arrivals'=3) + 0.2 : (stage'=REC_PKT_ARR_IQ3) & (iq3_arrivals'=4);
	[REC_PKT_ARR_IQ3_K0] stage=REC_PKT_ARR_IQ3 & iq3_arrivals=0 -> (stage'=REC_PKT_GET_IQ4);
	[REC_PKT_ARR_IQ3_K1] stage=REC_PKT_ARR_IQ3 & iq3_arrivals=1 -> (stage'=REC_UPD_NEW_IQ3) & (iq3_contents'=min(SZ,iq3_contents+1));
	[REC_PKT_ARR_IQ3_K2] stage=REC_PKT_ARR_IQ3 & iq3_arrivals=2 -> (stage'=REC_UPD_NEW_IQ3) & (iq3_contents'=min(SZ,iq3_contents+2));
	[REC_PKT_ARR_IQ3_K3] stage=REC_PKT_ARR_IQ3 & iq3_arrivals=3 -> (stage'=REC_UPD_NEW_IQ3) & (iq3_contents'=min(SZ,iq3_contents+3));
	[REC_PKT_ARR_IQ3_K4] stage=REC_PKT_ARR_IQ3 & iq3_arrivals=4 -> (stage'=REC_UPD_NEW_IQ3) & (iq3_contents'=min(SZ,iq3_contents+4));

	// If input queue 3 is not in new or old lists, then add to new list 
	[REC_UPD_NEW_IQ3_NOP] stage=REC_UPD_NEW_IQ3 & !iq3_add_to_new_list -> (stage'=REC_PKT_GET_IQ4);
	[REC_UPD_NEW_IQ3_ADD] stage=REC_UPD_NEW_IQ3 &  iq3_add_to_new_list -> (stage'=REC_PKT_GET_IQ4) & (iq3_new_rank'=min(IQS,new_list_len+1)) & (new_list_len'=min(IQS,new_list_len+1));

	// Arrivals to input queue 4
	[REC_PKT_GET_IQ4] stage=REC_PKT_GET_IQ4 -> 0.2 : (stage'=REC_PKT_ARR_IQ4) & (iq4_arrivals'=0) + 0.2 : (stage'=REC_PKT_ARR_IQ4) & (iq4_arrivals'=1) + 0.2 : (stage'=REC_PKT_ARR_IQ4) & (iq4_arrivals'=2) + 0.2 : (stage'=REC_PKT_ARR_IQ4) & (iq4_arrivals'=3) + 0.2 : (stage'=REC_PKT_ARR_IQ4) & (iq4_arrivals'=4);
	[REC_PKT_ARR_IQ4_K0] stage=REC_PKT_ARR_IQ4 & iq4_arrivals=0 -> (stage'=REC_PKT_GET_IQ5);
	[REC_PKT_ARR_IQ4_K1] stage=REC_PKT_ARR_IQ4 & iq4_arrivals=1 -> (stage'=REC_UPD_NEW_IQ4) & (iq4_contents'=min(SZ,iq4_contents+1));
	[REC_PKT_ARR_IQ4_K2] stage=REC_PKT_ARR_IQ4 & iq4_arrivals=2 -> (stage'=REC_UPD_NEW_IQ4) & (iq4_contents'=min(SZ,iq4_contents+2));
	[REC_PKT_ARR_IQ4_K3] stage=REC_PKT_ARR_IQ4 & iq4_arrivals=3 -> (stage'=REC_UPD_NEW_IQ4) & (iq4_contents'=min(SZ,iq4_contents+3));
	[REC_PKT_ARR_IQ4_K4] stage=REC_PKT_ARR_IQ4 & iq4_arrivals=4 -> (stage'=REC_UPD_NEW_IQ4) & (iq4_contents'=min(SZ,iq4_contents+4));

	// If input queue 4 is not in new or old lists, then add to new list 
	[REC_UPD_NEW_IQ4_NOP] stage=REC_UPD_NEW_IQ4 & !iq4_add_to_new_list -> (stage'=REC_PKT_GET_IQ5);
	[REC_UPD_NEW_IQ4_ADD] stage=REC_UPD_NEW_IQ4 &  iq4_add_to_new_list -> (stage'=REC_PKT_GET_IQ5) & (iq4_new_rank'=min(IQS,new_list_len+1)) & (new_list_len'=min(IQS,new_list_len+1));

	// Arrivals to input queue 5
	[REC_PKT_GET_IQ5] stage=REC_PKT_GET_IQ5 -> 0.6 : (stage'=REC_PKT_ARR_IQ5) & (iq5_arrivals'=0) + 0.1 : (stage'=REC_PKT_ARR_IQ5) & (iq5_arrivals'=1) + 0.1 : (stage'=REC_PKT_ARR_IQ5) & (iq5_arrivals'=2) + 0.1 : (stage'=REC_PKT_ARR_IQ5) & (iq5_arrivals'=3) + 0.1 : (stage'=REC_PKT_ARR_IQ5) & (iq5_arrivals'=4);
	[REC_PKT_ARR_IQ5_K0] stage=REC_PKT_ARR_IQ5 & iq5_arrivals=0 -> (stage'=DEQ) & (iq5_aipg'=iq5_aipg+1);
	[REC_PKT_ARR_IQ5_K1] stage=REC_PKT_ARR_IQ5 & iq5_arrivals=1 -> (stage'=REC_UPD_NEW_IQ5) & (iq5_contents'=min(SZ,iq5_contents+1)) & (iq5_cenq'=iq5_cenq+1) & (iq5_aipg'=0);
	[REC_PKT_ARR_IQ5_K2] stage=REC_PKT_ARR_IQ5 & iq5_arrivals=2 -> (stage'=REC_UPD_NEW_IQ5) & (iq5_contents'=min(SZ,iq5_contents+2)) & (iq5_cenq'=iq5_cenq+2) & (iq5_aipg'=0);
	[REC_PKT_ARR_IQ5_K3] stage=REC_PKT_ARR_IQ5 & iq5_arrivals=3 -> (stage'=REC_UPD_NEW_IQ5) & (iq5_contents'=min(SZ,iq5_contents+3)) & (iq5_cenq'=iq5_cenq+3) & (iq5_aipg'=0);
	[REC_PKT_ARR_IQ5_K4] stage=REC_PKT_ARR_IQ5 & iq5_arrivals=4 -> (stage'=REC_UPD_NEW_IQ5) & (iq5_contents'=min(SZ,iq5_contents+4)) & (iq5_cenq'=iq5_cenq+4) & (iq5_aipg'=0);

	// If input queue 5 is not in new or old lists, then add to new list 
	[REC_UPD_NEW_IQ5_NOP] stage=REC_UPD_NEW_IQ5 & !iq5_add_to_new_list -> (stage'=DEQ);
	[REC_UPD_NEW_IQ5_ADD] stage=REC_UPD_NEW_IQ5 &  iq5_add_to_new_list -> (stage'=DEQ) & (iq5_new_rank'=min(IQS,new_list_len+1)) & (new_list_len'=min(IQS,new_list_len+1));

	// If new list is not empty, then dequeue from first
	[DEQ_FROM_NEW_IQ1_DROP]   stage=DEQ & deq_iq1_from_new_list & iq1_contents=1 -> (stage'=REC_PKT_GET_IQ1) & (iq1_contents'=0) & (iq1_new_rank'=0) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (iq5_new_rank'=max(0,iq5_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ2_DROP]   stage=DEQ & deq_iq2_from_new_list & iq2_contents=1 -> (stage'=REC_PKT_GET_IQ1) & (iq2_contents'=0) & (iq2_new_rank'=0) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (iq5_new_rank'=max(0,iq5_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ3_DROP]   stage=DEQ & deq_iq3_from_new_list & iq3_contents=1 -> (stage'=REC_PKT_GET_IQ1) & (iq3_contents'=0) & (iq3_new_rank'=0) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (iq5_new_rank'=max(0,iq5_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ4_DROP]   stage=DEQ & deq_iq4_from_new_list & iq4_contents=1 -> (stage'=REC_PKT_GET_IQ1) & (iq4_contents'=0) & (iq4_new_rank'=0) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq5_new_rank'=max(0,iq5_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ1_TO_OLD] stage=DEQ & deq_iq1_from_new_list & iq1_contents>1 -> (stage'=REC_PKT_GET_IQ1) & (iq1_contents'=max(0,iq1_contents-1)) & (iq1_new_rank'=0) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (iq5_new_rank'=max(0,iq5_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq1_old_rank'=min(IQS,old_list_len+1)) & (old_list_len'=min(IQS,old_list_len+1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ2_TO_OLD] stage=DEQ & deq_iq2_from_new_list & iq2_contents>1 -> (stage'=REC_PKT_GET_IQ1) & (iq2_contents'=max(0,iq2_contents-1)) & (iq2_new_rank'=0) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (iq5_new_rank'=max(0,iq5_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq2_old_rank'=min(IQS,old_list_len+1)) & (old_list_len'=min(IQS,old_list_len+1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ3_TO_OLD] stage=DEQ & deq_iq3_from_new_list & iq3_contents>1 -> (stage'=REC_PKT_GET_IQ1) & (iq3_contents'=max(0,iq3_contents-1)) & (iq3_new_rank'=0) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (iq5_new_rank'=max(0,iq5_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq3_old_rank'=min(IQS,old_list_len+1)) & (old_list_len'=min(IQS,old_list_len+1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ4_TO_OLD] stage=DEQ & deq_iq4_from_new_list & iq4_contents>1 -> (stage'=REC_PKT_GET_IQ1) & (iq4_contents'=max(0,iq4_contents-1)) & (iq4_new_rank'=0) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq5_new_rank'=max(0,iq5_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq4_old_rank'=min(IQS,old_list_len+1)) & (old_list_len'=min(IQS,old_list_len+1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);

	[DEQ_FROM_NEW_IQ5_DROP_NOBL]   stage=DEQ & deq_iq5_from_new_list & iq5_contents=1 & !iqs_bl -> (stage'=REC_PKT_GET_IQ1) & (iq5_contents'=0) & (iq5_new_rank'=0) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ5_TO_OLD_NOBL] stage=DEQ & deq_iq5_from_new_list & iq5_contents>1 & !iqs_bl -> (stage'=REC_PKT_GET_IQ1) & (iq5_contents'=max(0,iq5_contents-1)) & (iq5_new_rank'=0) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq5_old_rank'=min(IQS,old_list_len+1)) & (old_list_len'=min(IQS,old_list_len+1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);

	[DEQ_FROM_NEW_IQ5_DROP_BL]   stage=DEQ & deq_iq5_from_new_list & iq5_contents=1 & iqs_bl -> (iq5_deqs_bl'=min(TIME_STEPS,iq5_deqs_bl+1)) & (stage'=REC_PKT_GET_IQ1) & (iq5_contents'=0) & (iq5_new_rank'=0) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_NEW_IQ5_TO_OLD_BL] stage=DEQ & deq_iq5_from_new_list & iq5_contents>1 & iqs_bl -> (iq5_deqs_bl'=min(TIME_STEPS,iq5_deqs_bl+1)) & (stage'=REC_PKT_GET_IQ1) & (iq5_contents'=max(0,iq5_contents-1)) & (iq5_new_rank'=0) & (iq2_new_rank'=max(0,iq2_new_rank-1)) & (iq1_new_rank'=max(0,iq1_new_rank-1)) & (iq3_new_rank'=max(0,iq3_new_rank-1)) & (iq4_new_rank'=max(0,iq4_new_rank-1)) & (new_list_len'=max(0,new_list_len-1)) & (iq5_old_rank'=min(IQS,old_list_len+1)) & (old_list_len'=min(IQS,old_list_len+1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);

	// If new list is empty, then dequeue from old list if possible
	[DEQ_FROM_OLD_IQ1_DROP]   stage=DEQ & deq_iq1_from_old_list & iq1_contents=1 -> (stage'=REC_PKT_GET_IQ1) & (iq1_contents'=0) & (iq1_old_rank'=0) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (iq5_old_rank'=max(0,iq5_old_rank-1)) & (old_list_len'=max(0,old_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ1_TO_OLD] stage=DEQ & deq_iq1_from_old_list & iq1_contents>1 -> (stage'=REC_PKT_GET_IQ1) & (iq1_contents'=max(0,iq1_contents-1)) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (iq5_old_rank'=max(0,iq5_old_rank-1)) & (iq1_old_rank'=old_list_len) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ2_DROP]   stage=DEQ & deq_iq2_from_old_list & iq2_contents=1 -> (stage'=REC_PKT_GET_IQ1) & (iq2_contents'=0) & (iq2_old_rank'=0) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (iq5_old_rank'=max(0,iq5_old_rank-1)) & (old_list_len'=max(0,old_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ2_TO_OLD] stage=DEQ & deq_iq2_from_old_list & iq2_contents>1 -> (stage'=REC_PKT_GET_IQ1) & (iq2_contents'=max(0,iq2_contents-1)) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (iq5_old_rank'=max(0,iq5_old_rank-1)) & (iq2_old_rank'=old_list_len) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ3_DROP]   stage=DEQ & deq_iq3_from_old_list & iq3_contents=1 -> (stage'=REC_PKT_GET_IQ1) & (iq3_contents'=0) & (iq3_old_rank'=0) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (iq5_old_rank'=max(0,iq5_old_rank-1)) & (old_list_len'=max(0,old_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ3_TO_OLD] stage=DEQ & deq_iq3_from_old_list & iq3_contents>1 -> (stage'=REC_PKT_GET_IQ1) & (iq3_contents'=max(0,iq3_contents-1)) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (iq5_old_rank'=max(0,iq5_old_rank-1)) & (iq3_old_rank'=old_list_len) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ4_DROP]   stage=DEQ & deq_iq4_from_old_list & iq4_contents=1 -> (stage'=REC_PKT_GET_IQ1) & (iq4_contents'=0) & (iq4_old_rank'=0) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq5_old_rank'=max(0,iq5_old_rank-1)) & (old_list_len'=max(0,old_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ4_TO_OLD] stage=DEQ & deq_iq4_from_old_list & iq4_contents>1 -> (stage'=REC_PKT_GET_IQ1) & (iq4_contents'=max(0,iq4_contents-1)) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq5_old_rank'=max(0,iq5_old_rank-1)) & (iq4_old_rank'=old_list_len) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);

	[DEQ_FROM_OLD_IQ5_DROP_NOBL]   stage=DEQ & deq_iq5_from_old_list & iq5_contents=1 & !iqs_bl -> (stage'=REC_PKT_GET_IQ1) & (iq5_contents'=0) & (iq5_old_rank'=0) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (old_list_len'=max(0,old_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ5_TO_OLD_NOBL] stage=DEQ & deq_iq5_from_old_list & iq5_contents>1 & !iqs_bl -> (stage'=REC_PKT_GET_IQ1) & (iq5_contents'=max(0,iq5_contents-1)) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (iq5_old_rank'=old_list_len) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);

	[DEQ_FROM_OLD_IQ5_DROP_BL]   stage=DEQ & deq_iq5_from_old_list & iq5_contents=1 & iqs_bl -> (iq5_deqs_bl'=min(TIME_STEPS,iq5_deqs_bl+1)) & (stage'=REC_PKT_GET_IQ1) & (iq5_contents'=0) & (iq5_old_rank'=0) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (old_list_len'=max(0,old_list_len-1)) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
	[DEQ_FROM_OLD_IQ5_TO_OLD_BL] stage=DEQ & deq_iq5_from_old_list & iq5_contents>1 & iqs_bl -> (iq5_deqs_bl'=min(TIME_STEPS,iq5_deqs_bl+1)) & (stage'=REC_PKT_GET_IQ1) & (iq5_contents'=max(0,iq5_contents-1)) & (iq2_old_rank'=max(0,iq2_old_rank-1)) & (iq1_old_rank'=max(0,iq1_old_rank-1)) & (iq3_old_rank'=max(0,iq3_old_rank-1)) & (iq4_old_rank'=max(0,iq4_old_rank-1)) & (iq5_old_rank'=old_list_len) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);

	// Otherwise, skip dequeue
	[DEQ_NOP] stage=DEQ & lists_empty -> (stage'=REC_PKT_GET_IQ1) & (iq1_arrivals'=0) & (iq2_arrivals'=0) & (iq3_arrivals'=0) & (iq4_arrivals'=0) & (iq5_arrivals'=0) & (time'=time+1);
endmodule

//rewards "iq5_deq_while_iq1_to_iq4_bl"
//   [DEQ_FROM_NEW_IQ5_DROP_BL]   iq1_backlogged & iq2_backlogged & iq3_backlogged & iq4_backlogged : 1;
//   [DEQ_FROM_NEW_IQ5_TO_OLD_BL] iq1_backlogged & iq2_backlogged & iq3_backlogged & iq4_backlogged : 1;
//   [DEQ_FROM_OLD_IQ5_DROP_BL]   iq1_backlogged & iq2_backlogged & iq3_backlogged & iq4_backlogged : 1;
//   [DEQ_FROM_OLD_IQ5_TO_OLD_BL] iq1_backlogged & iq2_backlogged & iq3_backlogged & iq4_backlogged : 1;
//endrewards
// Round robin scheduler
// 2 inputs (L, R) and 1 output (O), 2 program states (L, R)
// Buffers have length 2: states are tuples (NN, NN), (1N, 2N), ...
// Packet types Σ = {N,1,2} 
// 0-1 packets arrive at each time step (N = “no packet arrived”)

// Constraints:
// L gets packets of type N or 1
//   and ∆_2 (#1) ≥ 1/2 (at least one 1 per two packets)
// R gets packets of type 2 only
// Thus, Act = {(N,2), (1,2)} is the set of possible actions.

mdp

// formulae 
formula emptyl = (rr1_b11=0 & rr1_b12=0);
formula emptyr = (rr1_b21=0 & rr1_b22=0);

formula state0 = (rr1_ndq=1 & emptyl & emptyr & rr1_wrote_2=0);
formula state1 = (rr1_ndq=1 & emptyl & emptyr & rr1_wrote_2=2);
formula state2 = (rr1_ndq=2 & emptyl & rr1_b11=2 & rr1_b12=0);
formula state3 = (rr1_ndq=1 & emptyl & rr1_b11=2 & rr1_b12=0);
formula state4 = 

module rr1

	rr1_ndq: [1..2] init 1; // next dequeue from: 1=L, 2=R
	rr1_b11: [0..2] init 0; // buff 1, pos 1 contains 0,1,2 packet
	rr1_b12: [0..2] init 0; // buff 1, pos 2 contains 0,1,2 packet
	rr1_b21: [0..2] init 0; // buff 2, pos 1 contains 0,1,2 packet
	rr1_b22: [0..2] init 0; // buff 2, pos 2 contains 0,1,2 packet
	
	rr1_wrote_1: [0..2] init 0; // wrote pkt from L buffer
	rr1_wrote_2: [0..2] init 0; // wrote pkt from R buffer
	rr1_dropped_1: [0..1] init 0; // dropped from L buffer
	rr1_dropped_2: [0..1] init 0; // dropped from R buffer

	[a02] rr1_ndq=1 & emptyl & emptyr & rr1_wrote_2=0 -> (rr1_ndq'=1) & (rr1_wrote_2'=2);
	[a12] rr1_ndq=1 & emptyl & emptyr -> (rr1_ndq'=2) & (rr1_b21'=2);

	[a12] rr1_ndq=1 & emptyl & emptyr & rr1_wrote_2=2 -> (rr1_ndq'=2) & (rr1_b11'=2) & (rr1_wrote_1'=1) & (rr1_wrote_2'=0);

endmodule

// construct further modules through renaming
// module phil2 = phil1 [ p1=p2, p2=p3, p3=p1 ] endmodule
// module phil3 = phil1 [ p1=p3, p2=p1, p3=p2 ] endmodule

// labels

// a philosopher is hungry
// label "hungry" = ((p1>0)&(p1<8))|((p2>0)&(p2<8))|((p3>0)&(p3<8)); 
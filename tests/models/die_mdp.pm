// Knuth's model of a fair die using only fair coins
mdp

module die

	// local state
	s : [0..7] init 0;
	// value of the dice
	d : [0..6] init 0;
	
	[a0] s=0 -> 1 : (s'=1);
	[b0] s=0 -> 1 : (s'=2);
	[a1] s=1 -> 1 : (s'=3);
	[b1] s=1 -> 1 : (s'=4);
	[a2] s=2 -> 1 : (s'=5);
	[b2] s=2 -> 1 : (s'=6);
	[a3] s=3 -> 1 : (s'=1);
	[b3] s=3 -> 1 : (s'=7) & (d'=1);
	[a4] s=4 -> 1 : (s'=7) & (d'=2);
	[b4] s=4 -> 1 : (s'=7) & (d'=3);
	[a5] s=5 -> 1 : (s'=7) & (d'=4);
	[b5] s=5 -> 1 : (s'=7) & (d'=5);
	[a6] s=6 -> 1 : (s'=2);
	[b6] s=6 -> 1 : (s'=7) & (d'=6);
	[a7] s=7 -> 1 : (s'=7);
	
endmodule

label "one" = s=7&d=1;
label "two" = s=7&d=2;
label "three" = s=7&d=3;
label "four" = s=7&d=4;
label "five" = s=7&d=5;
label "six" = s=7&d=6;
label "done" = s=7;

// Small multi-module MDP used to test the native JANI compiler's parallel composition against Storm:
// three-way synchronisation (handoff), probabilistic branches inside synchronised commands, a renamed module,
// silent (unlabelled) interleaving commands, a global variable and nondeterminism.
mdp

const int N = 3;

global g : [0..4] init 0;

module producer
	p : [0..N] init 0;
	[produce] p < N -> 0.7:(p'=p+1) + 0.3:(p'=p);
	[handoff] p > 0 -> 0.9:(p'=p-1) + 0.1:(p'=0);
	[] p = N & g < 4 -> (g'=g+1);
endmodule

module consumer
	c : [0..N] init 0;
	[handoff] c < N -> (c'=c+1);
	[consume] c > 0 -> 0.5:(c'=c-1) + 0.5:(c'=max(0, c-2));
endmodule

module consumer2 = consumer [c=c2, consume=consume2] endmodule

module monitor
	seen : bool init false;
	[handoff] true -> 0.25:(seen'=true) + 0.75:(seen'=seen);
	[] seen & g > 0 -> (g'=g-1) & (seen'=false);
endmodule

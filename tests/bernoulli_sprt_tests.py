from src.smc.sampler.bernoulli_sampler import BernoulliSampler
from tests.plots import plot_sprt_results
from tests.sprt_test_runner import SPRTTwoHypParams, run_sprt_two_hyp, SPRTOneHypParams, run_sprt_one_hyp


def bernoulli_two_hyp_sprt_test():
    # params = SPRTTwoHypParams(theta=0.001, alpha=0.05, beta=0.1, delta=0.00005, p_minus=0.0009, p_plus=0.0011, N=20, seed=1)
    params = SPRTTwoHypParams(theta=0.15, alpha=0.05, beta=0.1, delta=0.005, p_minus=0.14, p_plus=0.16, N=1000, seed=1)
    results = run_sprt_two_hyp(params, lambda p: BernoulliSampler(p))
    print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    print(f"Empirical type I  error: {results['type_I']:.3f} (target = {params.alpha})")
    print(f"Empirical type II error: {results['type_II']:.3f} (target = {params.beta})")
    plot_sprt_results(results)

def bernoulli_one_hyp_sprt_test():
    params = SPRTOneHypParams(theta=0.15, alpha=0.025, beta=0.025, delta=0.01, N=200, seed=1)
    results = run_sprt_one_hyp(params, BernoulliSampler(0.167))
    print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

if __name__ == "__main__":
    # bernoulli_two_hyp_sprt_test()
    bernoulli_one_hyp_sprt_test()
from src.netmdp.sampler.bernoulli_sampler import BernoulliSampler
from tests.cr_test_runner import CRTwoHypParams, run_cr_two_hyp, CROneHypParams, run_cr_one_hyp
from tests.plots import plot_cr_results


def bernoulli_two_hyp_sprt_test():
    params = CRTwoHypParams(theta=0.01, alpha=0.01, beta=0.05, zeta=0.0005, p_minus=0.00949, p_plus=0.01051, N=100, seed=1)
    # params = CRParams(theta=0.5, alpha=0.05, beta=0.1, zeta=0.05, p_minus=0.4, p_plus=0.6, N=20, seed=1)
    results = run_cr_two_hyp(params, lambda p: BernoulliSampler(p))
    print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    print(f"Empirical type I  error: {results['type_I']:.3f} (target = {params.alpha})")
    print(f"Empirical type II error: {results['type_II']:.3f} (target = {params.beta})")
    plot_cr_results(results)


def bernoulli_one_hyp_sprt_test():
    params = CROneHypParams(theta=0.15, alpha=0.025, beta=0.025, zeta=0.01, N=200, seed=1)
    results = run_cr_one_hyp(params, BernoulliSampler(0.167))
    print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    print(f"Percent inconclusive: {results['pct_inconcl']:.3f} (N = {params.N})")
    print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

if __name__ == "__main__":
    # bernoulli_two_hyp_sprt_test()
    bernoulli_one_hyp_sprt_test()
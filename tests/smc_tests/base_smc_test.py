import stormpy

import stormpy.examples
import stormpy.examples.files
import stormpy.simulator

from src.smc.sampler.base_smc_sampler import BaseSMCSampler
from tests.cr_test_runner import CROneHypParams, run_cr_one_hyp
from tests.sprt_test_runner import SPRTOneHypParams, run_sprt_one_hyp


def base_smc_cr_test():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/die.pm"
    prism_program = stormpy.parse_prism_program(path)
    sampler = BaseSMCSampler("die", prism_program,"F<=12 s=7 & d=2", 12)

    params = CROneHypParams(theta=0.15, alpha=0.025, beta=0.025, zeta=0.01, N=200, seed=1)
    results = run_cr_one_hyp(params, sampler)
    print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    print(f"Percent inconclusive: {results['pct_inconcl']:.3f} (N = {params.N})")
    print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")


def base_smc_sprt_test():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/die.pm"
    prism_program = stormpy.parse_prism_program(path)
    sampler = BaseSMCSampler("die", prism_program,"F<=12 s=7 & d=2", 12)

    params = SPRTOneHypParams(theta=0.15, alpha=0.025, beta=0.025, delta=0.01, N=200, seed=1)
    results = run_sprt_one_hyp(params, sampler)
    print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def example_base_smc_run():
    path = stormpy.examples.files.prism_dtmc_die
    prism_program = stormpy.parse_prism_program(path)

    sampler = BaseSMCSampler("die", prism_program,"F<=12 s=7 & d>1", 12)
    return sampler.sample()

if __name__ == "__main__":
    example_base_smc_run()
    # base_smc_sprt_test()
    # base_smc_cr_test()
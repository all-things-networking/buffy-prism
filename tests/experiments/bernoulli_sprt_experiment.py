import json

import stormpy

import stormpy.examples
import stormpy.examples.files
import stormpy.simulator

from src.smc.sampler.base_symbolic_smc_sampler import BaseSymbolicSMCSampler
from src.smc.sampler.bernoulli_sampler import BernoulliSampler
from tests.cr_test_runner import CROneHypParams, run_cr_one_hyp
from tests.sprt_test_runner import SPRTOneHypParams, run_sprt_one_hyp


def bernoulli_sprt_exp_p3():
    params = SPRTOneHypParams(theta=0.0003, alpha=0.05, beta=0.05, delta=0.000025, N=50, seed=1)
    results = run_sprt_one_hyp(params, BernoulliSampler(0.0003824))
    with open(f"bernoulli_sprt_p3.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done bernoulli_sprt_p3")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def bernoulli_sprt_exp_p2():
    params = SPRTOneHypParams(theta=0.011, alpha=0.05, beta=0.05, delta=0.001, N=50, seed=1)
    results = run_sprt_one_hyp(params, BernoulliSampler(0.01295))
    with open(f"bernoulli_sprt_p2.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done bernoulli_sprt_p2")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def bernoulli_sprt_exp_p1():
    params = SPRTOneHypParams(theta=0.65, alpha=0.05, beta=0.05, delta=0.05, N=50, seed=1)
    results = run_sprt_one_hyp(params, BernoulliSampler(0.714))
    with open(f"bernoulli_sprt_p1.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done bernoulli_sprt_p1")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def experiment_base_smc_run():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>4)"
    sampler = BaseSymbolicSMCSampler("fqcodel_5i", prism_program, phi, 154, 5)
    return sampler.sample()

if __name__ == "__main__":
    # experiment_base_smc_run()
    # base_smc_cr_exp_p1()
    bernoulli_sprt_exp_p1()
    # base_smc_cr_test()
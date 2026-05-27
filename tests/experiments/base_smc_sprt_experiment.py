import json

import stormpy

import stormpy.examples
import stormpy.examples.files
import stormpy.simulator

from src.smc.sampler.base_symbolic_smc_sampler import BaseSymbolicSMCSampler
from tests.sprt_test_runner import SPRTOneHypParams, run_sprt_one_hyp

def base_smc_sprt_exp_p3(trial: int):
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>8)"
    sampler = BaseSymbolicSMCSampler("fqcodel_5i", prism_program, phi, 154, 9)

    params = SPRTOneHypParams(theta=0.00015, alpha=0.05, beta=0.05, delta=0.0001, N=1, seed=1)
    results = run_sprt_one_hyp(params, sampler)
    with open(f"base_smc_sprt_p3_t{trial}.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done base_smc_sprt_p3_t{trial}")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def base_smc_sprt_exp_p2(trial: int):
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>4)"
    sampler = BaseSymbolicSMCSampler("fqcodel_5i", prism_program, phi, 154, 5)

    params = SPRTOneHypParams(theta=0.011, alpha=0.05, beta=0.05, delta=0.001, N=1, seed=1)
    results = run_sprt_one_hyp(params, sampler)
    with open(f"base_smc_sprt_p2_t{trial}.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done base_smc_sprt_p2_t{trial}")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def base_smc_sprt_exp_p1(trial: int):
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>2)"
    sampler = BaseSymbolicSMCSampler("fqcodel_5i", prism_program, phi, 154, 3)

    params = SPRTOneHypParams(theta=0.65, alpha=0.05, beta=0.05, delta=0.05, N=1, seed=1)
    results = run_sprt_one_hyp(params, sampler)
    with open(f"base_smc_sprt_p1_t{trial}.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done base_smc_sprt_p1_t{trial}")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def experiment_base_smc_run():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>4)"
    sampler = BaseSymbolicSMCSampler("fqcodel_5i", prism_program, phi, 154)
    return sampler.sample()

if __name__ == "__main__":
    # experiment_base_smc_run()
    base_smc_sprt_exp_p1(1)
    # base_smc_cr_test()
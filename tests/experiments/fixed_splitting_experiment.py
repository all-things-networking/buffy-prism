import json

import stormpy

import stormpy.examples
import stormpy.examples.files
import stormpy.simulator

from src.smc.sampler.fixed_splitting_smc_sampler import FixedSplittingSMCSampler
from tests.cr_test_runner import CROneHypParams, run_cr_one_hyp
from tests.prism_examples.importance_fqcodel_5i import ImportanceFQCodel


def fixed_splitting_cr_exp_p3(trial: int):
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>8)"
    importance = ImportanceFQCodel(prism_program, phi, 154, 14, 4)

    expected_success_effort = 256
    sampler = FixedSplittingSMCSampler("fqcodel_5i", prism_program, phi, 154,
                                    9, importance, expected_success_effort)

    params = CROneHypParams(theta=0.00015, alpha=0.05, beta=0.05, zeta=0.0001, N=1, seed=1)
    results = run_cr_one_hyp(params, sampler)
    with open(f"fixed_splitting_cr_p3_t{trial}.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done fixed_splitting_cr_p3_t{trial}")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def fixed_splitting_cr_exp_p2(trial: int):
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>4)"
    importance = ImportanceFQCodel(prism_program, phi, 154, 14, 2)

    expected_success_effort = 256
    sampler = FixedSplittingSMCSampler("fqcodel_5i", prism_program, phi, 154,
                                    5, importance, expected_success_effort)

    params = CROneHypParams(theta=0.011, alpha=0.05, beta=0.05, zeta=0.001, N=1, seed=1)
    results = run_cr_one_hyp(params, sampler)
    with open(f"fixed_splitting_cr_p2_t{trial}.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done fixed_splitting_cr_p2_t{trial}")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def fixed_splitting_cr_exp_p1():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>2)"
    importance = ImportanceFQCodel(prism_program, phi, 154, 14, 1)

    expected_success_effort = 256
    sampler = FixedSplittingSMCSampler("fqcodel_5i", prism_program, phi, 154,
                                    3, importance, expected_success_effort)

    params = CROneHypParams(theta=0.65, alpha=0.05, beta=0.05, zeta=0.05, N=24, seed=1)
    results = run_cr_one_hyp(params, sampler)
    with open(f"fixed_splitting_cr_p1.json", "w") as f:
        json.dump(results, f, indent=4)
    print(f"done fixed_splitting_cr_p1")
    # print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    # print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def experiment_fixed_splitting_run():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/fqcodel_5i_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)
    phi = "(true) U<=154 (iq5_deqs_bl>2)"
    importance = ImportanceFQCodel(prism_program, phi, 154, 14, 1)

    expected_success_effort = 256
    sampler = FixedSplittingSMCSampler("fqcodel_5i", prism_program, phi, 154,
                                    3, importance, expected_success_effort)
    return sampler.sample()

if __name__ == "__main__":
    experiment_fixed_splitting_run()
    # fixed_splitting_cr_exp_p1(1)
    # fixed_splitting_cr_exp_p2(1)
    # base_smc_cr_test()
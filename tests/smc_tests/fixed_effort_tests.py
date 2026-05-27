import stormpy

import stormpy.examples
import stormpy.examples.files
import stormpy.simulator

from src.smc.sampler.fixed_effort_smc_sampler import FixedEffortSMCSampler
from tests.cr_test_runner import CROneHypParams, run_cr_one_hyp
from tests.prism_examples.importance_die import ImportanceDie

def fixed_effort_es_cr_test():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/die_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)

    phi = "F<=12 s=7 & d=2"
    trace_len = 12

    importance = ImportanceDie(prism_program, phi, trace_len)

    user_effort = 8
    expected_success_effort = 256

    sampler = FixedEffortSMCSampler("die", prism_program,phi, trace_len,
                                    importance,
                                    user_effort,
                                    expected_success_effort)

    params = CROneHypParams(theta=0.15, alpha=0.025, beta=0.025, zeta=0.01, N=200, seed=1)
    results = run_cr_one_hyp(params, sampler)
    print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    print(f"Percent inconclusive: {results['pct_inconcl']:.3f} (N = {params.N})")
    print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def fixed_effort_cr_test():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/die_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)

    phi = "F<=12 s=7 & d=2"
    trace_len = 12

    importance = ImportanceDie(prism_program, phi, trace_len)

    user_effort = 8
    all_levels = importance.get_all_levels()
    max_level = max(all_levels)
    const_splits = len(all_levels) * [user_effort]

    sampler = FixedEffortSMCSampler("die", prism_program,phi, trace_len,
                                    importance,
                                    user_effort,
                                    all_levels,
                                    const_splits,
                                    max_level)

    params = CROneHypParams(theta=0.15, alpha=0.025, beta=0.025, zeta=0.01, N=200, seed=1)
    results = run_cr_one_hyp(params, sampler)
    print(f"Average stopping time: {results['stopping_times'].mean():.2f}")
    print(f"Percent inconclusive: {results['pct_inconcl']:.3f} (N = {params.N})")
    print(f"Empirical type I error: {results['type_I']:.3f} (target = {params.alpha})")

def example_fixed_effort_smc_run():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/die_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)

    phi = "F<=12 s=7 & d=2"
    trace_len = 12

    importance = ImportanceDie(prism_program, phi, trace_len)

    user_effort = 8
    all_levels = importance.get_all_levels()
    max_level = max(all_levels)
    const_splits = len(all_levels) * [user_effort]

    sampler = FixedEffortSMCSampler("die", prism_program,phi, trace_len,
                                    importance,
                                    user_effort,
                                    all_levels,
                                    const_splits,
                                    max_level)
    return sampler.sample()

if __name__ == "__main__":
    # example_fixed_effort_smc_run()
    # fixed_effort_cr_test()
    fixed_effort_es_cr_test()
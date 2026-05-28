import stormpy

from src.netmdp.sampler.fixed_splitting_smc_sampler import FixedSplittingSMCSampler
from tests.models.importance_die import ImportanceDieOneRedundant


def example_expected_splitting_run():
    path = "/Users/jkai/535C-project-smc/tests/prism_examples/die_mdp.pm"
    prism_program = stormpy.parse_prism_program(path)

    phi = "F<=12 s=7 & d=1"
    trace_len = 12

    importance = ImportanceDieOneRedundant(prism_program, phi, trace_len)

    user_effort = 8

    sampler = FixedSplittingSMCSampler("die", prism_program,phi, trace_len,
                                    importance,
                                    user_effort)
    return None

if __name__ == "__main__":
    example_expected_splitting_run()
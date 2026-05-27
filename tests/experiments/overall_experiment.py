from tests.experiments.base_smc_cr_experiment import base_smc_cr_exp_p1, base_smc_cr_exp_p2, base_smc_cr_exp_p3
from tests.experiments.base_smc_sprt_experiment import base_smc_sprt_exp_p1, base_smc_sprt_exp_p2, base_smc_sprt_exp_p3
from tests.experiments.bernoulli_cr_experiment import bernoulli_cr_exp_p1, bernoulli_cr_exp_p2, bernoulli_cr_exp_p3
from tests.experiments.bernoulli_sprt_experiment import bernoulli_sprt_exp_p1, bernoulli_sprt_exp_p2, \
    bernoulli_sprt_exp_p3
from tests.experiments.fixed_effort_experiment import fixed_effort_cr_exp_p1, fixed_effort_cr_exp_p2, \
    fixed_effort_cr_exp_p3
from tests.experiments.fixed_splitting_experiment import fixed_splitting_cr_exp_p1, fixed_splitting_cr_exp_p2, \
    fixed_splitting_cr_exp_p3


def overall_experiment():
    for t in range(4,12):
        try:
            base_smc_sprt_exp_p3(t)
        except Exception as e:
            # Catch any other unexpected exceptions
            print(f"An unexpected error occurred for base_smc_sprt_exp_p3, trial {t}: {e}. Skipping to next item.")
            continue  # Skip to the next item
        try:
            base_smc_cr_exp_p3(t)
        except Exception as e:
            # Catch any other unexpected exceptions
            print(f"An unexpected error occurred for base_smc_cr_exp_p3, trial {t}: {e}. Skipping to next item.")
            continue  # Skip to the next item
        try:
            fixed_splitting_cr_exp_p3(t)
        except Exception as e:
            # Catch any other unexpected exceptions
            print(f"An unexpected error occurred for fixed_splitting_cr_exp_p3, trial {t}: {e}. Skipping to next item.")
            continue  # Skip to the next item
        try:
            fixed_effort_cr_exp_p3(t)
        except Exception as e:
            # Catch any other unexpected exceptions
            print(f"An unexpected error occurred for fixed_effort_cr_exp_p3, trial {t}: {e}. Skipping to next item.")
            continue  # Skip to the next item


if __name__ == "__main__":
    overall_experiment()
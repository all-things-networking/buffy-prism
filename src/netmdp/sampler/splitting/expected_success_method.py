import numpy as np
from stormpy import PrismProgram

from src.netmdp.sampler.splitting.importance_function import ImportanceFunction


class ExpectedSuccess:
    def __init__(self, model_name: str, program: PrismProgram, phi: str, trace_len: int,
                 goal_deq: int, importance: ImportanceFunction, n: int):
        self.model_name = model_name
        self.program = program
        self.phi = phi
        self.trace_len = trace_len
        self.goal_deq = goal_deq
        self.importance = importance
        self.n = n

    def get_levels_splits(self):
        import src.smc.sampler.fixed_effort_smc_sampler
        all_levels = self.importance.get_all_levels()
        max_level = max(all_levels)
        const_splits = len(all_levels) * [self.n]
        generic_fe_sampler = src.smc.sampler.fixed_effort_smc_sampler.FixedEffortSMCSampler(
            self.model_name, self.program, self.phi, self.trace_len, self.goal_deq,
            self.importance, self.n, None, all_levels, const_splits, max_level)

        m = 0
        p_up = np.zeros(len(all_levels))
        while p_up[-1] == 0:
            m += 1
            s = generic_fe_sampler.get_success_vector()
            for l in range(len(all_levels)):
                p_up[l] += ((s[l])/self.n - p_up[l])

        err = 0.0
        thresh_factors = np.zeros(len(all_levels), dtype=int)
        for l in range(len(all_levels)):
            split_factor = err + (1/p_up[l])
            thresh_factors[l] = np.floor(split_factor + 0.5).astype(int)
            err = split_factor - thresh_factors[l]

        # thresholds = thresh_factors > 1.0
        # num_thresholds = np.sum(thresholds)
        imp_to_level = []
        splits = []
        max_level = 0
        for i in all_levels:
            if i == 0 and thresh_factors[i] <= 1:
                splits.append(1)
            if thresh_factors[i] > 1.0:
                max_level += 1
                splits.append(thresh_factors[i])
            imp_to_level.append(max_level)
        return imp_to_level, splits, max_level

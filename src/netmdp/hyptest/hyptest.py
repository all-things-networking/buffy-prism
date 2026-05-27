import time
from enum import Enum

import numpy as np

from ..sampler.sampler import Sampler


class HypTestError(Exception):
    """A custom exception for hypothesis test errors."""
    pass

class ErrTols:
    def __init__(self, alpha: float, beta: float):
        if alpha < 0 or alpha > 1:
            raise HypTestError("alpha must be between 0 and 1.")
        if beta < 0 or beta > 1:
            raise HypTestError("beta must be between 0 and 1.")
        self.alpha = alpha
        self.beta = beta

    def __str__(self):
        return "({:e},{:e})".format(self.alpha, self.beta)

    def get_alpha(self) -> float:
        return self.alpha

    def get_beta(self) -> float:
        return self.beta

class HypResult(Enum):
    ACCEPT_H_MINUS = 1
    ACCEPT_H_PLUS = 2
    INCONCLUSIVE = 3

class HypTestResult:
    def __init__(self, result: HypResult, n: int, sample_mean: float, sample_var: float, wall_time: float):
        self.result = result
        self.n = n
        self.sample_mean = sample_mean
        self.sample_var = sample_var
        self.wall_time = wall_time

    def get_result(self) -> HypResult:
        return self.result

    def get_n(self):
        return self.n

    def get_wall_time(self):
        return self.wall_time

    def get_sample_mean(self):
        return self.sample_mean

    def get_sample_var(self):
        return self.sample_var

    # def rel_error(self) -> float:
    #     return np.sqrt(self.sample_var) / self.sample_mean
    #
    # def asym_eff_n(self) -> float:
    #     return self.sample_var * self.n / np.power(self.sample_mean, 2)
    #
    # def asym_eff_t(self) -> float:
    #     return self.sample_var * self.wall_time / np.power(self.sample_mean, 2)

class HypTest:
    def __init__(self, theta: float, err_tols: ErrTols, indifference: float, max_samples: int):
        self.start_time = None
        self.theta = theta
        self.err_tols = err_tols
        self.max_samples = max_samples
        self.indifference = indifference

    def tick(self):
        self.start_time = time.perf_counter()
        
    def tock(self):
        return time.perf_counter() - self.start_time

    def get_alpha(self) -> float:
        return self.err_tols.get_alpha()

    def get_beta(self) -> float:
        return self.err_tols.get_beta()

    def run_test(self, sampler: Sampler) -> HypTestResult:
        pass
from collections import namedtuple

import numpy as np

from src.smc.hyptest.hyptest import ErrTols, HypResult
from src.smc.hyptest.wald_sprt import WaldSprt

SPRTTwoHypParams = namedtuple('SPRTTwoHypParams',
                [
                'theta', # Parameter estimate
                'alpha', 'beta',  # Target type I and type II errors
                'delta', # Indifference parameter
                'p_minus', 'p_plus', # Bernoulli parameters for f_minus, f_plus
                'N',        # Number of simulations
                'seed'])

SPRTOneHypParams = namedtuple('SPRTOneHypParams',
                [
                'theta', # Parameter estimate
                'alpha', 'beta',  # Target type I and type II errors
                'delta', # Indifference parameter
                'N',        # Number of simulations
                'seed'])

def run_sprt_simulation_two_hyp(theta, alpha, beta, delta, sampler_minus, sampler_plus, N, seed):
    """SPRT simulation."""
    sprt_runner = WaldSprt(theta, ErrTols(alpha, beta), delta, 1)

    stopping_times = np.zeros(N, dtype=np.int64)
    decisions_h_minus = np.zeros(N, dtype=np.bool_)
    truth_h_minus = np.zeros(N, dtype=np.bool_)

    for i in range(N):
        true_f_minus = (i % 2 == 0)
        truth_h_minus[i] = true_f_minus
        result = sprt_runner.run_test(sampler_minus) \
            if true_f_minus else (
                sprt_runner.run_test(sampler_plus))
        print("ran trial {}".format(i))
        stopping_times[i] = result.get_n()
        decisions_h_minus[i] = result.get_result() == HypResult.ACCEPT_H_MINUS

    return stopping_times, decisions_h_minus, truth_h_minus


def run_sprt_two_hyp(params, sampler_generator):
    """Run SPRT simulations with given parameters."""
    sampler_minus = sampler_generator(params.p_minus)
    sampler_plus = sampler_generator(params.p_plus)
    stopping_times, decisions_h_minus, truth_h_minus = run_sprt_simulation_two_hyp(
        params.theta, params.alpha, params.beta, params.delta,
        sampler_minus, sampler_plus,
        params.N, params.seed
    )

    # Calculate error rates
    truth_h_minus_bool = truth_h_minus.astype(bool)
    decisions_h_minus_bool = decisions_h_minus.astype(bool)

    type_I = np.sum(~truth_h_minus_bool & decisions_h_minus_bool) / np.sum(~truth_h_minus_bool)
    type_II = np.sum(truth_h_minus_bool & ~decisions_h_minus_bool) / np.sum(truth_h_minus_bool)

    return {
        'stopping_times': stopping_times,
        'decisions_h_minus': decisions_h_minus_bool,
        'truth_h_minus': truth_h_minus_bool,
        'type_I': type_I,
        'type_II': type_II
    }


def run_sprt_simulation_one_hyp(theta, alpha, beta, delta, sampler, N, seed):
    """SPRT simulation."""
    sprt_runner = WaldSprt(theta, ErrTols(alpha, beta), delta, 1)

    stopping_times = np.zeros(N, dtype=np.int64)
    wall_times = np.zeros(N, dtype=np.float64)
    sample_means = np.zeros(N, dtype=np.float64)
    sample_vars = np.zeros(N, dtype=np.float64)
    decisions_h_minus = np.zeros(N, dtype=np.bool_)

    for i in range(N):
        result = sprt_runner.run_test(sampler)
        # print("ran trial {}, accept H_-1={}".format(i, result.get_result() == HypResult.ACCEPT_H_MINUS))
        stopping_times[i] = result.get_n()
        wall_times[i] = result.get_wall_time()
        sample_means[i] = result.get_sample_mean()
        sample_vars[i] = result.get_sample_var()
        decisions_h_minus[i] = result.get_result() == HypResult.ACCEPT_H_MINUS

    return stopping_times, wall_times, sample_means, sample_vars, decisions_h_minus


def run_sprt_one_hyp(params, sampler):
    """Run SPRT simulations with given parameters."""
    stopping_times, wall_times, sample_means, sample_vars, decisions_h_minus = run_sprt_simulation_one_hyp(
        params.theta, params.alpha, params.beta, params.delta,
        sampler, params.N, params.seed
    )

    # Calculate error rates
    stopping_times = [int(st) for st in stopping_times]
    wall_times = [float(wt) for wt in wall_times]
    sample_means = [float(sm) for sm in sample_means]
    sample_vars = [float(sv) for sv in sample_vars]
    decisions_h_minus_bool = [bool(d) for d in decisions_h_minus]
    # type_I = (np.sum(decisions_h_minus_bool) / params.N).astype(float)

    return {
        'stopping_times': stopping_times,
        'wall_times': wall_times,
        'sample_means': sample_means,
        'sample_vars': sample_vars,
        'decisions_h_minus': decisions_h_minus_bool,
        # 'type_I': type_I,
    }

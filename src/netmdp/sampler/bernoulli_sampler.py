from scipy.stats import bernoulli

from src.netmdp.sampler.sampler import Sampler, SamplerError


class BernoulliSampler(Sampler):
    def __init__(self, p: float):
        super().__init__()
        if p < 0 or p > 1:
            raise SamplerError(self.__str__() + ": p must lie in [0,1].")
        self.p = p

    def __str__(self):
        return "Bernoulli({}) sampler".format(self.p)

    def sample(self) -> float:
        return bernoulli.rvs(self.p)

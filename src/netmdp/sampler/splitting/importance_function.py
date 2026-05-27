import numpy as np
from numpy.typing import NDArray
from stormpy import PrismProgram


class ImportanceFunction:
    def __init__(self, program: PrismProgram, phi: str, trace_len: int):
        self.program = program
        self.phi = phi
        self.trace_len = trace_len

    def get_all_levels(self):
        pass

    def get_importance(self, state, prev_importance) -> int:
        pass
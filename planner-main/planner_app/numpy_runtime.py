"""Lazy array runtime shared by geometry and raster processing."""
import os
from functools import lru_cache


@lru_cache(maxsize = 1)
def LoadNumPy():
    # Elementwise work needs no BLAS pool. Configure before import: its default
    # Windows pool can otherwise exhaust the bounded preview process's memory.
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    import numpy
    return numpy

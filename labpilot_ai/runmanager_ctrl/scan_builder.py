import numpy as np


def linspace(start, stop, num):
    return np.linspace(float(start), float(stop), int(num))


def arange(start, stop, step):
    return np.arange(float(start), float(stop), float(step))

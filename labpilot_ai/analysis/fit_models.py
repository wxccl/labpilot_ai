import numpy as np


def linear(x, a, b):
    return a * np.asarray(x) + b


def gaussian(x, amp, x0, sigma, offset):
    x = np.asarray(x)
    return amp * np.exp(-0.5 * ((x - x0) / sigma) ** 2) + offset


def exponential(x, amp, tau, offset):
    x = np.asarray(x)
    return amp * np.exp(-x / tau) + offset


def lorentzian(x, amp, x0, gamma, offset):
    x = np.asarray(x)
    return amp * gamma**2 / ((x - x0)**2 + gamma**2) + offset


def fit_placeholder(x, y, model="linear"):
    # Starter placeholder. Add scipy.optimize.curve_fit later.
    return {"model": model, "status": "not_implemented", "params": {}}

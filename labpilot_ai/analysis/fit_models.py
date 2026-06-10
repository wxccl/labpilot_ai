import numpy as np


def linear(x, a, b):
    return a * np.asarray(x) + b


def gaussian(x, amp, x0, sigma, offset):
    x = np.asarray(x)
    return amp * np.exp(-0.5 * ((x - x0) / sigma) ** 2) + offset


def exponential(x, amp, tau, offset):
    x = np.asarray(x)
    return amp * np.exp(-x / tau) + offset


def logarithmic(x, a, b):
    x = np.asarray(x)
    return a * np.log(x) + b


def lorentzian(x, amp, x0, gamma, offset):
    x = np.asarray(x)
    return amp * gamma**2 / ((x - x0)**2 + gamma**2) + offset


def gaussian2d(coords, amp, x0, y0, sigma_x, sigma_y, offset):
    x, y = coords
    return amp * np.exp(-0.5 * (((x - x0) / sigma_x) ** 2 + ((y - y0) / sigma_y) ** 2)) + offset


def double_gaussian2d(coords, amp1, x01, y01, sx1, sy1, amp2, x02, y02, sx2, sy2, offset):
    return gaussian2d(coords, amp1, x01, y01, sx1, sy1, 0.0) + gaussian2d(coords, amp2, x02, y02, sx2, sy2, 0.0) + offset


MODEL_FUNCS = {
    "linear": linear,
    "gaussian": gaussian,
    "logarithmic": logarithmic,
    "exponential": exponential,
    "lorentzian": lorentzian,
}


def r_squared(y, y_fit):
    y = np.asarray(y, dtype=float)
    y_fit = np.asarray(y_fit, dtype=float)
    ss_res = float(np.sum((y - y_fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot


def initial_guess(x, y, model):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    amp = float(np.max(y) - np.min(y)) if len(y) else 1.0
    offset = float(np.min(y)) if len(y) else 0.0
    center = float(x[int(np.argmax(y))]) if len(x) else 0.0
    width = float((np.max(x) - np.min(x)) / 6) if len(x) > 1 else 1.0
    if width == 0:
        width = 1.0
    if model == "linear":
        return [1.0, float(np.mean(y)) if len(y) else 0.0]
    if model == "gaussian":
        return [amp, center, width, offset]
    if model == "logarithmic":
        return [1.0, offset]
    if model == "exponential":
        return [amp, width, offset]
    if model == "lorentzian":
        return [amp, center, width, offset]
    return None


def fit_xy(x, y, model="linear"):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if len(x) < 2:
        return {"model": model, "status": "failed", "error": "not enough finite points", "params": {}}
    if model == "logarithmic":
        mask = x > 0
        x = x[mask]
        y = y[mask]
    if model not in MODEL_FUNCS:
        return {"model": model, "status": "failed", "error": "unsupported model", "params": {}}
    try:
        if model == "linear":
            coeff = np.polyfit(x, y, 1)
            params = {"a": float(coeff[0]), "b": float(coeff[1])}
            y_fit = linear(x, **params)
        else:
            from scipy.optimize import curve_fit

            func = MODEL_FUNCS[model]
            popt, pcov = curve_fit(func, x, y, p0=initial_guess(x, y, model), maxfev=20000)
            names = {
                "gaussian": ["amp", "x0", "sigma", "offset"],
                "logarithmic": ["a", "b"],
                "exponential": ["amp", "tau", "offset"],
                "lorentzian": ["amp", "x0", "gamma", "offset"],
            }[model]
            params = {name: float(value) for name, value in zip(names, popt)}
            y_fit = func(x, *popt)
            errors = {f"{name}_stderr": float(np.sqrt(abs(pcov[i, i]))) for i, name in enumerate(names)}
            params.update(errors)
        return {"model": model, "status": "ok", "params": params, "r2": r_squared(y, y_fit)}
    except Exception as exc:
        return {"model": model, "status": "failed", "error": repr(exc), "params": {}}


def fit_histogram(values, model="gaussian", bins=30):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    counts, edges = np.histogram(values, bins=bins)
    centers = (edges[:-1] + edges[1:]) / 2
    return fit_xy(centers, counts, model=model)


def initial_guess_2d(x, y, z, model):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    amp = float(np.max(z) - np.min(z)) if len(z) else 1.0
    offset = float(np.min(z)) if len(z) else 0.0
    max_index = int(np.argmax(z)) if len(z) else 0
    x0 = float(x[max_index]) if len(x) else 0.0
    y0 = float(y[max_index]) if len(y) else 0.0
    sx = float((np.max(x) - np.min(x)) / 6) if len(x) > 1 else 1.0
    sy = float((np.max(y) - np.min(y)) / 6) if len(y) > 1 else 1.0
    sx = sx or 1.0
    sy = sy or 1.0
    if model == "gaussian2d":
        return [amp, x0, y0, sx, sy, offset]
    if model == "double_gaussian2d":
        return [amp, x0, y0, sx, sy, amp / 2.0, x0 + sx, y0 + sy, sx, sy, offset]
    return None


def fit_xyz(x, y, z, model="gaussian2d"):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x = x[mask]
    y = y[mask]
    z = z[mask]
    names_by_model = {
        "gaussian2d": ["amp", "x0", "y0", "sigma_x", "sigma_y", "offset"],
        "double_gaussian2d": [
            "amp1",
            "x01",
            "y01",
            "sigma_x1",
            "sigma_y1",
            "amp2",
            "x02",
            "y02",
            "sigma_x2",
            "sigma_y2",
            "offset",
        ],
    }
    if model not in names_by_model:
        return {"model": model, "status": "failed", "error": "unsupported 2D model", "params": {}}
    names = names_by_model[model]
    if len(z) < len(names):
        return {"model": model, "status": "failed", "error": "not enough finite points", "params": {}}
    try:
        from scipy.optimize import curve_fit

        func = gaussian2d if model == "gaussian2d" else double_gaussian2d
        popt, pcov = curve_fit(func, (x, y), z, p0=initial_guess_2d(x, y, z, model), maxfev=40000)
        z_fit = func((x, y), *popt)
        params = {name: float(value) for name, value in zip(names, popt)}
        params.update({f"{name}_stderr": float(np.sqrt(abs(pcov[i, i]))) for i, name in enumerate(names)})
        return {"model": model, "status": "ok", "params": params, "r2": r_squared(z, z_fit)}
    except Exception as exc:
        return {"model": model, "status": "failed", "error": repr(exc), "params": {}}


def fit_placeholder(x, y, model="linear"):
    return fit_xy(x, y, model=model)

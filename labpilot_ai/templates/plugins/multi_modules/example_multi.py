def analyze(dataframe, params=None):
    return {"mean_N_total": float(dataframe["N_total"].mean()) if "N_total" in dataframe else None}

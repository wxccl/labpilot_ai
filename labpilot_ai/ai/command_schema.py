ALLOWED_ACTIONS = {
    "set_global",
    "set_blacs_manual",
    "engage",
    "get_globals",
    "load_h5",
    "load_h5_folder",
    "run_single_lyse",
    "run_multi_lyse",
    "plot",
    "fit",
    "start_optimization",
    "stop_optimization",
    "tell_optimization_result",
    "evaluate_optimization_result",
    "generate_protocol",
    "generate_report",
}


def action_summary(action: dict) -> str:
    typ = action.get("type", "")
    if typ in {"set_global", "set_blacs_manual"}:
        return f"{typ}: {action.get('name')} = {action.get('value')!r}"
    if typ == "start_optimization":
        names = ", ".join((action.get("parameters") or {}).keys())
        return f"{typ}: {action.get('method')} {action.get('mode')} {action.get('objective')} over {names}"
    if typ in {"plot", "fit"}:
        return f"{typ}: {action.get('plot_type', action.get('model', ''))}"
    return typ

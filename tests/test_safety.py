import numpy as np
from labpilot_ai.safety.validator import SafetyValidator


def test_float_array_linspace():
    reg = {"x": {"type":"float", "allow_array":True, "min":0, "max":10, "max_points":5}}
    safe = SafetyValidator(reg).validate_command({"actions":[{"type":"set_global", "name":"x", "value":{"linspace":[0,10,3]}}]})
    assert np.allclose(safe["globals"]["x"], [0,5,10])


def test_high_risk_requires_confirmation():
    reg = {"p": {"type": "float", "min": 0, "max": 1, "risk": "high"}}
    safe = SafetyValidator(reg).validate_command({"actions": [{"type": "set_global", "name": "p", "value": 0.5}]})
    assert safe["confirmations"][0]["name"] == "p"


def test_optimization_parameters_are_whitelisted():
    reg = {"x": {"type": "float", "min": 0, "max": 10, "max_points": 10}}
    safe = SafetyValidator(reg).validate_command(
        {
            "actions": [
                {
                    "type": "start_optimization",
                    "objective": "signal",
                    "parameters": {"x": {"min": 1, "max": 2, "points": 3}},
                }
            ]
        }
    )
    assert safe["optimization"]["parameters"]["x"]["points"] == 3


def test_optimization_auto_loop_options_are_validated():
    reg = {"x": {"type": "float", "min": 0, "max": 10, "max_points": 10}}
    safe = SafetyValidator(reg).validate_command(
        {
            "actions": [
                {
                    "type": "start_optimization",
                    "objective": "signal",
                    "parameters": {"x": {"min": 1, "max": 2, "points": 3}},
                    "auto_loop": True,
                    "run_checked_modules": False,
                    "poll_interval_s": 0.1,
                    "h5_timeout_s": 1.5,
                    "generate_report_on_complete": True,
                }
            ]
        }
    )
    opt = safe["optimization"]
    assert opt["auto_loop"] is True
    assert opt["run_checked_modules"] is False
    assert opt["poll_interval_s"] == 0.1
    assert opt["h5_timeout_s"] == 1.5
    assert opt["generate_report_on_complete"] is True


def test_optimization_feedback_latest_h5_action():
    safe = SafetyValidator({}).validate_command(
        {"actions": [{"type": "tell_optimization_result", "source": "latest_h5", "run_checked_modules": True}]}
    )
    assert safe["optimization_feedback"][0]["source"] == "latest_h5"


def test_optimization_feedback_manual_values_action():
    safe = SafetyValidator({}).validate_command(
        {"actions": [{"type": "tell_optimization_result", "values": {"N_total": 2.0}}]}
    )
    assert safe["optimization_feedback"][0]["values"]["N_total"] == 2.0


def test_validator_reload_updates_blacs_whitelist():
    validator = SafetyValidator({}, {})
    validator.reload(blacs_registry={"ao0": {"type": "float", "min": 0, "max": 5}})
    safe = validator.validate_command({"actions": [{"type": "set_blacs_manual", "name": "ao0", "value": 1.25}]})
    assert safe["blacs_manual"]["ao0"] == 1.25

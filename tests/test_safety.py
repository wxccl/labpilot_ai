import numpy as np
from labpilot_ai.safety.validator import SafetyValidator


def test_float_array_linspace():
    reg = {"x": {"type":"float", "allow_array":True, "min":0, "max":10, "max_points":5}}
    safe = SafetyValidator(reg).validate_command({"actions":[{"type":"set_global", "name":"x", "value":{"linspace":[0,10,3]}}]})
    assert np.allclose(safe["globals"]["x"], [0,5,10])

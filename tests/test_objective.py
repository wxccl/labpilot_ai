import pytest

from labpilot_ai.optimizer.objective import ObjectiveError, SafeObjective


def test_safe_objective_basic_math():
    obj = SafeObjective("N_total / temperature_uK")
    assert obj.evaluate({"N_total": 10, "temperature_uK": 2}) == 5


def test_safe_objective_dotted_columns():
    obj = SafeObjective("results.N_total - globals.offset")
    assert obj.evaluate({"results.N_total": 12, "globals.offset": 2}) == 10


def test_safe_objective_blocks_attributes():
    with pytest.raises(ObjectiveError):
        SafeObjective("__import__('os').system('echo bad')")

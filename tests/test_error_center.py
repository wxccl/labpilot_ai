from labpilot_ai.ai.error_advisor import advise_error
from labpilot_ai.app.error_center import ErrorCenter, ErrorRecord, trim_traceback
from labpilot_ai.storage.database import LabPilotDatabase


def test_error_record_jsonl_and_database_roundtrip(tmp_path):
    db = LabPilotDatabase(tmp_path / "state.sqlite")
    center = ErrorCenter(database=db, jsonl_path=tmp_path / "errors.jsonl")
    record = center.capture_exception(
        "BLACS bridge failed",
        RuntimeError("localhost connection refused"),
        kind="blacs",
        severity="hardware_pause",
        context="connection_table.py",
        modal=False,
    )
    assert record.kind == "blacs"
    assert (tmp_path / "errors.jsonl").exists()
    rows = db.list_error_records()
    assert rows[0]["kind"] == "blacs"
    assert "connection refused" in rows[0]["message"]


def test_error_advisor_categories():
    assert "CUDA" in advise_error("cublas64_12.dll is not found")
    assert "OpenMP" in advise_error("OMP: Error #15 libiomp5md.dll already initialized")
    assert "pypdf" in advise_error("PDF import requires labpilot-ai[docs]")
    assert "runmanager" in advise_error("runmanager remote timeout")
    assert "BLACS" in advise_error("BLACS localhost bridge connection refused")
    assert "objective" in advise_error("objective variable N_total is missing")
    assert "scipy" in advise_error("No module named scipy")


def test_traceback_trim():
    text = "x" * 20000
    trimmed = trim_traceback(text, max_chars=1000)
    assert len(trimmed) == 1000


def test_error_record_serializes_chinese():
    record = ErrorRecord(title="错误", message="中文错误", advice="建议")
    payload = record.to_dict()
    assert payload["title"] == "错误"
    assert payload["message"] == "中文错误"

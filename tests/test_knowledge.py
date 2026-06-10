import builtins

import pytest

from labpilot_ai.ai.llm_client import LLMClient
from labpilot_ai.ai.prompt_builder import build_command_prompt
from labpilot_ai.knowledge.context_builder import build_project_context
from labpilot_ai.knowledge.indexer import (
    KnowledgeIndexer,
    discover_source_files,
    project_db_path,
    read_source_text,
    source_counts,
)
from labpilot_ai.knowledge.search import KnowledgeSearch


def test_knowledge_index_search_and_skip(tmp_path):
    sequence_dir = tmp_path / "sequences"
    sequence_dir.mkdir()
    sequence = sequence_dir / "rabi_sequence.py"
    sequence.write_text("do_Rabi = True\n# Rabi pulse scan uses duration_tof_ms\n", encoding="utf-8")
    connection = tmp_path / "connection_table.py"
    connection.write_text("Device = 'NI_DAQ'\n# bias channel ao0\n", encoding="utf-8")
    single_dir = tmp_path / "single"
    single_dir.mkdir()
    (single_dir / "count_atoms.py").write_text("def analyze(h5_path):\n    return {'N_total': 1}\n", encoding="utf-8")

    settings = {
        "sequence_dir": str(sequence_dir),
        "connection_table": str(connection),
        "single_modules_dir": str(single_dir),
        "knowledge_db_path": "knowledge.sqlite",
    }
    files = discover_source_files(settings, project_dir=tmp_path)
    assert {item["category"] for item in files} >= {"sequence", "connection_table", "single_lyse"}
    counts = source_counts(settings, project_dir=tmp_path)
    assert counts["sequence"] == 1

    indexer = KnowledgeIndexer(project_db_path(settings, project_dir=tmp_path))
    stats = indexer.index_project(settings, project_dir=tmp_path, rebuild=True)
    assert stats["indexed"] == 3
    stats_again = indexer.index_project(settings, project_dir=tmp_path, rebuild=False)
    assert stats_again["skipped"] == 3

    results = KnowledgeSearch(indexer.db_path).search("Rabi duration_tof_ms", limit=3)
    assert results
    assert results[0]["category"] == "sequence"
    assert "Rabi" in results[0]["snippet"]


def test_knowledge_context_is_limited(tmp_path):
    docs = tmp_path / "manual"
    docs.mkdir()
    (docs / "ramsey.md").write_text(("Ramsey contrast scan\n" * 200), encoding="utf-8")
    settings = {"manual_dir": str(docs), "knowledge_db_path": "knowledge.sqlite"}
    indexer = KnowledgeIndexer(project_db_path(settings, project_dir=tmp_path))
    indexer.index_project(settings, project_dir=tmp_path, rebuild=True, chunk_chars=400)

    context, results = build_project_context("Ramsey contrast", settings, project_dir=tmp_path, max_items=4, max_chars=900, snippet_chars=300)
    assert results
    assert len(context) <= 1200
    assert "Project knowledge context" in context
    assert "Ramsey" in context


def test_pdf_dependency_error(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("missing pypdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="labpilot-ai\\[docs\\]"):
        read_source_text(pdf)


def test_llm_prompt_and_mock_parse_receive_project_context():
    prompt = build_command_prompt({"do_Rabi": {"type": "bool"}}, project_context="sequence says do_Rabi enables Rabi")
    assert "sequence says do_Rabi" in prompt
    client = LLMClient(mock=True)
    parsed = client.parse_command("enable Rabi", {"do_Rabi": {"type": "bool"}}, project_context="Rabi context")
    assert parsed["project_context_used"] is True

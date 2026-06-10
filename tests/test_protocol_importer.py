import builtins

import pytest

from labpilot_ai.ai.protocol_importer import (
    build_protocol_prompt,
    describe_image_attachment,
    import_protocol_file,
    read_pdf_text,
    read_text_document,
)


def test_text_and_markdown_import(tmp_path):
    text = tmp_path / "idea.md"
    text.write_text("# Ramsey\nScan detuning.", encoding="utf-8")
    assert "Scan detuning" in read_text_document(text)
    assert "Ramsey" in import_protocol_file(text)


def test_pdf_import_dependency_error(monkeypatch, tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("missing pypdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="labpilot-ai\\[docs\\]"):
        read_pdf_text(pdf)


def test_image_attachment_and_prompt(tmp_path):
    image = tmp_path / "figure.png"
    image.write_bytes(b"fake")
    attachment = describe_image_attachment(image, "Rabi oscillation figure")
    prompt = build_protocol_prompt("Optimize contrast.", [attachment])
    assert "Optimize contrast" in prompt
    assert "figure.png" in prompt
    assert "Rabi oscillation" in prompt


def test_unsupported_protocol_file(tmp_path):
    file = tmp_path / "data.csv"
    file.write_text("x,y\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        import_protocol_file(file)

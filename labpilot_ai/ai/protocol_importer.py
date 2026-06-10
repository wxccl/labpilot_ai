from pathlib import Path


TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}


def read_text_document(path):
    path = Path(path)
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8-sig")


def read_pdf_text(path):
    path = Path(path)
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise RuntimeError("PDF import requires labpilot-ai[docs] or `pip install pypdf`.") from exc

    reader = PdfReader(str(path))
    parts = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            parts.append(f"[PDF page {index}]\n{text.strip()}")
    return "\n\n".join(parts)


def import_protocol_file(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return read_text_document(path)
    if suffix == ".pdf":
        return read_pdf_text(path)
    raise ValueError(f"Unsupported protocol import type: {suffix or path.name}")


def describe_image_attachment(path, note=""):
    path = Path(path)
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Unsupported image attachment type: {path.suffix or path.name}")
    text = f"Image attachment: {path.name}\nPath: {path}"
    if note:
        text += f"\nHuman note: {note}"
    return text


def build_protocol_prompt(text, attachments=None):
    sections = [(text or "").strip()]
    attachments = [str(item).strip() for item in (attachments or []) if str(item).strip()]
    if attachments:
        sections.append("Attachments and operator notes:\n" + "\n\n".join(attachments))
    return "\n\n".join([section for section in sections if section])

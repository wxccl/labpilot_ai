from datetime import date
from pathlib import Path


FORMAT_EXTENSIONS = {
    "markdown": "md",
    "latex": "tex",
    "dokuwiki": "txt",
}


def _limit_paragraphs(text, length_mode="one_a4", paragraph_count=8):
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if length_mode == "full":
        return text
    if length_mode == "paragraphs":
        return "\n\n".join(paragraphs[: max(1, int(paragraph_count or 1))])
    return "\n\n".join(paragraphs[:10])


def _plain_sections(data):
    day = data.get("date") or date.today().isoformat()
    lines = [f"LabPilot experiment log - {day}"]
    if data.get("notes"):
        lines.extend(["Operator notes", str(data["notes"])])
    commands = data.get("command_records") or []
    lines.extend(["Natural-language commands", f"{len(commands)} command record(s)."])
    for record in commands[-20:]:
        payload = record.get("payload", record)
        lines.append(f"- {record.get('created_at', '')}: {payload.get('user_text', payload.get('event', ''))}")
    changes = data.get("code_change_records") or []
    lines.extend(["Code changes", f"{len(changes)} code change record(s)."])
    for record in changes[-20:]:
        payload = record.get("payload", record)
        lines.append(f"- {record.get('created_at', payload.get('created_at', ''))}: {payload.get('summary', payload.get('kind', 'change'))}")
    analysis = data.get("analysis_records") or []
    if analysis:
        lines.extend(["Analysis and optimizer", f"{len(analysis)} analysis record(s)."])
        for record in analysis[-20:]:
            lines.append(f"- {record.get('kind', '')}/{record.get('name', '')}: {record.get('result', '')}")
    errors = data.get("error_records") or []
    if errors:
        lines.extend(["Errors and warnings", f"{len(errors)} recent error/warning record(s)."])
        for record in errors[-20:]:
            lines.append(f"- {record.get('severity', '')}/{record.get('kind', '')}: {record.get('title', '')} - {record.get('message', '')}")
    if data.get("sequence_path"):
        lines.extend(["Active sequence", str(data.get("sequence_path"))])
    if data.get("connection_table_path"):
        lines.extend(["Active connection table", str(data.get("connection_table_path"))])
    if data.get("h5_output_dir"):
        lines.extend(["H5 output folder", str(data.get("h5_output_dir"))])
    if data.get("knowledge_context"):
        lines.extend(["Knowledge context used", str(data.get("knowledge_context"))[:3000]])
    return "\n\n".join(lines)


def _markdown(data):
    text = _plain_sections(data)
    lines = text.splitlines()
    if lines:
        lines[0] = "# " + lines[0]
    headings = {
        "Operator notes",
        "Natural-language commands",
        "Code changes",
        "Analysis and optimizer",
        "Errors and warnings",
        "Active sequence",
        "Active connection table",
        "H5 output folder",
        "Knowledge context used",
    }
    return "\n".join(("## " + line) if line in headings else line for line in lines)


def _latex_escape(text):
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = str(text)
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out


def _latex(data):
    plain = _plain_sections(data)
    lines = [_latex_escape(line) for line in plain.splitlines()]
    return "\\section*{" + lines[0] + "}\n" + "\n\n".join(lines[1:])


def _dokuwiki(data):
    text = _plain_sections(data)
    lines = text.splitlines()
    if lines:
        lines[0] = "====== " + lines[0] + " ======"
    headings = {
        "Operator notes",
        "Natural-language commands",
        "Code changes",
        "Analysis and optimizer",
        "Errors and warnings",
        "Active sequence",
        "Active connection table",
        "H5 output folder",
        "Knowledge context used",
    }
    return "\n".join(("===== " + line + " =====") if line in headings else line for line in lines)


def generate_experiment_log(
    data,
    *,
    output_format="markdown",
    length_mode="one_a4",
    paragraph_count=8,
):
    output_format = (output_format or "markdown").lower()
    if output_format == "latex":
        text = _latex(data)
    elif output_format == "dokuwiki":
        text = _dokuwiki(data)
    else:
        text = _markdown(data)
        output_format = "markdown"
    return _limit_paragraphs(text, length_mode=length_mode, paragraph_count=paragraph_count)


def save_experiment_log(base_dir, date_text, text, output_format="markdown"):
    output_format = (output_format or "markdown").lower()
    extension = FORMAT_EXTENSIONS.get(output_format, "md")
    folder = Path(base_dir or "labpilot_outputs/experiment_logs") / str(date_text)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"experiment_log.{extension}"
    path.write_text(text, encoding="utf-8")
    return path

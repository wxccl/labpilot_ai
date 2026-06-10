from pathlib import Path


def generate_markdown_report(
    title: str,
    dataframe=None,
    fit_results=None,
    figures=None,
    notes: str = "",
    analysis_records=None,
    error_records=None,
    optimizer_history=None,
    knowledge_context: str = "",
) -> str:
    lines = [f"# {title or 'LabPilot analysis report'}", ""]
    if dataframe is not None:
        lines.append(f"- Rows: {len(dataframe)}")
        lines.append(f"- Columns: {', '.join(map(str, dataframe.columns[:20]))}")
        lines.append("")
    if fit_results:
        lines.append("## Fits")
        for result in fit_results:
            lines.append(f"- {result.get('model')}: {result.get('status')} params={result.get('params', {})}")
        lines.append("")
    if figures:
        lines.append("## Figures")
        for fig in figures:
            lines.append(f"- {fig}")
        lines.append("")
    if analysis_records:
        lines.append("## Analysis records")
        for row in analysis_records[-20:]:
            result = row.get("result", {})
            status = result.get("status", "ok") if isinstance(result, dict) else "ok"
            lines.append(f"- {row.get('kind')}/{row.get('name')}: {status}")
        lines.append("")
    if optimizer_history:
        lines.append("## Optimizer")
        best = optimizer_history.get("best") if isinstance(optimizer_history, dict) else None
        lines.append(f"- Best: {best}")
        lines.append("")
    if error_records:
        lines.append("## Recent errors and warnings")
        for record in error_records[-10:]:
            lines.append(f"- {record.get('severity', 'error')}/{record.get('kind', 'ui')}: {record.get('title', '')} - {record.get('message', '')}")
        lines.append("")
    if knowledge_context:
        lines.append("## AI knowledge context")
        lines.append(knowledge_context[:3000])
        lines.append("")
    if notes:
        lines.extend(["## Notes", notes, ""])
    return "\n".join(lines)


def save_markdown_report(path, *args, **kwargs):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = generate_markdown_report(*args, **kwargs)
    path.write_text(text, encoding="utf-8")
    return path

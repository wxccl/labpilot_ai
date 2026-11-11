import ast
import builtins
import difflib
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DANGEROUS_PATTERNS = [
    "os.remove",
    "os.unlink",
    "shutil.rmtree",
    "subprocess.",
    "eval(",
    "exec(",
    "__import__(",
]

COMMON_RECEIVERS = {
    "np",
    "numpy",
    "math",
    "time",
    "labscript",
    "builtins",
}


@dataclass
class PatchValidationResult:
    ok: bool
    errors: list
    warnings: list
    previews: list
    summary: str = ""

    def to_dict(self):
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "previews": [
                {
                    "path": str(item["path"]),
                    "old_text": item.get("old_text", ""),
                    "new_text": item.get("new_text", ""),
                    "unified_diff": item.get("unified_diff", ""),
                }
                for item in self.previews
            ],
            "summary": self.summary,
        }


@dataclass
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list


def _resolve(path):
    return Path(path).expanduser().resolve()


def _allowed_paths(sequence_path, connection_table_path):
    allowed = {}
    for path in [sequence_path, connection_table_path]:
        if path:
            resolved = _resolve(path)
            allowed[str(resolved).lower()] = resolved
            allowed[resolved.name.lower()] = resolved
            allowed[str(path).replace("\\", "/").lower()] = resolved
    return allowed


def _plan_files(plan):
    if not isinstance(plan, dict):
        raise ValueError("Patch plan must be a dict.")
    files = plan.get("files", [])
    if not isinstance(files, list):
        raise ValueError("Patch plan field `files` must be a list.")
    return files


def _target_path(file_item, allowed):
    raw = str(file_item.get("path", "")).strip()
    if not raw:
        raise ValueError("Patch file entry is missing path.")
    normalized = raw.replace("\\", "/").lower()
    candidates = [
        str(_resolve(raw)).lower() if not raw.startswith(("/dev/", "dev/")) else raw.lower(),
        normalized,
        Path(raw).name.lower(),
    ]
    for candidate in candidates:
        if candidate in allowed:
            return allowed[candidate]
    raise ValueError(f"Patch path is not one of the selected editable files: {raw}")


def _has_file_creation_or_deletion(diff_text):
    lowered = diff_text.lower()
    return "/dev/null" in lowered or "new file mode" in lowered or "deleted file mode" in lowered


def _normalize_ai_escaped_docstring_delimiters(diff_text):
    """Repair common JSON-escaped docstring delimiters leaked into AI diffs."""
    repaired = []
    warnings = []
    for line in str(diff_text or "").splitlines(keepends=True):
        if line[:1] not in {" ", "+", "-"}:
            repaired.append(line)
            continue
        prefix = line[:1]
        body = line[1:]
        stripped = body.lstrip()
        indent = body[: len(body) - len(stripped)]
        if stripped.startswith('\\"""'):
            repaired.append(prefix + indent + stripped.replace('\\"""', '"""', 1))
            warnings.append("Repaired JSON-escaped Python docstring delimiter in AI patch.")
        else:
            repaired.append(line)
    return "".join(repaired), warnings


def _hunk_header(line):
    match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2) or "1"),
        int(match.group(3)),
        int(match.group(4) or "1"),
    )


def _parse_hunks(diff_lines):
    hunks = []
    index = 0
    while index < len(diff_lines):
        header = _hunk_header(diff_lines[index])
        if header is None:
            index += 1
            continue
        index += 1
        lines = []
        while index < len(diff_lines) and not diff_lines[index].startswith("@@ "):
            lines.append(diff_lines[index])
            index += 1
        hunks.append(_Hunk(*header, lines=lines))
    return hunks


def _line_equal(expected, actual):
    return expected == actual or expected.rstrip("\r\n") == actual.rstrip("\r\n")


def _apply_unified_diff_strict(original_text, diff_text):
    original = original_text.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)
    output = []
    old_index = 0
    index = 0
    found_hunk = False
    while index < len(diff_lines):
        line = diff_lines[index]
        header = _hunk_header(line)
        if header is None:
            index += 1
            continue
        found_hunk = True
        old_start = header[0]
        target_old_index = max(0, old_start - 1)
        if target_old_index < old_index:
            raise ValueError("Overlapping or out-of-order patch hunks.")
        output.extend(original[old_index:target_old_index])
        old_index = target_old_index
        index += 1
        while index < len(diff_lines) and not diff_lines[index].startswith("@@ "):
            hunk_line = diff_lines[index]
            if hunk_line.startswith("\\"):
                index += 1
                continue
            if not hunk_line:
                index += 1
                continue
            prefix = hunk_line[:1]
            body = hunk_line[1:]
            if prefix == " ":
                if old_index >= len(original) or not _line_equal(original[old_index], body):
                    raise ValueError(f"Patch context mismatch near original line {old_index + 1}.")
                output.append(original[old_index])
                old_index += 1
            elif prefix == "-":
                if old_index >= len(original) or not _line_equal(original[old_index], body):
                    raise ValueError(f"Patch removal mismatch near original line {old_index + 1}.")
                old_index += 1
            elif prefix == "+":
                output.append(body)
            else:
                raise ValueError(f"Unsupported unified diff line: {hunk_line!r}")
            index += 1
    if not found_hunk:
        raise ValueError("No unified diff hunk was found.")
    output.extend(original[old_index:])
    return "".join(output)


def _body_lines(hunk_lines, prefixes):
    bodies = []
    for line in hunk_lines:
        if line.startswith("\\") or not line:
            continue
        if line[:1] in prefixes:
            bodies.append(line[1:])
    return bodies


def _sequence_equal(lines, start, sequence):
    if start < 0 or start + len(sequence) > len(lines):
        return False
    return all(_line_equal(lines[start + offset], expected) for offset, expected in enumerate(sequence))


def _find_sequence(lines, sequence, start=0):
    if not sequence:
        return []
    return [
        index
        for index in range(max(0, start), len(lines) - len(sequence) + 1)
        if _sequence_equal(lines, index, sequence)
    ]


def _near_header(indices, old_start, window=80):
    header_index = max(0, old_start - 1)
    near = [index for index in indices if abs(index - header_index) <= window]
    return near or indices


def _anchor_candidates(lines, context_lines, old_start):
    if not context_lines:
        return []
    max_anchor = min(6, len(context_lines))
    for size in range(max_anchor, 0, -1):
        anchor = context_lines[-size:]
        matches = _near_header(_find_sequence(lines, anchor), old_start)
        if matches:
            return [(match + size, anchor) for match in matches]
    return []


def _suffix_candidates(lines, suffix_context, old_start, start=0):
    if not suffix_context:
        return []
    max_anchor = min(6, len(suffix_context))
    for size in range(max_anchor, 0, -1):
        anchor = suffix_context[:size]
        matches = _near_header(_find_sequence(lines, anchor, start=start), old_start)
        if matches:
            return [(match, anchor) for match in matches]
    return []


def _fuzzy_insert_index(lines, hunk):
    prefixes = {line[:1] for line in hunk.lines if line and not line.startswith("\\")}
    if "-" in prefixes:
        raise ValueError("Fuzzy patch repair is only allowed for pure insertion hunks.")
    inserted = _body_lines(hunk.lines, {"+"})
    if not inserted:
        raise ValueError("Fuzzy patch repair found no inserted lines.")

    first_insert = next(index for index, line in enumerate(hunk.lines) if line.startswith("+"))
    last_insert = len(hunk.lines) - 1 - next(index for index, line in enumerate(reversed(hunk.lines)) if line.startswith("+"))
    prefix_context = _body_lines(hunk.lines[:first_insert], {" "})
    suffix_context = _body_lines(hunk.lines[last_insert + 1 :], {" "})

    candidate_indices = set()
    prefix_candidates = _anchor_candidates(lines, prefix_context, hunk.old_start)
    if prefix_candidates:
        for prefix_end, _anchor in prefix_candidates:
            suffix_candidates = _suffix_candidates(lines, suffix_context, hunk.old_start, start=prefix_end)
            if suffix_candidates:
                for suffix_start, _suffix_anchor in suffix_candidates:
                    candidate_indices.add(suffix_start)
            elif not suffix_context:
                candidate_indices.add(prefix_end)
    elif suffix_context:
        for suffix_start, _suffix_anchor in _suffix_candidates(lines, suffix_context, hunk.old_start):
            candidate_indices.add(suffix_start)

    if not candidate_indices:
        raise ValueError(f"Patch context mismatch near original line {hunk.old_start}.")
    if len(candidate_indices) > 1:
        options = ", ".join(str(index + 1) for index in sorted(candidate_indices)[:8])
        raise ValueError(
            f"Patch insertion is ambiguous near original line {hunk.old_start}; "
            f"candidate lines: {options}."
        )
    return next(iter(candidate_indices))


def _apply_unified_diff_fuzzy_insertions(original_text, diff_text):
    lines = original_text.splitlines(keepends=True)
    hunks = _parse_hunks(diff_text.splitlines(keepends=True))
    if not hunks:
        raise ValueError("No unified diff hunk was found.")
    warnings = []
    for hunk in hunks:
        inserted = _body_lines(hunk.lines, {"+"})
        insertion_index = _fuzzy_insert_index(lines, hunk)
        lines[insertion_index:insertion_index] = inserted
        warnings.append(
            f"Patch hunk near original line {hunk.old_start} was repaired with unique-context insertion."
        )
    return "".join(lines), warnings


def apply_unified_diff_with_warnings(original_text, diff_text):
    try:
        return _apply_unified_diff_strict(original_text, diff_text), []
    except ValueError as strict_error:
        try:
            new_text, warnings = _apply_unified_diff_fuzzy_insertions(original_text, diff_text)
        except ValueError:
            raise strict_error
        return new_text, warnings


def apply_unified_diff(original_text, diff_text):
    new_text, _warnings = apply_unified_diff_with_warnings(original_text, diff_text)
    return new_text


def make_unified_diff(old_text, new_text, path):
    return "".join(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        )
    )


def _syntax_errors(path, text):
    try:
        ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"{path.name}: Python syntax error at line {exc.lineno}: {exc.msg}"]
    return []


def _symbols_from_connection(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    symbols = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
                elif isinstance(target, (ast.Tuple, ast.List)):
                    for item in target.elts:
                        if isinstance(item, ast.Name):
                            symbols.add(item.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                symbols.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                symbols.add(alias.asname or alias.name)
    return symbols


def _attribute_receivers(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    receivers = set()
    assigned = set()
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned.add(target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            value = node.func.value
            if isinstance(value, ast.Name):
                name = value.id
                if name not in assigned and name not in imported and name not in COMMON_RECEIVERS:
                    receivers.add(name)
    return receivers


def consistency_warnings(sequence_text, connection_table_text):
    warnings = []
    connection_symbols = _symbols_from_connection(connection_table_text)
    receivers = _attribute_receivers(sequence_text)
    builtin_names = set(dir(builtins))
    missing = sorted(
        name for name in receivers
        if name not in connection_symbols and name not in builtin_names and not name.startswith("_")
    )
    if missing:
        warnings.append(
            "Sequence references possible devices not declared in connection table: "
            + ", ".join(missing[:20])
        )
    for pattern in DANGEROUS_PATTERNS:
        if pattern in sequence_text or pattern in connection_table_text:
            warnings.append(f"Potentially dangerous code pattern found: {pattern}")
    return warnings


def validate_patch_plan(plan, sequence_path, connection_table_path):
    errors = []
    warnings = []
    previews = []
    allowed = _allowed_paths(sequence_path, connection_table_path)
    try:
        files = _plan_files(plan)
    except Exception as exc:
        return PatchValidationResult(False, [str(exc)], [], [], summary="")
    if not files:
        warnings.append("Patch plan has no file changes.")
    for file_item in files:
        try:
            target = _target_path(file_item, allowed)
            diff_text = str(file_item.get("unified_diff", ""))
            diff_text, normalize_warnings = _normalize_ai_escaped_docstring_delimiters(diff_text)
            warnings.extend(normalize_warnings)
            if not diff_text.strip():
                errors.append(f"{target.name}: missing unified_diff.")
                continue
            if "Binary files" in diff_text or _has_file_creation_or_deletion(diff_text):
                errors.append(f"{target.name}: creating, deleting, or binary patching files is not allowed.")
                continue
            old_text = target.read_text(encoding="utf-8")
            new_text, repair_warnings = apply_unified_diff_with_warnings(old_text, diff_text)
            warnings.extend(repair_warnings)
            errors.extend(_syntax_errors(target, new_text))
            previews.append(
                {
                    "path": target,
                    "old_text": old_text,
                    "new_text": new_text,
                    "unified_diff": make_unified_diff(old_text, new_text, target),
                }
            )
        except Exception as exc:
            errors.append(str(exc))
    preview_by_name = {item["path"].name.lower(): item for item in previews}
    seq_path = _resolve(sequence_path) if sequence_path else None
    conn_path = _resolve(connection_table_path) if connection_table_path else None
    if seq_path and conn_path and seq_path.exists() and conn_path.exists():
        sequence_text = preview_by_name.get(seq_path.name.lower(), {}).get("new_text", seq_path.read_text(encoding="utf-8"))
        connection_text = preview_by_name.get(conn_path.name.lower(), {}).get("new_text", conn_path.read_text(encoding="utf-8"))
        warnings.extend(consistency_warnings(sequence_text, connection_text))
    return PatchValidationResult(
        ok=not errors,
        errors=errors,
        warnings=warnings + list(plan.get("warnings", []) or []),
        previews=previews,
        summary=str(plan.get("summary", "")),
    )


def apply_patch_plan(plan, sequence_path, connection_table_path, *, require_backup=True):
    result = validate_patch_plan(plan, sequence_path, connection_table_path)
    if not result.ok:
        raise RuntimeError("Patch validation failed: " + "; ".join(result.errors))
    applied = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for preview in result.previews:
        path = Path(preview["path"])
        backup = None
        if require_backup:
            backup = path.with_name(f"{path.name}.{timestamp}.bak")
            shutil.copy2(path, backup)
        path.write_text(preview["new_text"], encoding="utf-8")
        applied.append(
            {
                "path": str(path),
                "backup_path": str(backup) if backup else "",
                "unified_diff": preview["unified_diff"],
            }
        )
    return {
        "status": "applied",
        "summary": result.summary,
        "warnings": result.warnings,
        "applied": applied,
        "color_tags": plan.get("color_tags", []) or [],
        "risk_level": plan.get("risk_level", "medium"),
    }

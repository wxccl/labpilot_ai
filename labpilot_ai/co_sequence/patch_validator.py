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


def _line_equal(expected, actual):
    return expected == actual or expected.rstrip("\r\n") == actual.rstrip("\r\n")


def apply_unified_diff(original_text, diff_text):
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
            if not diff_text.strip():
                errors.append(f"{target.name}: missing unified_diff.")
                continue
            if "Binary files" in diff_text or _has_file_creation_or_deletion(diff_text):
                errors.append(f"{target.name}: creating, deleting, or binary patching files is not allowed.")
                continue
            old_text = target.read_text(encoding="utf-8")
            new_text = apply_unified_diff(old_text, diff_text)
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

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _safe_name(path: Path) -> str:
    name = path.stem
    name = re.sub(r"[^0-9a-zA-Z_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name:
        name = "lyse_module"
    if name[0].isdigit():
        name = "m_" + name
    return name


def _detect_mode(path: Path) -> str:
    """
    labpilot_module: 文件里有 def run(...)
    lyse_script: 原版 lyse 风格脚本，顶层执行，常见 from lyse import Run, path
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return "lyse_script"

    if re.search(r"^\s*def\s+run\s*\(", text, flags=re.MULTILINE):
        return "labpilot_module"

    lyse_markers = [
        r"from\s+lyse\s+import",
        r"import\s+lyse",
        r"\bRun\s*\(",
        r"\bsave_result\s*\(",
        r"\blyse\.data\s*\(",
        r"\bpath\b",
    ]
    if any(re.search(pattern, text) for pattern in lyse_markers):
        return "lyse_script"

    return "lyse_script"


def _scan_py_files(folder: str | Path | None) -> list[Path]:
    if not folder:
        return []

    root = Path(folder).expanduser()
    if not root.exists():
        return []

    files = []
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.name.startswith("_"):
            continue
        files.append(path.resolve())

    return sorted(files, key=lambda p: str(p).lower())


def _path_text(path: Path, project_root: Path | None = None) -> str:
    path = path.resolve()
    if project_root is not None:
        try:
            return path.relative_to(project_root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _make_entry(
    path: Path,
    *,
    group: str,
    index: int,
    existing: dict[str, Any] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    existing = dict(existing or {})

    description = (
        "Auto registered single-shot lyse analysis script."
        if group == "single_modules"
        else "Auto registered multi-shot lyse analysis script."
    )

    entry = {
        "path": _path_text(path, project_root),
        "mode": existing.get("mode") or _detect_mode(path),
        "enabled_by_default": existing.get("enabled_by_default", True),
        "order": int(existing.get("order", (index + 1) * 10)),
        "description": existing.get("description", description),
        "params": existing.get("params", {}),
    }

    # 保留用户已经手动加的字段，例如 outputs、meta_h5_path 等
    for key, value in existing.items():
        if key not in entry:
            entry[key] = value

    return entry


def _resolve_registry_path(path_text: str, project_root: Path | None = None) -> Path:
    path = Path(str(path_text or ""))
    if path.is_absolute():
        return path
    if project_root is not None:
        return project_root / path
    return Path.cwd() / path


def merge_autoscanned_lyse_modules(
    registry: dict[str, Any] | None,
    *,
    single_dir: str | Path | None = None,
    multi_dir: str | Path | None = None,
    project_root: str | Path | None = None,
    prune_missing: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    扫描 single_dir/multi_dir，把文件夹中的 .py 自动合并到 lyse_registry。

    不会删除真实 .py 文件；
    prune_missing=True 时只删除 registry 中路径已经不存在的条目。
    """
    project_root_path = Path(project_root).resolve() if project_root else Path.cwd().resolve()

    new_registry: dict[str, Any] = {
        "single_modules": dict((registry or {}).get("single_modules", {}) or {}),
        "multi_modules": dict((registry or {}).get("multi_modules", {}) or {}),
    }

    report = {
        "single_scanned": 0,
        "multi_scanned": 0,
        "added": [],
        "updated": [],
        "pruned": [],
    }

    jobs = [
        ("single_modules", single_dir, "single_scanned"),
        ("multi_modules", multi_dir, "multi_scanned"),
    ]

    for group, folder, count_key in jobs:
        files = _scan_py_files(folder)
        report[count_key] = len(files)

        modules = dict(new_registry.get(group, {}) or {})
        existing_by_resolved_path = {}

        for name, cfg in modules.items():
            resolved = _resolve_registry_path(cfg.get("path", ""), project_root_path).resolve()
            existing_by_resolved_path[str(resolved).lower()] = name

        for index, path in enumerate(files):
            key = _safe_name(path)
            resolved_key = str(path.resolve()).lower()

            if resolved_key in existing_by_resolved_path:
                key = existing_by_resolved_path[resolved_key]

            if key in modules:
                old = modules[key]
                modules[key] = _make_entry(
                    path,
                    group=group,
                    index=index,
                    existing=old,
                    project_root=project_root_path,
                )
                report["updated"].append(f"{group}.{key}")
            else:
                candidate = key
                suffix = 2
                while candidate in modules:
                    candidate = f"{key}_{suffix}"
                    suffix += 1
                key = candidate

                modules[key] = _make_entry(
                    path,
                    group=group,
                    index=index,
                    existing={},
                    project_root=project_root_path,
                )
                report["added"].append(f"{group}.{key}")

        if prune_missing:
            kept = {}
            for name, cfg in modules.items():
                resolved = _resolve_registry_path(cfg.get("path", ""), project_root_path)
                if resolved.exists():
                    kept[name] = cfg
                else:
                    report["pruned"].append(f"{group}.{name}")
            modules = kept

        modules = dict(
            sorted(
                modules.items(),
                key=lambda item: (int(item[1].get("order", 1000)), item[0]),
            )
        )
        new_registry[group] = modules

    return new_registry, report
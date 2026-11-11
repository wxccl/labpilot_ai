"""Expose small excerpts from an operator-enabled experiment source directory."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import stat

_SUFFIXES = {".py", ".md", ".txt"}
_PRIVATE_NAME = re.compile(
    r"(^|[._-])(secret|secrets|credential|credentials|token|tokens|password|passwd|api[-_]?key|"
    r"private[-_]?key|authorized[-_]?keys|id[-_]rsa|id[-_]ed25519)([._-]|$)", re.IGNORECASE
)
_PRIVATE_TEXT = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"\b(?:sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16})\b|"
    r"""\b(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)\b\s*[:=]\s*['"][^'"\r\n]{8,}['"]""",
    re.IGNORECASE,
)
_MAX_SCAN_ENTRIES = 4096
_MAX_FILE_BYTES = 256 * 1024
_MAX_EXCERPT = 8000


class SourceError(ValueError):
    """A source refusal that can be displayed without exposing a local path."""


def _allowed_name(name):
    return (bool(name) and not name.startswith(".") and name not in {"__pycache__", "node_modules"}
            and not _PRIVATE_NAME.search(name) and not any(char in name for char in "\\:\0"))


def _linked(file_stat):
    return stat.S_ISLNK(file_stat.st_mode) or bool(
        getattr(file_stat, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


class SourceIndex:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir() or not self.root.name or not all(
            _allowed_name(part) for part in self.root.parts[1:]
        ):
            raise ValueError("Select a dedicated experiment source directory")

    def list(self, limit: int) -> dict:
        paths = []
        pending = [self.root]
        scanned = 0
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as entries:
                for entry in entries:
                    scanned += 1
                    if len(paths) >= limit or scanned > _MAX_SCAN_ENTRIES:
                        return {"paths": sorted(paths), "truncated": True}
                    if not _allowed_name(entry.name):
                        continue
                    entry_stat = entry.stat(follow_symlinks=False)
                    if _linked(entry_stat):
                        continue
                    path = Path(entry.path)
                    if stat.S_ISDIR(entry_stat.st_mode):
                        pending.append(path)
                    elif stat.S_ISREG(entry_stat.st_mode) and path.suffix.lower() in _SUFFIXES:
                        paths.append(path.relative_to(self.root).as_posix())
        return {"paths": sorted(paths), "truncated": False}

    def read(self, reference: str, start_line: int, max_lines: int) -> dict:
        parts = reference.split("/")
        relative = PurePosixPath(reference)
        if (not all(_allowed_name(part) for part in parts) or relative.is_absolute()
                or relative.suffix.lower() not in _SUFFIXES):
            raise SourceError("Source reference is outside the allowed file set")
        path = self.root
        for part in parts:
            path /= part
            if _linked(path.lstat()):
                raise SourceError("Source links are outside the allowed file set")
        path = path.resolve(strict=True)
        if not path.is_relative_to(self.root) or not path.is_file():
            raise SourceError("Source reference is outside the configured root")
        initial = path.lstat()
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if (_linked(initial) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink > 1
                    or (initial.st_dev, initial.st_ino) != (opened.st_dev, opened.st_ino)
                    or not path.resolve(strict=True).is_relative_to(self.root)):
                raise SourceError("Source changed during open or is outside the allowed file set")
            raw = stream.read(_MAX_FILE_BYTES + 1)
        if len(raw) > _MAX_FILE_BYTES:
            raise SourceError("Source file exceeds the size limit")
        try:
            source = raw.decode("utf-8-sig")
        except UnicodeError:
            raise SourceError("Source file must use UTF-8") from None
        if "\0" in source or _PRIVATE_TEXT.search(source):
            raise SourceError("Source file is not available for model access")
        lines = source.splitlines(keepends=True)
        first_index = start_line - 1
        excerpt = "".join(lines[first_index:first_index + max_lines])
        return {
            "path": relative.as_posix(), "sha256": hashlib.sha256(raw).hexdigest(),
            "start_line": start_line, "text": excerpt[:_MAX_EXCERPT],
            "truncated": first_index + max_lines < len(lines) or len(excerpt) > _MAX_EXCERPT,
        }

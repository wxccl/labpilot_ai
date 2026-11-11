"""Create a detached coding workspace and collect its patch for operator review."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import uuid

from .catalog import decode_json, encode_json

_MAX_PATCH_BYTES = 2 * 1024 * 1024


class DraftError(RuntimeError):
    """A draft cannot be prepared or collected safely."""


def _git(directory, *args):
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"})
    try:
        completed = subprocess.run(
            ["git", "-c", f"core.hooksPath={os.devnull}", "-c", "core.longpaths=true", "-c", "protocol.allow=never",
             "-c", "submodule.recurse=false", "--literal-pathspecs", *args],
            cwd=directory, env=environment, capture_output=True, check=False,
            timeout=60, shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise DraftError("Local Git command failed") from None
    if completed.returncode:
        raise DraftError(f"Local Git {args[0]} failed")
    return completed.stdout


def _scope_paths(scope):
    if not isinstance(scope, (list, tuple)) or not 1 <= len(scope) <= 32:
        raise DraftError("Provide 1 to 32 repository-relative review paths")
    paths = []
    for path in scope:
        if (not isinstance(path, str) or not path or len(path) > 256 or "\\" in path or ":" in path
                or any(part in {"", ".", ".."} or part.lower() == ".git" for part in path.split("/"))
                or any(ord(char) < 32 for char in path)):
            raise DraftError("Use forward-slash repository-relative review paths")
        paths.append(PurePosixPath(path))
    return paths


def draft_code(*, repo, review_root, scope, prompt, editor=None):
    """Prepare a draft. An optional editor must already enforce its own file sandbox."""
    scoped = _scope_paths(scope)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 24_000:
        raise DraftError("Provide a nonempty coding task within the prompt limit")
    repository = Path(repo).resolve(strict=True)
    git_root = Path(_git(repository, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    if repository != git_root:
        raise DraftError("Select the repository root")
    destination = Path(review_root).resolve()
    if destination.is_relative_to(repository):
        raise DraftError("Place review worktrees outside the primary checkout")
    destination.mkdir(parents=True, exist_ok=True)
    base = _git(repository, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    bundle = destination / f"draft-{uuid.uuid4().hex[:16]}"
    bundle.mkdir()
    worktree = bundle / "worktree"
    _git(repository, "worktree", "add", "--detach", str(worktree), base)
    instructions = (
        "Draft a code change in the detached checkout. Keep all changed files within these relative paths:\n"
        + "".join(f"- {path}\n" for path in scoped)
        + "\nUse offline tests and produce a change for operator review. "
        "Avoid site credentials, live equipment, package deployment and publication.\n\n"
        + prompt.strip() + "\n"
    )
    request = bundle / "REQUEST.md"
    request.write_text(instructions, encoding="utf-8")
    metadata = {"base_commit": base, "scope": [path.as_posix() for path in scoped]}
    (bundle / "draft.json").write_text(encode_json(metadata) + "\n", encoding="utf-8")
    if editor is not None:
        editor(worktree, instructions)
        return collect_draft(bundle)
    return {"state": "WORKTREE_READY", **metadata, "bundle": str(bundle),
            "worktree": str(worktree), "request": str(request)}


def _changed_paths(raw):
    return {PurePosixPath(item) for item in raw.decode("utf-8").split("\0") if item}


def collect_draft(bundle):
    """Export a reviewed-scope patch. The detached worktree is kept for inspection."""
    directory = Path(bundle).resolve(strict=True)
    worktree = directory / "worktree"
    if worktree.is_symlink() or not worktree.is_dir() or not (worktree / ".git").is_file():
        raise DraftError("Expected a detached draft worktree")
    manifest = directory / "draft.json"
    if manifest.is_symlink():
        raise DraftError("Draft metadata must be a local file")
    try:
        with manifest.open(encoding="utf-8") as stream:
            raw = stream.read(16 * 1024 + 1)
        if len(raw) > 16 * 1024:
            raise DraftError("Draft metadata exceeds the size limit")
        metadata = decode_json(raw)
        scope = _scope_paths(metadata["scope"])
        base = metadata["base_commit"]
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise DraftError("Draft metadata is invalid") from None
    if not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base):
        raise DraftError("Invalid draft base commit")
    if _git(worktree, "rev-parse", "--abbrev-ref", "HEAD").strip() != b"HEAD":
        raise DraftError("The draft must remain detached")
    tracked = _changed_paths(_git(worktree, "diff", "--name-only", "--no-renames", "-z", base))
    untracked = _changed_paths(_git(worktree, "ls-files", "--others", "--exclude-standard", "-z"))
    changed = tracked | untracked
    if len(changed) > 128 or any(not any(path.is_relative_to(rule) for rule in scope) for path in changed):
        raise DraftError("Draft changes exceed the selected review scope")
    for path in changed:
        local = worktree / path
        if local.is_symlink() or not local.resolve().is_relative_to(worktree):
            raise DraftError("Draft review requires regular files inside the worktree")
    if untracked:
        _git(worktree, "add", "--intent-to-add", "--", *sorted(path.as_posix() for path in untracked))
    patch = _git(worktree, "diff", "--binary", "--no-ext-diff", "--no-textconv", "--no-renames", base)
    if len(patch) > _MAX_PATCH_BYTES:
        raise DraftError("Draft patch exceeds the size limit")
    digest = hashlib.sha256(patch).hexdigest()
    patch_path = directory / f"review-{digest[:16]}.patch"
    try:
        with patch_path.open("xb") as stream:
            stream.write(patch)
    except FileExistsError:
        if patch_path.is_symlink() or patch_path.read_bytes() != patch:
            raise DraftError("Existing draft patch fails hash verification") from None
    return {"state": "DRAFT_REVIEW", "bundle": str(directory), "worktree": str(worktree),
            "base_commit": base, "changed_paths": sorted(path.as_posix() for path in changed),
            "patch": str(patch_path), "patch_sha256": digest}

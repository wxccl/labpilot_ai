from hashlib import sha256
from pathlib import Path
import shutil
import subprocess

import pytest

from labpilot_ai.harness import worktree as implementation
from labpilot_ai.harness.worktree import DraftError, collect_draft, draft_code


@pytest.fixture
def repo(tmp_path_factory):
    if not shutil.which("git"):
        pytest.skip("Git is required for detached worktrees")
    folder = tmp_path_factory.mktemp("git")
    checkout = folder / "p"
    checkout.mkdir()

    def git(*args):
        return subprocess.run(
            ["git", "-c", "core.longpaths=true", *args],
            cwd=checkout, check=True, capture_output=True,
        ).stdout

    try:
        git("init", f"--separate-git-dir={folder / 'metadata'}")
    except subprocess.CalledProcessError as exc:
        if b"permission denied" in exc.stderr.lower():
            pytest.skip("This sandbox prevents temporary Git metadata writes")
        raise
    git("config", "user.name", "Example Test")
    git("config", "user.email", "test@example.invalid")
    (checkout / "src").mkdir()
    (checkout / "src" / "example.py").write_text("value = 1\n", encoding="utf-8")
    (checkout / "README.md").write_text("example\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "Baseline")
    return checkout


def test_detached_draft_collects_tracked_and_new_changes_without_touching_primary(repo):
    draft = draft_code(repo=repo, review_root=repo.parent / "r", scope=["src"], prompt="Edit the example")
    assert draft["state"] == "WORKTREE_READY"
    worktree = Path(draft["worktree"])
    assert "Edit the example" in Path(draft["request"]).read_text(encoding="utf-8")
    (worktree / "src" / "example.py").write_text("value = 2\n", encoding="utf-8")
    (worktree / "src" / "additional.py").write_text("additional = 3\n", encoding="utf-8")
    result = collect_draft(draft["bundle"])
    assert result["state"] == "DRAFT_REVIEW"
    assert result["changed_paths"] == ["src/additional.py", "src/example.py"]
    patch = Path(result["patch"]).read_bytes()
    assert b"+value = 2" in patch
    assert b"+additional = 3" in patch
    assert result["patch_sha256"] == sha256(patch).hexdigest()
    assert collect_draft(draft["bundle"]) == result
    assert (repo / "src" / "example.py").read_text(encoding="utf-8") == "value = 1\n"
    assert not (repo / "src" / "additional.py").exists()


def test_draft_rejects_out_of_scope_changes(repo):
    def editor(worktree, _instructions):
        (worktree / "README.md").write_text("changed\n", encoding="utf-8")

    review = repo.parent / "r"
    with pytest.raises(DraftError, match="review scope"):
        draft_code(repo=repo, review_root=review, scope=["src"], prompt="Edit src", editor=editor)
    assert not list(review.rglob("review-*.patch"))
    assert (repo / "README.md").read_text(encoding="utf-8") == "example\n"


def test_draft_rejects_output_below_primary_checkout_and_scope_traversal(tmp_path, monkeypatch):
    repo = tmp_path / "project"
    repo.mkdir()
    monkeypatch.setattr(implementation, "_git", lambda directory, *_args: str(directory).encode())
    with pytest.raises(DraftError, match="outside"):
        draft_code(repo=repo, review_root=repo / "review", scope=["src"], prompt="Edit src")
    with pytest.raises(DraftError, match="repository-relative"):
        draft_code(repo=repo, review_root=tmp_path / "review", scope=["../elsewhere"], prompt="Edit src")


def test_draft_git_contract_without_metadata_permissions(tmp_path, monkeypatch):
    repo = tmp_path / "project"
    repo.mkdir()
    commit = "a" * 40
    calls = []
    fake_patch = b"diff --git a/src/value.py b/src/value.py\n"

    def git(directory, *args):
        calls.append((directory, args))
        if args == ("rev-parse", "--show-toplevel"):
            return str(directory).encode()
        if args == ("rev-parse", "--verify", "HEAD"):
            return commit.encode()
        if args[:3] == ("worktree", "add", "--detach"):
            assert args[4] == commit
            worktree = Path(args[3])
            worktree.mkdir()
            (worktree / ".git").write_text("gitdir: fake\n", encoding="utf-8")
            return b""
        if args == ("rev-parse", "--abbrev-ref", "HEAD"):
            return b"HEAD\n"
        if args[:2] == ("diff", "--name-only"):
            return b"src/value.py\0"
        if args[:2] == ("ls-files", "--others"):
            return b"src/new.py\0"
        if args[:2] == ("diff", "--binary"):
            return fake_patch
        assert args == ("add", "--intent-to-add", "--", "src/new.py")
        return b""

    monkeypatch.setattr(implementation, "_git", git)
    draft = draft_code(repo=repo, review_root=tmp_path / "review", scope=["src"], prompt="Edit src")
    result = collect_draft(draft["bundle"])
    assert Path(result["patch"]).read_bytes() == fake_patch
    assert result["changed_paths"] == ["src/new.py", "src/value.py"]
    assert calls[2][0] == repo
    assert all(path == Path(draft["worktree"]) for path, _ in calls[3:])

    invalid_draft = draft_code(repo=repo, review_root=tmp_path / "review", scope=["other"], prompt="Edit other")
    with pytest.raises(DraftError, match="review scope"):
        collect_draft(invalid_draft["bundle"])

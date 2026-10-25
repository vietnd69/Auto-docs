"""Read-only access to the ``dst-scripts`` git repository at any revision.

All git calls use argument lists (never a shell) and are confined to ``repo``.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from harness.safepath import normalize_rel


class GitError(RuntimeError):
    """A git command failed."""


@dataclass(frozen=True)
class Commit:
    sha: str
    date: str
    subject: str
    body: str


@dataclass(frozen=True)
class FileChange:
    """One entry of ``git diff --name-status -M``."""

    status: str  # A, M, D or R
    path: str
    old_path: str | None = None


_RECORD_SEP = "\x1e"
_FIELD_SEP = "\x1f"


class GitSource:
    """Thin wrapper around git plumbing commands for one repository."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo

    def _git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            raise GitError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result.stdout

    def rev_parse(self, rev: str) -> str:
        """Resolve any revision expression to a full SHA."""
        return self._git("rev-parse", "--verify", f"{rev}^{{commit}}").strip()

    def show(self, rev: str, path: str) -> str:
        """File content at ``rev`` (cached per full SHA)."""
        return _cached_show(self.repo, self.rev_parse(rev), normalize_rel(path))

    def show_many(self, rev: str, paths: list[str]) -> dict[str, str]:
        """Read many files at ``rev`` with one ``git cat-file --batch`` process."""
        sha = self.rev_parse(rev)
        request = "".join(f"{sha}:{normalize_rel(p)}\n" for p in paths).encode("utf-8")
        result = subprocess.run(
            ["git", "-C", str(self.repo), "cat-file", "--batch"],
            input=request,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise GitError(result.stderr.decode("utf-8", errors="replace").strip())
        return _parse_batch(result.stdout, paths)

    def exists(self, rev: str, path: str) -> bool:
        try:
            self._git("cat-file", "-e", f"{self.rev_parse(rev)}:{normalize_rel(path)}")
        except GitError:
            return False
        return True

    def ls_files(self, rev: str, suffix: str = ".lua") -> list[str]:
        """Tracked files at ``rev`` ending with ``suffix``, sorted."""
        out = self._git("ls-tree", "-r", "--name-only", self.rev_parse(rev))
        return sorted(line for line in out.splitlines() if line.endswith(suffix))

    def grep(self, rev: str, pattern: str, pathspec: str = "*.lua", max_count: int = 200) -> list[str]:
        """``git grep -n`` at ``rev``; returns ``path:line:text`` rows (rev prefix stripped)."""
        sha = self.rev_parse(rev)
        try:
            out = self._git("grep", "-n", "-I", "-E", "-e", pattern, sha, "--", pathspec)
        except GitError:
            return []  # git grep exits 1 when nothing matches
        prefix = f"{sha}:"
        rows = [line.removeprefix(prefix) for line in out.splitlines()]
        return rows[:max_count]

    def diff_name_status(self, old: str, new: str, suffix: str = ".lua") -> list[FileChange]:
        """Changed files between two revisions with rename detection."""
        out = self._git("diff", "--name-status", "-M", self.rev_parse(old), self.rev_parse(new))
        changes: list[FileChange] = []
        for line in out.splitlines():
            parts = line.split("\t")
            status = parts[0][0]
            if status == "R" and len(parts) == 3:
                change = FileChange("R", parts[2], parts[1])
            else:
                change = FileChange(status, parts[-1])
            if change.path.endswith(suffix) or (change.old_path or "").endswith(suffix):
                changes.append(change)
        return changes

    def log(self, rev_range: str) -> list[Commit]:
        """Commits in ``rev_range`` (oldest first) with full messages."""
        fmt = _FIELD_SEP.join(["%H", "%cs", "%s", "%b"]) + _RECORD_SEP
        out = self._git("log", "--reverse", f"--format={fmt}", rev_range)
        commits: list[Commit] = []
        for record in out.split(_RECORD_SEP):
            fields = record.strip("\n").split(_FIELD_SEP)
            if len(fields) == 4:
                commits.append(Commit(*fields))
        return commits

    def message(self, rev: str) -> Commit:
        """Single commit metadata."""
        sha = self.rev_parse(rev)
        commits = self.log(f"{sha}^!")
        if not commits:
            raise GitError(f"no commit for {rev}")
        return commits[0]

    def is_ancestor(self, older: str, newer: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(self.repo), "merge-base", "--is-ancestor", older, newer],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0


@lru_cache(maxsize=512)
def _cached_show(repo: Path, sha: str, path: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "show", f"{sha}:{path}"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise GitError(f"{path} not found at {sha[:10]}")
    return result.stdout.decode("utf-8", errors="replace")


def _parse_batch(data: bytes, paths: list[str]) -> dict[str, str]:
    contents: dict[str, str] = {}
    pos = 0
    for path in paths:
        header_end = data.index(b"\n", pos)
        header = data[pos:header_end].split()
        pos = header_end + 1
        if len(header) < 3 or header[1] != b"blob":
            continue  # "<name> missing"
        size = int(header[2])
        contents[path] = data[pos : pos + size].decode("utf-8", errors="replace")
        pos += size + 1
    return contents

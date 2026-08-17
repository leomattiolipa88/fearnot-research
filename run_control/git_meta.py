"""Read-only Git metadata capture.

Nothing here mutates the repository: no add, commit, tag, push, pull, fetch,
reset, restore, checkout, merge, rebase, or clean. If any invocation fails,
the corresponding field is left as ``None`` and the run continues.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

# Explicit deny-list makes the read-only invariant auditable at a glance.
_FORBIDDEN_GIT_VERBS = frozenset(
    {
        "add",
        "commit",
        "tag",
        "push",
        "pull",
        "fetch",
        "reset",
        "restore",
        "checkout",
        "merge",
        "rebase",
        "clean",
        "gc",
        "prune",
        "stash",
        "config",
    }
)


@dataclass
class GitMetadata:
    sha: str | None
    branch: str | None
    dirty: bool | None


def _run(args: list[str], cwd: Path, timeout: float = 5.0) -> str | None:
    verb = args[1] if len(args) > 1 else ""
    if verb in _FORBIDDEN_GIT_VERBS:
        raise AssertionError(
            f"capture_git_metadata attempted a mutating git verb: {verb!r}"
        )
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def capture_git_metadata(repo_root: Path | str) -> GitMetadata:
    """Capture SHA, branch and dirty flag from a working tree, read-only.

    All three fields are independent: any single one may be ``None`` if the
    underlying invocation fails, without invalidating the others.
    """
    root = Path(repo_root)
    sha = _run(["git", "rev-parse", "HEAD"], root)
    branch_raw = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    branch = None if branch_raw in (None, "", "HEAD") else branch_raw
    status = _run(["git", "status", "--porcelain"], root)
    dirty: bool | None
    if status is None:
        dirty = None
    else:
        dirty = bool(status.strip())
    return GitMetadata(sha=sha, branch=branch, dirty=dirty)

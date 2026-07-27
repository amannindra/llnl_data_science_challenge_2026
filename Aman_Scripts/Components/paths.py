"""Safe, centralized path discovery for scripts and generated artifacts."""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import Iterable


DEFAULT_REPOSITORY_MARKERS = ("Scripts", "data")


class RepositoryNotFoundError(FileNotFoundError):
    """Raised when no parent directory contains all repository markers."""


class UnsafePathError(ValueError):
    """Raised when a requested path resolves outside its permitted base."""


def _starting_directory(start: str | PathLike[str] | None) -> Path:
    candidate = Path(__file__) if start is None else Path(start).expanduser()
    candidate = candidate.resolve(strict=False)
    return candidate.parent if candidate.is_file() else candidate


def find_repository_root(
    start: str | PathLike[str] | None = None,
    *,
    markers: Iterable[str | PathLike[str]] = DEFAULT_REPOSITORY_MARKERS,
) -> Path:
    """Return the nearest ancestor containing every requested marker.

    ``start`` may name either a file or directory.  Discovery never relies on
    the process working directory unless the caller explicitly supplies it.
    Marker paths must be relative so an absolute marker cannot accidentally
    make an unrelated directory look like the repository.
    """

    marker_paths = tuple(Path(marker) for marker in markers)
    if not marker_paths:
        raise ValueError("at least one repository marker is required")
    if any(marker.is_absolute() or ".." in marker.parts for marker in marker_paths):
        raise ValueError("repository markers must be safe relative paths")

    origin = _starting_directory(start)
    for candidate in (origin, *origin.parents):
        if all((candidate / marker).exists() for marker in marker_paths):
            return candidate
    marker_text = ", ".join(str(marker) for marker in marker_paths)
    raise RepositoryNotFoundError(
        f"could not find a repository containing [{marker_text}] above {origin}"
    )


def ensure_within(
    base: str | PathLike[str],
    candidate: str | PathLike[str],
) -> Path:
    """Resolve ``candidate`` and require it to remain inside ``base``.

    Relative candidates are interpreted below ``base``.  Resolution follows
    existing symlinks, preventing a symlink from silently escaping the base.
    The returned path need not exist.
    """

    base_path = Path(base).expanduser().resolve(strict=False)
    requested = Path(candidate).expanduser()
    resolved = (
        requested.resolve(strict=False)
        if requested.is_absolute()
        else (base_path / requested).resolve(strict=False)
    )
    try:
        resolved.relative_to(base_path)
    except ValueError as exc:
        raise UnsafePathError(f"path escapes permitted base {base_path}: {resolved}") from exc
    return resolved


def repository_path(
    *parts: str | PathLike[str],
    root: str | PathLike[str] | None = None,
    must_exist: bool = False,
) -> Path:
    """Build a safe absolute path below the repository root."""

    repository = find_repository_root(root) if root is not None else find_repository_root()
    target = ensure_within(repository, Path(*parts)) if parts else repository
    if must_exist and not target.exists():
        raise FileNotFoundError(target)
    return target


def data_path(
    *parts: str | PathLike[str],
    root: str | PathLike[str] | None = None,
    must_exist: bool = False,
) -> Path:
    """Build a safe path below the repository's ``data`` directory."""

    repository = find_repository_root(root) if root is not None else find_repository_root()
    target = ensure_within(repository / "data", Path(*parts)) if parts else repository / "data"
    if must_exist and not target.exists():
        raise FileNotFoundError(target)
    return target


def scripts_path(
    *parts: str | PathLike[str],
    root: str | PathLike[str] | None = None,
    must_exist: bool = False,
) -> Path:
    """Build a safe path below the repository's ``Scripts`` directory."""

    repository = find_repository_root(root) if root is not None else find_repository_root()
    target = ensure_within(repository / "Scripts", Path(*parts)) if parts else repository / "Scripts"
    if must_exist and not target.exists():
        raise FileNotFoundError(target)
    return target


def output_path(
    *parts: str | PathLike[str],
    root: str | PathLike[str] | None = None,
    create: bool = False,
    must_exist: bool = False,
) -> Path:
    """Build a safe path below ``Scripts/outputs``.

    ``create=True`` creates the returned path as a directory.  This is the only
    path helper that writes, and the write is explicit at the call site.
    """

    repository = find_repository_root(root) if root is not None else find_repository_root()
    base = repository / "Scripts" / "outputs"
    target = ensure_within(base, Path(*parts)) if parts else base.resolve(strict=False)
    if create:
        target.mkdir(parents=True, exist_ok=True)
    if must_exist and not target.exists():
        raise FileNotFoundError(target)
    return target


def relative_repository_path(
    path: str | PathLike[str],
    *,
    root: str | PathLike[str] | None = None,
) -> Path:
    """Return a validated repository-relative representation of ``path``."""

    repository = find_repository_root(root) if root is not None else find_repository_root()
    return ensure_within(repository, path).relative_to(repository)

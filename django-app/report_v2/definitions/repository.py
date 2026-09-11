# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""File-backed definition drafts + immutable publication with atomic pointer swaps.

Mechanism:
- Revision tokens are SHA-256 hex digests of the YAML text (content-addressed).
- Publication writes blobs under root/blobs/ then atomically flips the pointer file
  root/pointers/<def_id> via os.replace (inode swap, safe for bind-mounts).
- Concurrency: fcntl.flock(LOCK_EX) on a per-def_id lockfile under root/.locks/
  serialises publishes of the SAME def_id; different def_ids are independent.
- Immutable means published blobs are never mutated; republishing changed content
  creates a NEW version blob; old blobs stay forever.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .loader import DefinitionError, load_report_definition
from .validation import (
    DisplayValidationError,
    ensure_no_calculated_baseline_band,
    ensure_whisker_is_not_ci,
    validate_display,
)
from ..projects.registry import CrossProjectReferenceError, ProjectRegistry, require_project_context
from ..projects.base import ProjectCatalogError

# ---------------------------------------------------------------------------
# Default private persistent root
# ---------------------------------------------------------------------------
# The runtime definitions/publish root is PRIVATE and lives OUTSIDE every public
# static surface: never under STATIC_ROOT (the collectstatic / WhiteNoise-served
# dir) and never under a STATICFILES_DIRS entry. An operator may point it
# elsewhere via settings.REPORT_V2_ROOT; the fallback below is derived from
# BASE_DIR and is deliberately placed under a ``private_data`` tree that
# collectstatic does not harvest. default_root() is pure path math (creates no
# directories) so importing this module never touches the filesystem.
_DEFAULT_ROOT_SUBPATH = ("private_data", "report_v2_definitions")


def default_root() -> Path:
    """Return the configured runtime publish root (a private, non-public path).

    Reads ``settings.REPORT_V2_ROOT`` when set; otherwise falls back to a
    documented ``private_data`` tree under ``settings.BASE_DIR``. The fallback is
    guaranteed NOT to live under ``STATIC_ROOT`` or any ``STATICFILES_DIRS``
    entry, so definition blobs are never collected by ``collectstatic`` nor served
    by WhiteNoise. No directories are created here.
    """
    from django.conf import settings as _s

    override = getattr(_s, "REPORT_V2_ROOT", None)
    if override:
        return Path(override)
    base = Path(str(getattr(_s, "BASE_DIR", Path.cwd())))
    return base.joinpath(*_DEFAULT_ROOT_SUBPATH)


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------

class RepositoryError(Exception):
    """Base class for all repository-level errors."""


class InvalidDefinitionIdError(RepositoryError):
    """Definition ID is malformed or unsafe."""


class PathTraversalError(RepositoryError):
    """Resolved path escapes the configured root (symlink-free traversal detected)."""


class PathEscapeError(RepositoryError):
    """A resolved symlink target escapes the configured root."""


class StaleRevisionError(RepositoryError):
    """Optimistic concurrency: expected_revision does not match current on-disk revision."""


class DraftNotFoundError(RepositoryError):
    """A draft does not exist at the given definition id."""


class PublishRejectedError(RepositoryError):
    """Validation failed; the pointer was NOT moved."""


class DuplicateVersionError(RepositoryError):
    """Target version blob already exists with different content."""


# ---------------------------------------------------------------------------
# Receipt dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PublishReceipt:
    """Proof-of-publication returned on success."""
    version: str
    blob_path: Path
    pointer_path: Path


# ---------------------------------------------------------------------------
# ID validation
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,63}$")


def validate_definition_id(def_id: str | None) -> str:
    """Reject unsafe or malformed definition IDs. Raise InvalidDefinitionIdError."""
    if def_id is None or def_id == "":
        raise InvalidDefinitionIdError("definition id must not be None or empty")
    if not isinstance(def_id, str):
        raise InvalidDefinitionIdError(f"definition id must be a string, got {type(def_id).__name__}")
    if _ID_RE.match(def_id) is None:
        raise InvalidDefinitionIdError(f"invalid definition id: {def_id!r}")
    # belt-and-suspenders explicit checks (regex already excludes these, but spec demands them)
    if "/" in def_id or "\\" in def_id:
        raise InvalidDefinitionIdError(f"path separator in id: {def_id!r}")
    if ".." in def_id:
        raise InvalidDefinitionIdError(f"parent traversal in id: {def_id!r}")
    if "~" in def_id:
        raise InvalidDefinitionIdError(f"tilde in id: {def_id!r}")
    if def_id.startswith("."):
        raise InvalidDefinitionIdError(f"dotfile id: {def_id!r}")
    if os.path.isabs(def_id):
        raise InvalidDefinitionIdError(f"absolute id: {def_id!r}")
    # NUL / control chars
    for ch in def_id:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise InvalidDefinitionIdError(f"control char in id: {def_id!r}")
    return def_id


# ---------------------------------------------------------------------------
# Path building with containment assertions
# ---------------------------------------------------------------------------

def _build_path(root: Path, def_id: str, *sub: str) -> Path:
    """Validate id, join, and assert logical containment under root (no symlink resolution)."""
    validate_definition_id(def_id)
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*sub, def_id)
    # Check logical path doesn't escape (without following symlinks)
    # Use os.path.normpath to collapse .. components without filesystem access
    normed = os.path.normpath(str(candidate))
    if not normed.startswith(str(resolved_root) + os.sep) and normed != str(resolved_root):
        raise PathTraversalError(f"path escapes root: {normed!r}")
    return Path(normed)


def _realpath_within(root: Path, path: Path) -> Path:
    """Check that realpath of path stays under realpath'd root; raise PathEscapeError if not."""
    real_root = Path(os.path.realpath(root))
    real_target = Path(os.path.realpath(path))
    if not real_target.is_relative_to(real_root):
        raise PathEscapeError(f"symlink target escapes root: {real_target!r}")
    return real_target


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

def _revision_of(yaml_text: str) -> str:
    """Content-addressed revision token (SHA-256 hex)."""
    return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()[:16]


class DefinitionRepository:
    """File-backed definition repository rooted at *root*, scoped to *project_id*."""

    def __init__(self, root: Path | str, *, project_id: str, registry: ProjectRegistry | None = None) -> None:
        self._root = Path(root)
        self._project_id = project_id
        self._registry = registry  # None => use production default
        # ensure subdirectory layout exists
        self._drafts_dir = self._root / "drafts"
        self._blobs_dir = self._root / "blobs"
        self._pointers_dir = self._root / "pointers"
        self._locks_dir = self._root / ".locks"
        self._tmp_dir = self._root / ".tmp"
        for d in (self._drafts_dir, self._blobs_dir, self._pointers_dir, self._locks_dir, self._tmp_dir):
            d.mkdir(parents=True, exist_ok=True)

    # -- Draft operations ---------------------------------------------------

    def _draft_path(self, def_id: str) -> Path:
        return _build_path(self._root, def_id, "drafts")

    def save_draft(self, def_id: str, yaml_text: str, *, expected_revision: str | None) -> str:
        """Write (or update) a draft. Returns the new revision token.

        Optimistic concurrency: if expected_revision does not match the current on-disk
        revision, raise StaleRevisionError without writing.
        """
        path = self._draft_path(def_id)
        # Check current revision
        current_rev: str | None = None
        if path.exists():
            content = path.read_text(encoding="utf-8")
            current_rev = _revision_of(content)
        # Compare by VALUE (not identity): the current revision is re-read from disk
        # so it is always a distinct str object with the same digest.
        if expected_revision is not None and current_rev != expected_revision:
            raise StaleRevisionError(
                f"expected revision {expected_revision!r} but current is {current_rev!r}"
            )
        # Atomic write
        tmp = self._tmp_dir / f"draft-{def_id}-{os.getpid()}"
        tmp.write_text(yaml_text, encoding="utf-8")
        fd = os.open(str(tmp), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(str(tmp), str(path))
        return _revision_of(yaml_text)

    def read_draft(self, def_id: str) -> tuple[str, str]:
        """Return (yaml_text, revision). Raise DraftNotFoundError if absent."""
        path = self._draft_path(def_id)
        if not path.exists():
            raise DraftNotFoundError(f"draft not found: {def_id!r}")
        # symlink safety
        _realpath_within(self._root, path)
        text = path.read_text(encoding="utf-8")
        return text, _revision_of(text)

    def validate_preview(self, def_id: str, yaml_text: str) -> list[str]:
        """Validate without writing. Returns list of violation strings (empty = ok)."""
        violations: list[str] = []
        try:
            data = load_report_definition(yaml_text)
        except (DefinitionError,) as exc:
            violations.append(str(exc))
            return violations
        # display validations
        try:
            ensure_whisker_is_not_ci(data)
        except DisplayValidationError as exc:
            violations.append(str(exc))
        try:
            ensure_no_calculated_baseline_band(data)
        except DisplayValidationError as exc:
            violations.append(str(exc))
        try:
            validate_display(data)
        except DisplayValidationError as exc:
            violations.append(str(exc))
        return violations

    # -- Publication --------------------------------------------------------

    def _blob_path(self, def_id: str, version: str) -> Path:
        """Path for a published blob. Version token is safe because def_id is already validated."""
        validate_definition_id(def_id)
        resolved_root = self._root.resolve()
        blob_name = f"{version}.yaml"
        candidate = (resolved_root / "blobs" / blob_name).resolve(strict=False)
        if not candidate.is_relative_to(resolved_root):
            raise PathTraversalError(f"blob path escapes root: {candidate!r}")
        return candidate

    def _pointer_path(self, def_id: str) -> Path:
        return _build_path(self._root, def_id, "pointers")

    def _lock_path(self, def_id: str) -> Path:
        return _build_path(self._root, def_id, ".locks")

    def _read_pointer(self, def_id: str) -> str | None:
        pp = self._pointer_path(def_id)
        if not pp.exists():
            return None
        _realpath_within(self._root, pp)
        return pp.read_text(encoding="utf-8").strip()

    def _next_version(self, def_id: str, current_pointer: str | None) -> str:
        """Compute the next version string for def_id."""
        if current_pointer is None:
            return f"{def_id}@r1"
        # parse trailing number after @r
        parts = current_pointer.split("@r")
        try:
            n = int(parts[-1])
        except (ValueError, IndexError):
            n = 0
        return f"{def_id}@r{n + 1}"

    def _validate_for_publish(self, yaml_text: str) -> dict[str, Any]:
        """Run loader + display validation; raise PublishRejectedError on failure. Return parsed data."""
        try:
            data = load_report_definition(yaml_text)
        except DefinitionError as exc:
            raise PublishRejectedError(str(exc)) from exc
        try:
            ensure_whisker_is_not_ci(data)
        except DisplayValidationError as exc:
            raise PublishRejectedError(str(exc)) from exc
        try:
            ensure_no_calculated_baseline_band(data)
        except DisplayValidationError as exc:
            raise PublishRejectedError(str(exc)) from exc
        try:
            validate_display(data)
        except DisplayValidationError as exc:
            raise PublishRejectedError(str(exc)) from exc
        return data

    def _check_project_refs(self, data: dict[str, Any]) -> None:
        """Walk parsed data for project-scoped identifiers; raise CrossProjectReferenceError on foreign refs.

        Collects measurement ids from top-level and nested sections[*].widgets[*].query, then calls
        the registry guard once per collected id (via require_project_context).
        """
        measurement_ids: list[str] = []
        # Top-level
        m = data.get("measurement") or data.get("measurement_id")
        if isinstance(m, str):
            measurement_ids.append(m)
        # Nested widgets
        for section in data.get("sections") or []:
            for widget in section.get("widgets") or []:
                q = widget.get("query") or {}
                mid = q.get("measurement") or q.get("measurement_id")
                if isinstance(mid, str):
                    measurement_ids.append(mid)
        for mid in measurement_ids:
            require_project_context(
                self._project_id,
                registry=self._registry,
                measurement_id=mid,
            )

    def publish(
        self,
        def_id: str,
        yaml_text: str,
        *,
        expected_revision: str | None = None,
    ) -> PublishReceipt:
        """Publish a definition immutably. Returns PublishReceipt.

        Steps (ordered):
          1. Validate id.
          2. Validate YAML + display (raises PublishRejectedError, pointer unchanged).
          3. Check project references (raises CrossProjectReferenceError).
          4. Compute version; check duplicate blob (DuplicateVersionError if content differs).
          5. Write blob atomically (tmp + fsync + os.replace on same fs).
          6. Flip pointer atomically (tmp + fsync + os.replace) under flock — the very last move.
        """
        # (1) validate id
        validate_definition_id(def_id)

        # (2) validate content
        data = self._validate_for_publish(yaml_text)

        # (3) project refs
        self._check_project_refs(data)

        # Acquire per-def_id lock for pointer operations
        lock_path = self._lock_path(def_id)
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            # (3.5) optimistic concurrency: when the caller asserts an expected
            # revision, the current on-disk draft revision must match it exactly.
            # Checked here, under the per-def_id lock and BEFORE any durable move,
            # so a racing writer that advanced the draft first makes this loser
            # fail loudly with no blob written and no pointer moved (no clobber).
            if expected_revision is not None:
                draft_rev: str | None = None
                draft_path = self._draft_path(def_id)
                if draft_path.exists():
                    draft_rev = _revision_of(draft_path.read_text(encoding="utf-8"))
                # Compare by VALUE (not identity): the digest re-read from disk is a
                # distinct str object with the same content hash.
                if draft_rev != expected_revision:
                    raise StaleRevisionError(
                        f"expected revision {expected_revision!r} but current is {draft_rev!r}"
                    )

            # (4) version computation + duplicate check
            current_pointer = self._read_pointer(def_id)
            version = self._next_version(def_id, current_pointer)
            blob_path = self._blob_path(def_id, version)
            if blob_path.exists():
                existing = blob_path.read_text(encoding="utf-8")
                if existing == yaml_text:
                    # idempotent no-op: same content already published
                    return PublishReceipt(version=version, blob_path=blob_path, pointer_path=self._pointer_path(def_id))
                raise DuplicateVersionError(
                    f"version {version!r} already exists with different content"
                )

            # (5) atomic blob write
            tmp_blob = self._tmp_dir / f"blob-{def_id}-{os.getpid()}-{id(object())}"
            tmp_blob.write_text(yaml_text, encoding="utf-8")
            fd = os.open(str(tmp_blob), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(str(tmp_blob), str(blob_path))

            # (6) atomic pointer flip (inode swap via os.replace)
            pp = self._pointer_path(def_id)
            tmp_ptr = self._tmp_dir / f"ptr-{def_id}-{os.getpid()}-{id(object())}"
            tmp_ptr.write_text(version, encoding="utf-8")
            fd = os.open(str(tmp_ptr), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(str(tmp_ptr), str(pp))

        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

        return PublishReceipt(version=version, blob_path=blob_path, pointer_path=pp)

    def get_current_version(self, def_id: str) -> str | None:
        """Return the current published version token for def_id, or None."""
        return self._read_pointer(def_id)

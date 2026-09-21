# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Transient render snapshots for report-v2 exports (Task 17).

A *render snapshot* is the short-lived, server-owned freeze of everything an export
(print now, email in Task 18) needs: the already-evaluated widget payloads, the
report/policy versions they were produced under, and the per-widget overrides
(dates / filters / comparison / page) that were active when the user asked to export.

Design contract (DESIGN.md "Page and storage proposal"; EXECUTION-RUNBOOK Task 17):

* **Frozen, not re-derived.** The stored document is the only input to the export
  renderer. A later dataset change or a new publication can never alter it, and an
  expired snapshot is never silently regenerated under newer definitions -- expiry is
  an explicit, typed failure telling the user to regenerate from the report page.
* **Scoped opaque ids.** The snapshot id handed to the browser is a server-signed
  token (domain-separated salt, never reused elsewhere) binding ``user``, ``project``
  and ``slug``; the payload is looked up under an unguessable random store key. A
  foreign user, foreign project or foreign report fails explicitly, as does any
  tampering with the token itself.
* **Bounded lifetime and size.** Retention is a bounded TTL (default 15 minutes);
  the store culls entries and refuses oversized payloads/widget counts.
* **Transient store, not process memory.** The deployment runs multiple gunicorn
  workers and no shared cache backend is configured, so the store is Django's
  file-based cache (existing infrastructure, no new dependency) rooted at a private,
  non-public directory -- overridable via ``settings.REPORT_V2_SNAPSHOT_ROOT``. It is
  deliberately *not* the definitions tree and is never served as media/static.
* **Not user preferences.** :func:`load_snapshot` hands the frozen document to the
  export renderer only; nothing in this module (or its callers) writes a snapshot
  back into page state, so an export can never resurrect itself as UI defaults.

Values are stored as JSON text (the cache backend pickles that single string), so a
snapshot document is plain-data in and plain-data out.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from django.core import signing
from django.core.cache.backends.filebased import FileBasedCache

__all__ = [
    "DEFAULT_SNAPSHOT_TTL",
    "MAX_SNAPSHOT_TTL",
    "MIN_SNAPSHOT_TTL",
    "MAX_SNAPSHOT_WIDGETS",
    "MAX_SNAPSHOT_BYTES",
    "SnapshotError",
    "SnapshotTamperedError",
    "SnapshotExpiredError",
    "SnapshotForeignError",
    "SnapshotPayloadError",
    "default_snapshot_root",
    "create_snapshot",
    "load_snapshot",
]

#: Domain-separated salt for the opaque snapshot token (never reused elsewhere).
_SNAP_SALT = "report_v2.snapshot.v1"

#: Bounded retention window (seconds). Short enough to be "transient export state",
#: long enough for a user to walk a print dialog through Save-as-PDF.
DEFAULT_SNAPSHOT_TTL = 900
MIN_SNAPSHOT_TTL = 60
MAX_SNAPSHOT_TTL = 3600

#: Hard size/count bounds so a snapshot can never become a durable archive.
MAX_SNAPSHOT_WIDGETS = 64
MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024

#: Store entry budget handed to the file cache (it culls on overflow).
_MAX_ENTRIES = 256
_CULL_FREQUENCY = 2

#: Private default root, mirroring the definitions tree convention (repository.py):
#: under ``private_data`` so collectstatic never harvests it and no public URL serves it.
_DEFAULT_ROOT_SUBPATH = ("private_data", "report_v2_snapshots")

_EXPIRED_MESSAGE = (
    "This export snapshot has expired. Close this page and regenerate it from the "
    "report page (Print / Save as PDF)."
)

_lock = threading.Lock()
_cache_instance: FileBasedCache | None = None


# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------
class SnapshotError(Exception):
    """Base for every snapshot-store failure (each surfaces explicitly to the caller)."""


class SnapshotTamperedError(SnapshotError):
    """The opaque snapshot token failed to verify or disagrees with the store entry."""


class SnapshotExpiredError(SnapshotError):
    """The snapshot's bounded lifetime is over; the user must regenerate it."""


class SnapshotForeignError(SnapshotError):
    """The snapshot exists but is scoped to another user, project or report."""


class SnapshotPayloadError(SnapshotError):
    """The document offered for freezing violates the size/count contract."""


# ---------------------------------------------------------------------------
# Store plumbing
# ---------------------------------------------------------------------------
def default_snapshot_root() -> Path:
    """The private snapshot-store root (pure path math; creates no directories).

    Reads ``settings.REPORT_V2_SNAPSHOT_ROOT`` when set, otherwise falls back to a
    ``private_data`` tree under ``settings.BASE_DIR`` -- never under ``STATIC_ROOT``
    or any ``STATICFILES_DIRS`` entry, so snapshot documents are neither collected
    by ``collectstatic`` nor served by WhiteNoise.
    """
    from django.conf import settings as _s

    override = getattr(_s, "REPORT_V2_SNAPSHOT_ROOT", None)
    if override:
        return Path(str(override))
    base = Path(str(getattr(_s, "BASE_DIR", Path.cwd())))
    return base.joinpath(*_DEFAULT_ROOT_SUBPATH)


def _store() -> FileBasedCache:
    """The process-wide file-backed store (created lazily; the backend mkdirs)."""
    global _cache_instance
    with _lock:
        if _cache_instance is None:
            # FileBasedCache creates its directory tree on construction, so this must
            # never run at import time (tests point the root at a temp dir first).
            _cache_instance = FileBasedCache(
                str(default_snapshot_root()),
                {"MAX_ENTRIES": _MAX_ENTRIES, "CULL_FREQUENCY": _CULL_FREQUENCY},
            )
        return _cache_instance


def _reset_store_for_tests() -> None:
    """Drop the cached store instance so the next use picks up a new settings root."""
    global _cache_instance
    with _lock:
        _cache_instance = None


def _json_coerce(value: Any) -> str:
    """The single tolerated non-JSON type: date/datetime ride inside table-row
    payloads and are ISO-formatted exactly like the page's own serialisation.
    Anything else (arbitrary objects, sets, callables, ...) stays a refusal."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not JSON-serialisable")


def _check_document(document: dict[str, Any]) -> None:
    """Enforce the plain-data contract before anything is frozen."""
    if not isinstance(document, dict):
        raise SnapshotPayloadError("snapshot document must be a JSON object")
    widgets = document.get("widgets")
    if not isinstance(widgets, list) or not widgets:
        raise SnapshotPayloadError("snapshot document must carry a non-empty widgets list")
    if len(widgets) > MAX_SNAPSHOT_WIDGETS:
        raise SnapshotPayloadError(
            f"snapshot carries {len(widgets)} widgets; the bound is {MAX_SNAPSHOT_WIDGETS}"
        )
    try:
        json.dumps(document, default=_json_coerce)
    except (TypeError, ValueError) as exc:
        raise SnapshotPayloadError(f"snapshot document is not JSON-serialisable: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def create_snapshot(
    *,
    user_id: int,
    project_id: str,
    slug: str,
    document: dict[str, Any],
    ttl: int = DEFAULT_SNAPSHOT_TTL,
) -> str:
    """Freeze ``document`` and return the opaque, server-signed snapshot token.

    The token binds ``(user, project, slug, expiry)``; the document itself is stored
    under an unguessable random key inside the private transient store with the same
    bounded timeout. Raises :class:`SnapshotPayloadError` for an oversized or
    non-plain-data document -- before anything is written.
    """
    if not (MIN_SNAPSHOT_TTL <= ttl <= MAX_SNAPSHOT_TTL):
        raise SnapshotPayloadError(
            f"snapshot ttl must be within [{MIN_SNAPSHOT_TTL}, {MAX_SNAPSHOT_TTL}] seconds"
        )
    _check_document(document)

    blob = json.dumps(document, sort_keys=True, default=_json_coerce)
    if len(blob.encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise SnapshotPayloadError(
            f"snapshot document is {len(blob.encode('utf-8'))} bytes; "
            f"the bound is {MAX_SNAPSHOT_BYTES}"
        )

    now = time.time()
    expires = now + ttl
    sid = secrets.token_hex(16)
    stored = {
        "sid": sid,
        "user_id": user_id,
        "project_id": project_id,
        "slug": slug,
        "created": now,
        "expires": expires,
        "document": document,
    }
    _store().set(f"snap:{sid}", json.dumps(stored, sort_keys=True, default=_json_coerce), timeout=ttl)

    return signing.dumps(
        {"sid": sid, "u": user_id, "p": project_id, "r": slug, "x": expires},
        salt=_SNAP_SALT,
    )


def load_snapshot(token: object, *, user_id: int, project_id: str, slug: str) -> dict[str, Any]:
    """Verify ``token`` and return the frozen document -- or raise a typed error.

    Failure modes are explicit and disjoint, in verification order:

    * tampered token / claim mismatch with the store entry -> :class:`SnapshotTamperedError`
    * token scoped to another user, project or report      -> :class:`SnapshotForeignError`
    * TTL over (signed expiry or store miss/timeout)       -> :class:`SnapshotExpiredError`
      (carrying the regenerate message; never a silent re-freeze under new definitions)
    """
    try:
        claims = signing.loads(token, salt=_SNAP_SALT)
    except Exception as exc:  # BadSignature / SignatureExpired / TypeError / ...
        raise SnapshotTamperedError("snapshot token failed to verify") from exc
    if not isinstance(claims, dict):
        raise SnapshotTamperedError("snapshot token payload is malformed")

    if claims.get("u") != user_id or claims.get("p") != project_id or claims.get("r") != slug:
        raise SnapshotForeignError("snapshot is scoped to another user, project or report")

    if not isinstance(claims.get("x"), (int, float)) or time.time() > float(claims["x"]):
        raise SnapshotExpiredError(_EXPIRED_MESSAGE)

    sid = claims.get("sid")
    if not isinstance(sid, str) or not sid:
        raise SnapshotTamperedError("snapshot token payload is malformed")
    raw = _store().get(f"snap:{sid}")
    if raw is None:
        # Store timeout or eviction: same explicit regenerate path as signed expiry.
        raise SnapshotExpiredError(_EXPIRED_MESSAGE)
    try:
        stored = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise SnapshotTamperedError("snapshot store entry is malformed") from exc

    if (
        stored.get("sid") != sid
        or stored.get("user_id") != claims.get("u")
        or stored.get("project_id") != claims.get("p")
        or stored.get("slug") != claims.get("r")
    ):
        raise SnapshotTamperedError("snapshot store entry does not match its token")
    if time.time() > float(stored.get("expires", 0)):
        raise SnapshotExpiredError(_EXPIRED_MESSAGE)

    document = stored.get("document")
    if not isinstance(document, dict):
        raise SnapshotTamperedError("snapshot store entry is malformed")
    return document

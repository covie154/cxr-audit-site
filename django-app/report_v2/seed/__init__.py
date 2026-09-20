# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Packaged, reviewed report-v2 seed material (vendored, never published from here).

The two YAML files that ship inside this package are byte-for-byte mirrors of the reviewed planning
drafts under ``.planning/report-v2/`` with only the single leading comment line replaced, so a copy can
never be mistaken for the reviewed original. Nothing here mutates the planning source and nothing here
publishes: this module only exposes the packaged bytes plus content-addressed digests so callers (the
seeding engine, the ``seed_report_v2`` command) can read and audit them without hard-coding any hash.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = [
    "REPORT_SEED_NAME",
    "POLICY_SEED_NAME",
    "SEED_DEF_ID",
    "SEED_REVISION",
    "SeedSourceError",
    "seed_dir",
    "seed_text",
    "report_seed_text",
    "policy_seed_text",
    "seed_digest",
    "seed_manifest",
]

#: File name of the packaged report seed inside this directory.
REPORT_SEED_NAME = "prime-overview.v1.yaml"
#: File name of the packaged threshold-policy seed inside this directory.
POLICY_SEED_NAME = "lunit-defaults.v1.yaml"
#: Definition id the reviewed seed carries at its top level (``id: overview``).
SEED_DEF_ID = "overview"
#: Human label for this vendored seed vintage; used only in messages, never as a content hash.
SEED_REVISION = "task16-v1"


class SeedSourceError(Exception):
    """A packaged seed file is missing or unreadable (a source-of-truth problem, not a schema problem)."""


def seed_dir() -> Path:
    """Return the packaged seed directory (the directory this package lives in)."""
    return Path(__file__).resolve().parent


def seed_text(name: str) -> str:
    """Return one packaged seed file decoded from its raw on-disk UTF-8 bytes, ``SeedSourceError`` if absent.

    The bytes are decoded verbatim (no newline translation) so the exact reviewed bytes -- CRLF included --
    flow unchanged into the installed draft, keeping the draft byte-for-byte faithful to the vendored seed
    and its content-addressed revision token consistent with :func:`seed_digest`.
    """
    path = seed_dir() / name
    if not path.is_file():
        raise SeedSourceError(f"packaged seed file is missing: {path}")
    return path.read_bytes().decode("utf-8")


def report_seed_text() -> str:
    """Return the packaged report seed text."""
    return seed_text(REPORT_SEED_NAME)


def policy_seed_text() -> str:
    """Return the packaged threshold-policy seed text."""
    return seed_text(POLICY_SEED_NAME)


def seed_digest(name: str) -> str:
    """Return the SHA-256 hex digest of a packaged seed file's on-disk bytes, computed at call time.

    The digest is always recomputed from the bytes currently on disk so the value cannot drift away from
    the file; nothing here stores a pre-baked hash.
    """
    path = seed_dir() / name
    if not path.is_file():
        raise SeedSourceError(f"packaged seed file is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_manifest() -> dict[str, str]:
    """Return ``{seed_file_name: sha256_hex}`` for both packaged seeds (auditable, nothing hard-coded)."""
    return {
        REPORT_SEED_NAME: seed_digest(REPORT_SEED_NAME),
        POLICY_SEED_NAME: seed_digest(POLICY_SEED_NAME),
    }

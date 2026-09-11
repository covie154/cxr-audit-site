# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Tests for the file-backed DefinitionRepository: ID safety, atomic publish, concurrency, immutability."""
from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path

from django.test import SimpleTestCase

from report_v2.definitions.repository import (
    DefinitionRepository,
    DraftNotFoundError,
    DuplicateVersionError,
    InvalidDefinitionIdError,
    PathEscapeError,
    PathTraversalError,
    PublishRejectedError,
    PublishReceipt,
    StaleRevisionError,
    default_root,
    validate_definition_id,
)
from report_v2.projects.base import (
    CrossProjectReferenceError,
    MeasurementSignature,
    ProjectDefinition,
    Source,
)
from report_v2.projects.registry import ProjectRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_YAML = """\
schema_version: 1
project: prime
id: testreport
title: T
grid:
  columns: 12
  row_height_px: 64
sections:
- id: s
  title: S
  widgets:
  - id: w
    title: W
    type: value
    layout:
      width: 2
      height: 3
    query:
      measurement: record_count
      inputs: {}
    window:
      start: '2025-12-12'
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: []
    ci:
      enabled: false
    export: full
"""

INVALID_YAML = """\
schema_version: 1
project: prime
id: bad
title: [&anchor "x"]
sections: []
"""

# YAML with a measurement that belongs to a foreign test project
FOREIGN_MEASUREMENT_YAML = """\
schema_version: 1
project: prime
id: foreign
title: F
grid:
  columns: 12
  row_height_px: 64
sections:
- id: s
  title: S
  widgets:
  - id: w
    title: W
    type: value
    layout:
      width: 2
      height: 3
    query:
      measurement: foreign_only_metric
      inputs: {}
    window:
      start: '2025-12-12'
      end: D
    controls:
      date_range: true
      filters: [site]
      compare_by: []
    ci:
      enabled: false
    export: full
"""


def _make_registry_with_two_projects() -> ProjectRegistry:
    """Create a registry with 'prime' (has record_count) and 'other' (has foreign_only_metric)."""
    reg = ProjectRegistry()
    prime_sources = {"record_id": Source("record_id", "record_id", "accession_no")}
    prime = ProjectDefinition(
        project_id="prime",
        display_name="PRIME",
        model_label="upload.cxrstudy",
        sources=prime_sources,
        measurements={"record_count": MeasurementSignature("record_count", {})},
    )
    other = ProjectDefinition(
        project_id="other",
        display_name="Other",
        model_label="upload.cxrstudy",
        sources={"record_id": Source("record_id", "record_id", "accession_no")},
        measurements={"foreign_only_metric": MeasurementSignature("foreign_only_metric", {})},
    )
    reg.register(prime, allow_overwrite=True)
    reg.register(other, allow_overwrite=True)
    return reg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class RepositoryTests(SimpleTestCase):
    """One test per Done-when criterion; all filesystem under tempfile.mkdtemp()."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="repo-test-"))

    def tearDown(self):
        # cleanup temp dir
        import shutil
        shutil.rmtree(self.root, ignore_errors=True)

    def _repo(self, project_id: str = "prime", registry: ProjectRegistry | None = None) -> DefinitionRepository:
        return DefinitionRepository(self.root, project_id=project_id, registry=registry)

    # ------------------------------------------------------------------
    def test_traversal_rejected(self):
        """Malicious IDs must raise InvalidDefinitionIdError / PathTraversalError; no files outside root."""
        repo = self._repo()
        bad_ids = ["../escape", "../../etc/passwd", "a/..", "/etc/passwd", "a%2fb", "a\\b", "a\x00b"]
        for bid in bad_ids:
            with self.subTest(id=bid):
                with self.assertRaises((InvalidDefinitionIdError, PathTraversalError)):
                    repo.save_draft(bid, VALID_YAML, expected_revision=None)

    # ------------------------------------------------------------------
    def test_symlink_escape_rejected(self):
        """A symlink under root pointing outside → PathEscapeError on read_draft."""
        repo = self._repo()
        # Save a valid draft first
        repo.save_draft("good", VALID_YAML, expected_revision=None)
        # Create a symlink under drafts that points outside root
        link_path = self.root / "drafts" / "evil"
        outside = Path(tempfile.mkdtemp(prefix="outside-"))
        try:
            (outside / "leak.yaml").write_text("secret", encoding="utf-8")
            os.symlink(str(outside / "leak.yaml"), str(link_path))
            with self.assertRaises(PathEscapeError):
                repo.read_draft("evil")
        finally:
            import shutil
            shutil.rmtree(outside, ignore_errors=True)

    # ------------------------------------------------------------------
    def test_wrong_project_rejected(self):
        """Draft referencing another project's ids → CrossProjectReferenceError."""
        registry = _make_registry_with_two_projects()
        repo = self._repo(project_id="prime", registry=registry)
        with self.assertRaises(CrossProjectReferenceError):
            repo.publish("crossref", FOREIGN_MEASUREMENT_YAML, expected_revision=None)

    # ------------------------------------------------------------------
    def test_duplicate_version_rejected(self):
        """Republishing changed content under an existing version → DuplicateVersionError."""
        repo = self._repo()
        # First publish creates r1
        receipt = repo.publish("dup", VALID_YAML, expected_revision=None)
        self.assertEqual(receipt.version, "dup@r1")
        # Monkeypatch _next_version to force it back to r1 (simulating a race on same version)
        original = repo._next_version
        repo._next_version = lambda def_id, cp: f"{def_id}@r1"
        try:
            different_yaml = VALID_YAML.replace("title: T", "title: Modified")
            with self.assertRaises(DuplicateVersionError):
                repo.publish("dup", different_yaml, expected_revision=None)
        finally:
            repo._next_version = original

    # ------------------------------------------------------------------
    def test_stale_revision_rejected(self):
        """save_draft with wrong expected_revision → StaleRevisionError; content not clobbered."""
        repo = self._repo()
        rev = repo.save_draft("conc", VALID_YAML, expected_revision=None)
        # Try to save with a bogus revision
        with self.assertRaises(StaleRevisionError):
            repo.save_draft("conc", "changed: yes", expected_revision="bogus-token")
        # Verify on-disk content unchanged
        text, _ = repo.read_draft("conc")
        self.assertEqual(text, VALID_YAML)

    # ------------------------------------------------------------------
    def test_stale_revision_rejected_on_publish(self):
        """publish() with a stale expected_revision → StaleRevisionError, no blob/pointer move."""
        repo = self._repo()
        # Seed a draft so a revision baseline exists, then publish once to set a pointer.
        rev = repo.save_draft("pubstale", VALID_YAML, expected_revision=None)
        receipt = repo.publish("pubstale", VALID_YAML, expected_revision=rev)
        pointer_before = repo._read_pointer("pubstale")
        self.assertEqual(pointer_before, receipt.version)
        blobs_before = sorted(p.name for p in (self.root / "blobs").iterdir())

        # Now the draft has advanced (a concurrent editor saved a changed draft), so the
        # revision the publisher still holds is stale. Publishing must fail WITHOUT moving
        # the pointer or writing any new blob.
        newer = repo.save_draft("pubstale", VALID_YAML.replace("title: T", "title: T2"), expected_revision=rev)
        self.assertNotEqual(newer, rev)

        with self.assertRaises(StaleRevisionError):
            repo.publish("pubstale", VALID_YAML.replace("title: T", "title: T3"), expected_revision=rev)

        # Pointer is untouched and no new blob appeared.
        self.assertEqual(repo._read_pointer("pubstale"), pointer_before)
        self.assertEqual(sorted(p.name for p in (self.root / "blobs").iterdir()), blobs_before)

    # ------------------------------------------------------------------
    def test_invalid_yaml_rejected_at_publish(self):
        """Malformed / anchor-using YAML → PublishRejectedError, pointer unchanged."""
        repo = self._repo()
        # Publish a valid version first
        repo.publish("inv", VALID_YAML, expected_revision=None)
        pointer_before = repo._read_pointer("inv")
        # Attempt to publish invalid YAML
        with self.assertRaises(PublishRejectedError):
            repo.publish("inv", INVALID_YAML, expected_revision=None)
        # Pointer must still reference the original version
        self.assertEqual(repo._read_pointer("inv"), pointer_before)

    # ------------------------------------------------------------------
    def test_failed_publish_keeps_old_pointer(self):
        """Mid-publish failure after blob temp write: pointer still references OLD version."""
        repo = self._repo()
        # Publish v1 successfully
        repo.publish("fp", VALID_YAML, expected_revision=None)
        old_pointer = repo._read_pointer("fp")
        self.assertIsNotNone(old_pointer)

        # Monkeypatch to raise after blob is written but before pointer move
        original_replace = os.replace
        call_count = [0]

        def patched_replace(src, dst):
            # Allow blob replace, fail on pointer replace
            if "ptr-" in str(src):
                raise OSError("injected failure")
            return original_replace(src, dst)

        os.replace = patched_replace
        try:
            changed = VALID_YAML.replace("title: T", "title: Changed")
            with self.assertRaises(OSError):
                repo.publish("fp", changed, expected_revision=None)
        finally:
            os.replace = original_replace

        # Pointer must still reference old version
        self.assertEqual(repo._read_pointer("fp"), old_pointer)

    # ------------------------------------------------------------------
    def test_multiple_reports_publish_independently(self):
        """Two def_ids: each pointer references its own version; failing A leaves B intact."""
        repo = self._repo()
        repo.publish("report-a", VALID_YAML, expected_revision=None)
        repo.publish("report-b", VALID_YAML, expected_revision=None)
        self.assertEqual(repo._read_pointer("report-a"), "report-a@r1")
        self.assertEqual(repo._read_pointer("report-b"), "report-b@r1")

        # Now fail publishing to report-a (invalid YAML)
        with self.assertRaises(PublishRejectedError):
            repo.publish("report-a", INVALID_YAML, expected_revision=None)
        # report-b unaffected
        self.assertEqual(repo._read_pointer("report-b"), "report-b@r1")

    # ------------------------------------------------------------------
    def test_concurrent_publishers_no_loss(self):
        """N threads publish distinct def_ids concurrently; all pointers valid, no partial writes."""
        n = 8
        errors: list[BaseException] = []
        barrier = threading.Barrier(n)

        def worker(i: int):
            try:
                barrier.wait()
                repo = DefinitionRepository(self.root, project_id="prime")
                repo.publish(f"conc-{i}", VALID_YAML, expected_revision=None)
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"threads raised: {errors}")
        # All pointers present and complete (single version token)
        check_repo = self._repo()
        for i in range(n):
            pointer = check_repo._read_pointer(f"conc-{i}")
            self.assertIsNotNone(pointer, f"conc-{i} pointer missing")
            self.assertTrue(pointer.endswith(f"@r1"))

        # Same-def_id contention: this is what the per-def_id flock actually protects.
        # N threads publish the SAME def_id; the exclusive lock serialises the
        # read-pointer -> write-blob -> flip-pointer sequence, so every successful
        # publish yields a DISTINCT version with its own durable blob and the final
        # pointer is a single complete token (no lost update, no interleaved content).
        same_errors: list[BaseException] = []
        same_versions: list[str] = []
        receipts_lock = threading.Lock()
        barrier2 = threading.Barrier(n)

        def same_worker(i: int):
            try:
                barrier2.wait()
                r = DefinitionRepository(self.root, project_id="prime")
                receipt = r.publish("hot", VALID_YAML, expected_revision=None)
                with receipts_lock:
                    same_versions.append(receipt.version)
            except BaseException as exc:
                same_errors.append(exc)

        threads2 = [threading.Thread(target=same_worker, args=(i,)) for i in range(n)]
        for t in threads2:
            t.start()
        for t in threads2:
            t.join()

        self.assertEqual(same_errors, [], f"same-def threads raised: {same_errors}")
        # Every concurrently-published version is distinct (the serialised +1 never repeats).
        self.assertEqual(len(set(same_versions)), n, f"versions not distinct: {same_versions}")
        # Final pointer is one complete, well-formed version token (never blank/partial).
        final = check_repo._read_pointer("hot")
        self.assertIsNotNone(final)
        self.assertRegex(final, r"^hot@r\d+$")
        # The final pointer is the highest published version, and its blob is durable.
        expected_final = f"hot@r{n}"
        self.assertEqual(final, expected_final, f"lost update: final pointer {final!r}")
        self.assertTrue((self.root / "blobs" / f"{final}.yaml").exists())
        # Every distinct version blob survived (no clobber / overwrite of a sibling).
        blob_names = {p.name for p in (self.root / "blobs").iterdir()}
        for v in same_versions:
            self.assertIn(f"{v}.yaml", blob_names, f"blob missing for {v}")

    # ------------------------------------------------------------------
    def test_container_mount_survives_replacement(self):
        """Republishing changes the pointer's inode (os.replace inode swap), blob unchanged."""
        repo = self._repo()
        receipt = repo.publish("mnt", VALID_YAML, expected_revision=None)
        pp = receipt.pointer_path
        inode_1 = pp.stat().st_ino
        blob_1_ino = receipt.blob_path.stat().st_ino

        # Publish a second version
        changed = VALID_YAML.replace("title: T", "title: V2")
        receipt2 = repo.publish("mnt", changed, expected_revision=None)
        inode_2 = pp.stat().st_ino

        self.assertNotEqual(inode_1, inode_2, "pointer inode should change on os.replace swap")
        # Original blob is untouched (same inode)
        self.assertEqual(receipt.blob_path.stat().st_ino, blob_1_ino)

    # ------------------------------------------------------------------
    def test_runtime_definitions_not_public_static(self):
        """Configured definitions root is NOT under STATIC_ROOT / public static/media."""
        from django.conf import settings as dj_settings

        static_root = Path(dj_settings.STATIC_ROOT).resolve()
        staticfiles_dirs = [Path(str(d)).resolve() for d in (dj_settings.STATICFILES_DIRS or [])]

        # (a) An injected temp root is clearly not under the public static surface.
        repo = self._repo()
        self.assertFalse(
            repo._root.resolve().is_relative_to(static_root),
            "test root must not be inside STATIC_ROOT",
        )

        # (b) The configured/runtime DEFAULT publish root (settings.REPORT_V2_ROOT
        #     override or the module fallback) must itself NOT live under
        #     STATIC_ROOT nor under any collectstatic STATICFILES_DIRS source, so a
        #     published definition blob can never be harvested by collectstatic nor
        #     served publicly by WhiteNoise.
        configured = default_root().resolve()
        self.assertFalse(
            configured.is_relative_to(static_root),
            f"default definitions root {configured!r} must NOT be inside STATIC_ROOT {static_root!r}",
        )
        for src in staticfiles_dirs:
            self.assertFalse(
                configured.is_relative_to(src),
                f"default definitions root {configured!r} must NOT be inside collectstatic source {src!r}",
            )

        # (c) An explicit operator override honoured by default_root() stays private too.
        with self.settings(REPORT_V2_ROOT=str(self.root / "operator-private")):
            self.assertFalse(
                default_root().resolve().is_relative_to(static_root),
                "operator override REPORT_V2_ROOT must not be inside STATIC_ROOT",
            )

# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Pure, side-effect-free installer for the reviewed report-v2 seed: validate, then draft.

This module is the *engine* behind ``manage.py seed_report_v2``. It reads the packaged seed bytes from
:mod:`report_v2.seed`, drives them through the strict definition loader, cross-checks every binding against
the PRIME project catalog, and installs the result as admin-editable **drafts** through the file-backed
:class:`~report_v2.definitions.repository.DefinitionRepository`.

Hard guarantees relied on by the rest of the system:

* It never imports, references, or calls a publication helper. The repository is only ever used through
  ``save_draft``; the pointer/publish surface is deliberately left untouched and unimported here, so a
  seed load can never move a published pointer. :class:`SeedPublicationForbidden` exists purely as a
  defensive trip for any caller that tries to smuggle a ``publish=True`` request in.
* Installation is validate-before-write: a single violation aborts with :class:`SeedValidationError`
  before the repository is even constructed, therefore before a single byte is written.
* The report and the policy are stored under *different* definition ids (the policy under a suffixed id) so
  the two artifacts can never be mistaken for one another.
* It contains no Django request objects, no ORM access, and no email -- it is importable in a bare
  interpreter.
"""
from __future__ import annotations

import re

from report_v2.definitions.loader import DefinitionError, load_policy, load_report_definition
from report_v2.definitions.repository import (DefinitionRepository, RepositoryError,
    StaleRevisionError, DraftNotFoundError, validate_definition_id)
from report_v2.projects.prime import get_project_definition
from report_v2.seed import (
    POLICY_SEED_NAME,
    REPORT_SEED_NAME,
    SEED_DEF_ID,
    policy_seed_text,
    report_seed_text,
)

__all__ = [
    "SeedError",
    "SeedValidationError",
    "SeedPublicationForbidden",
    "SEED_DEF_ID",
    "REPORT_SEED_NAME",
    "POLICY_SEED_NAME",
    "POLICY_SUFFIX",
    "CLASSIFICATION_SUMMARY_COLUMNS",
    "REFERENCE_AGREEMENT_COLUMNS",
    "PAIRED_REFERENCE_COLUMNS",
    "CASE_COLUMNS",
    "COLUMN_ALLOW_LIST",
    "load_seeds",
    "validate_seeds",
    "validate_seed_bindings",
    "seed_draft_texts",
    "install_drafts",
    "seed_summary",
]

#: The report and the policy live under different definition ids so a draft can never be mistaken for the
#: other; the policy is stored under ``<def_id><POLICY_SUFFIX>``.
POLICY_SUFFIX = "-policy"

# ---------------------------------------------------------------------------
# Declared column contracts per table measurement. Validation is done ONLY against these frozen sets
# (never derived from the measurement ``units`` map) so the column vocabulary stays an explicit,
# reviewable surface rather than an emergent property of the catalog.
# ---------------------------------------------------------------------------
CLASSIFICATION_SUMMARY_COLUMNS = (
    "n",
    "accuracy",
    "balanced_accuracy",
    "sensitivity",
    "specificity",
    "ppv",
    "npv",
    "tp",
    "tn",
    "fp",
    "fn",
    "predicted_negative_fraction",
)
REFERENCE_AGREEMENT_COLUMNS = ("n", "agreement", "kappa")
PAIRED_REFERENCE_COLUMNS = ("n", "b", "c", "p_value")
CASE_COLUMNS = ("accession", "site", "study_date", "highest_finding", "highest_score", "report_text")

#: Maps a table measurement id to the tuple of columns it is allowed to project. A widget whose measurement
#: is absent from this map is never column-checked (no declared contract to hold it to).
COLUMN_ALLOW_LIST: dict[str, tuple[str, ...]] = {
    "classification_summary": CLASSIFICATION_SUMMARY_COLUMNS,
    "reference_agreement": REFERENCE_AGREEMENT_COLUMNS,
    "paired_reference_comparison": PAIRED_REFERENCE_COLUMNS,
    "false_negatives": CASE_COLUMNS,
    "false_positives": CASE_COLUMNS,
}


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------
class SeedError(Exception):
    """Base for every seeding-engine failure."""


class SeedValidationError(SeedError):
    """One or more seed validations failed; nothing was written.

    ``violations`` carries the collected human-readable strings (each already embedding the loader's
    path/line context when the failure originated in the strict loader).
    """

    def __init__(self, message: str = "seed validation failed", *, violations=None) -> None:
        super().__init__(message)
        self.violations: list[str] = list(violations) if violations else []


class SeedPublicationForbidden(SeedError):
    """Defensive trip: raised if anything ever tries to turn a draft install into a publication."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
_ID_LINE_RE = re.compile(r"(?m)^id:[^\r\n]*")


def _iter_widgets(report_data: dict):
    """Yield every widget mapping from a strict-loaded report definition, in document order."""
    for section in report_data.get("sections") or []:
        for widget in (section or {}).get("widgets") or []:
            yield widget


def _load_report_or_none(text: str) -> tuple[dict | None, str | None]:
    """Strict-load ``text``; return ``(data, None)`` on success or ``(None, str(exc))`` on a DefinitionError."""
    try:
        return load_report_definition(text, source=REPORT_SEED_NAME), None
    except DefinitionError as exc:  # DefinitionError.__str__ already embeds source/path/line
        return None, str(exc)


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------
def load_seeds() -> tuple[str, str]:
    """Return ``(report_yaml, policy_yaml)`` read from the packaged seed bytes."""
    return report_seed_text(), policy_seed_text()


def validate_seeds(report_yaml: str | None = None, policy_yaml: str | None = None) -> list[str]:
    """Collect every structural violation across *both* seeds plus the threshold-policy cross-check.

    Each seed is strict-loaded through the loader; every :class:`DefinitionError` is folded into one
    violation string (they already carry path/line context) and *nothing* stops at the first failure.
    Afterwards every widget ``query.threshold_policy`` reference (form ``<id>@<version>``) is required to
    resolve against the packaged policy seed's own ``id``/``version``.
    """
    report_text = report_seed_text() if report_yaml is None else report_yaml
    policy_text = policy_seed_text() if policy_yaml is None else policy_yaml

    violations: list[str] = []

    report_data, report_error = _load_report_or_none(report_text)
    if report_error is not None:
        violations.append(report_error)

    try:
        load_policy(policy_text, source=POLICY_SEED_NAME)
    except DefinitionError as exc:
        violations.append(str(exc))

    # Cross-check only makes sense once the report itself parsed; the reference target is always the
    # *packaged* policy seed's identity, independent of any caller-supplied policy text.
    if report_data is not None:
        try:
            packaged_policy = load_policy(policy_seed_text(), source=POLICY_SEED_NAME)
        except DefinitionError as exc:
            violations.append(str(exc))
        else:
            expected_ref = f"{packaged_policy['id']}@{packaged_policy['version']}"
            for widget in _iter_widgets(report_data):
                ref = (widget.get("query") or {}).get("threshold_policy")
                if ref is None:
                    continue
                if ref != expected_ref:
                    widget_id = widget.get("id", "<no-id>")
                    violations.append(
                        f"widget {widget_id!r}: query.threshold_policy reference {ref!r} does not resolve "
                        f"against the packaged policy seed {expected_ref!r}"
                    )
    return violations


def validate_seed_bindings(report_yaml: str | None = None, *, project=None) -> list[str]:
    """Cross-check every widget binding in the report seed against the PRIME project catalog.

    For every widget (default: the packaged report text, validated against
    :func:`report_v2.projects.prime.get_project_definition`) the following must hold; any breach yields one
    violation string naming the widget and the offending identifier:

    * ``query.measurement`` is a key of ``project.measurements``;
    * every ``query.inputs`` role is declared by that signature (``inputs`` or ``optional_inputs``) and the
      bound source exists in ``project.sources`` carrying exactly the ``kind`` the signature declares;
    * ``query.cohort`` (when present) is a key of ``project.cohorts``;
    * ``controls.filters``, ``controls.compare_by`` and ``default_compare_by`` are keys of ``project.dimensions``;
    * every ``columns`` entry is one of the columns declared for that measurement in :data:`COLUMN_ALLOW_LIST`.
    """
    if project is None:
        project = get_project_definition()

    report_text = report_seed_text() if report_yaml is None else report_yaml
    report_data, report_error = _load_report_or_none(report_text)
    if report_error is not None:
        # Without a parsed document there is nothing to bind-check; surface the loader's own diagnostic.
        return [report_error]

    violations: list[str] = []
    for widget in _iter_widgets(report_data):
        widget_id = widget.get("id", "<no-id>")
        query = widget.get("query") or {}
        measurement = query.get("measurement")

        signature = project.measurements.get(measurement)
        if signature is None:
            violations.append(f"widget {widget_id!r}: unknown measurement {measurement!r}")
        else:
            declared = dict(signature.inputs or {})
            optional = dict(signature.optional_inputs or {})
            for role in declared:
                if role not in (query.get("inputs") or {}):
                    violations.append(f"widget {widget_id!r}: missing required input role {role!r}")
            for role, source_id in (query.get("inputs") or {}).items():
                if role not in declared and role not in optional:
                    violations.append(
                        f"widget {widget_id!r}: input role {role!r} is not declared by measurement {measurement!r}"
                    )
                    continue
                expected_kind = declared.get(role, optional.get(role))
                source = project.sources.get(source_id)
                if source is None:
                    violations.append(
                        f"widget {widget_id!r}: input role {role!r} binds unknown source {source_id!r}"
                    )
                    continue
                if source.kind != expected_kind:
                    violations.append(
                        f"widget {widget_id!r}: input role {role!r} bound to source {source_id!r} has kind "
                        f"{source.kind!r}, expected {expected_kind!r}"
                    )

            columns = widget.get("columns")
            if columns:
                allowed = COLUMN_ALLOW_LIST.get(measurement)
                if allowed is not None:
                    allowed_set = set(allowed)
                    for column in columns:
                        if column not in allowed_set:
                            violations.append(
                                f"widget {widget_id!r}: column {column!r} is not supported by measurement {measurement!r}"
                            )

        cohort = query.get("cohort")
        if cohort is not None and cohort not in project.cohorts:
            violations.append(f"widget {widget_id!r}: unknown cohort {cohort!r}")

        controls = widget.get("controls") or {}
        for dimension in (controls.get("filters") or []):
            if dimension not in project.dimensions:
                violations.append(f"widget {widget_id!r}: filter dimension {dimension!r} is not a known dimension")
        for dimension in (controls.get("compare_by") or []):
            if dimension not in project.dimensions:
                violations.append(f"widget {widget_id!r}: compare_by dimension {dimension!r} is not a known dimension")
        default_compare_by = widget.get("default_compare_by")
        if default_compare_by is not None and default_compare_by not in project.dimensions:
            violations.append(
                f"widget {widget_id!r}: default_compare_by {default_compare_by!r} is not a known dimension"
            )
    return violations


def seed_draft_texts(*, def_id: str = SEED_DEF_ID) -> dict[str, str]:
    """Return the packaged seed texts, with the report's top-level ``id`` retargeted to ``def_id``.

    When ``def_id`` already equals :data:`SEED_DEF_ID` the packaged report text is returned untouched.
    Otherwise exactly the single top-level ``id:`` line (column zero; widget/section ``- id:`` list items are
    indented and therefore never matched) is rewritten and the result is re-strict-loaded; a loader
    rejection becomes a :class:`SeedValidationError` naming ``def_id``. The policy text is always returned
    unmodified.
    """
    validate_definition_id(def_id)
    validate_definition_id(f"{def_id}{POLICY_SUFFIX}")
    report_text = report_seed_text()
    policy_text = policy_seed_text()

    if def_id != SEED_DEF_ID:
        replacement = f"id: {def_id}"
        candidate, changed = _ID_LINE_RE.subn(lambda _match: replacement, report_text, count=1)
        if changed != 1:
            raise SeedValidationError(
                f"could not locate a single top-level id line to retarget for def_id {def_id!r}",
                violations=[f"def_id {def_id!r}: top-level id line not found exactly once"],
            )
        try:
            load_report_definition(candidate, source=REPORT_SEED_NAME)
        except DefinitionError as exc:
            raise SeedValidationError(
                f"retargeting the top-level id to {def_id!r} produced an invalid report definition: {exc}",
                violations=[str(exc)],
            ) from exc
        report_text = candidate

    return {"report": report_text, "policy": policy_text}


def install_drafts(root, *, def_id: str = SEED_DEF_ID, expected_revisions=None, **_guard) -> dict:
    """Validate the seed pair, then write it as two drafts under ``root`` -- never publishing.

    Validation (:func:`validate_seeds` + :func:`validate_seed_bindings`) runs *before* the repository is
    constructed, so any violation aborts with :class:`SeedValidationError` without writing a single byte.
    On success the report is saved under ``def_id`` and the policy under ``def_id + POLICY_SUFFIX`` via
    ``save_draft`` only. No publication helper is imported or called anywhere in this module; a caller that
    smuggles a ``publish`` keyword in is met with :class:`SeedPublicationForbidden`.
    """
    # The sanctioned signature offers no ``publish`` axis at all; trap any attempt to introduce one.
    if "publish" in _guard:
        raise SeedPublicationForbidden(
            "install_drafts is drafts-only by design and never publishes; refusing a publish request"
        )
    if _guard:
        raise SeedError(f"unexpected keyword argument(s) for install_drafts: {sorted(_guard)}")

    texts = seed_draft_texts(def_id=def_id)
    violations = validate_seeds(report_yaml=texts["report"], policy_yaml=texts["policy"])
    violations += validate_seed_bindings(report_yaml=texts["report"])
    if violations:
        raise SeedValidationError("seed validation failed before any write", violations=violations)

    expected = dict(expected_revisions or {})
    try:
        repository = DefinitionRepository(root, project_id="prime")
        policy_def_id = f"{def_id}{POLICY_SUFFIX}"
        current = {}
        current_text = {}
        for key, draft_id in (("report", def_id), ("policy", policy_def_id)):
            try:
                current_text[key], current[key] = repository.read_draft(draft_id)
            except DraftNotFoundError:
                current[key] = None
            if expected.get(key) is not None and expected[key] != current[key]:
                raise StaleRevisionError("seed draft changed; reload before loading the seed")
        if (current["report"] is not None and expected.get("report") is None
                and current_text["report"] != texts["report"].replace("\r\n", "\n")):
            raise StaleRevisionError("report draft already exists; load it in the editor before replacing it")
        report_revision = repository.save_draft(
            def_id, texts["report"], expected_revision=expected.get("report")
        )
        # Loading a report seed must never reset a separately edited policy draft.
        policy_revision = current["policy"]
        if policy_revision is None:
            policy_revision = repository.save_draft(policy_def_id, texts["policy"], expected_revision=None)
    except StaleRevisionError:
        raise
    except RepositoryError as exc:
        # Repository-level rejections (bad id, stale revision, path escape) are seeding failures too.
        raise SeedError(f"draft installation failed: {exc}") from exc

    return {
        "def_id": def_id,
        "report_revision": report_revision,
        "policy_def_id": policy_def_id,
        "policy_revision": policy_revision,
        "status": "drafted",
        "drafts_only": True,
        "published": False,
    }


def seed_summary(report_yaml: str | None = None) -> dict:
    """Return ``{"def_id","title","sections","widgets","by_type"}`` counts taken from the strict-loaded report.

    ``def_id``/``title`` are the report's own top-level ``id``/``title``; ``widgets`` is the total widget
    count and ``by_type`` a ``type -> count`` tally (keys sorted for a deterministic, printable mapping).
    """
    report_text = report_seed_text() if report_yaml is None else report_yaml
    report_data, report_error = _load_report_or_none(report_text)
    if report_error is not None:
        raise SeedValidationError("cannot summarise an invalid report seed", violations=[report_error])

    sections = 0
    widgets = 0
    by_type: dict[str, int] = {}
    for section in report_data.get("sections") or []:
        sections += 1
        for widget in (section or {}).get("widgets") or []:
            widgets += 1
            widget_type = str(widget.get("type"))
            by_type[widget_type] = by_type.get(widget_type, 0) + 1

    return {
        "def_id": report_data.get("id"),
        "title": report_data.get("title"),
        "sections": sections,
        "widgets": widgets,
        "by_type": {key: by_type[key] for key in sorted(by_type)},
    }

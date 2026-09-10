# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Synthetic test fixture / factory layer for the report_v2 measurement runbook.

Two kinds of fixtures are provided:

(A) In-memory records: plain ``dict``s carrying the *logical* label fields a later
    measurement layer consumes. They NEVER touch the ORM.
(B) Synthetic ``CXRStudy`` ORM rows: created through the Django ORM inside the
    test database the runner provisions. Every DB-writing builder is guarded by
    :func:`ensure_test_database` so it can never write to the real sqlite file.

Everything is fully reproducible: all randomness flows from the single
``random.Random(FIXED_SEED)`` family below, seeded from ``FIXED_SEED`` at import,
and every synthetic string is obviously fake (SYNTH prefix). No real accessions,
patient ids/names, or realistic radiology prose are ever produced.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from django.conf import settings as dj_settings
from django.db import connections
from django.utils import timezone as dj_timezone

from upload.models import CXRStudy

# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #
FIXED_SEED = 20260910


def _rng(offset: int = 0) -> random.Random:
    """Return a freshly seeded RNG derived from ``FIXED_SEED``.

    A *new* ``random.Random`` is created per call (seeded from ``FIXED_SEED``
    plus an optional family offset) so repeated calls to a builder reproduce
    byte-identical values. Never use the module-level ``random`` directly.
    """
    return random.Random(FIXED_SEED + int(offset))


# --------------------------------------------------------------------------- #
# Synthetic identity conventions
# --------------------------------------------------------------------------- #
SYNTH_MARK = "SYNTH"
RESERVED_ACCESSION_BASE = 900000000  # reserved non-clinical accession block
RESERVED_ACCESSION_SPAN = 1_000_000   # 900000000 .. 900999999
TEXT_REPORT_PREFIX = "SYNTHETIC-TEST-REPORT (no clinical content)"
SITES = ("SYNTH-SITE-A", "SYNTH-SITE-B")

# model-permitted gender values; CXRStudy.patient_gender has NO choices, so any
# short string is permitted -- we keep to the obvious M/F for readability.
GENDERS = ("M", "F")

# The Lunit finding-score FloatFields that CXRStudy actually defines (verified
# against upload/models.py). These are the keys used in `findings` dicts and on
# DB rows. (The runbook lists ~ten "relevant" findings; the model has these 12.)
ALL_FINDINGS = (
    "abnormal",
    "atelectasis",
    "calcification",
    "cardiomegaly",
    "consolidation",
    "fibrosis",
    "mediastinal_widening",
    "nodule",
    "pleural_effusion",
    "pneumoperitoneum",
    "pneumothorax",
    "tuberculosis",
)

# Field that encodes the binary prediction on DB rows via a strict >10 threshold.
BINARY_DESIGNATED_FINDING = "abnormal"
# Field that encodes the 3-class label on DB rows via a documented score band.
THREECLASS_DESIGNATED_FINDING = "consolidation"
# Three-class score bands (documented mapping, consistent with the >10 idea):
#   < 10      -> class "A"
#   10 .. 30  -> class "B"
#   > 30      -> class "C"
CLASS_BANDS = {"A": 5.0, "B": 20.0, "C": 35.0}
CLASS_ORDER = ("A", "B", "C")

# Threshold shared by v2 recomputation: binarised = score > SCORE_THRESHOLD.
SCORE_THRESHOLD = 10.0

# Identifier/text fields that MUST pass the synthetic check on a DB row / study.
IDENTIFIER_TEXT_FIELDS = (
    "patient_name",
    "patient_id",
    "study_id",
    "study_description",
    "text_report",
    "workplace",
)
# In-memory record keys that carry identifiers/text (excludes gender, which is
# not an identifier and legitimately holds "M"/"F").
DICT_IDENTIFIER_KEYS = (
    "accession",
    "patient_name",
    "patient_id",
    "study_id",
    "study_description",
    "text_report",
    "site",
)


# --------------------------------------------------------------------------- #
# Synthetic-only guards
# --------------------------------------------------------------------------- #
def assert_no_real_identifiers(value: object) -> None:
    """Raise ``AssertionError`` unless *value* is obviously synthetic.

    Rule (simple on purpose):
      * ``None``                       -> allowed (missing values are expected).
      * ``int``                        -> must live in the reserved accession block.
      * ``str``                        -> must carry the SYNTH marker.
      * anything else (float/datetime) -> not an identifier, allowed through.

    This is deliberately conservative: any free text without the SYNTH marker --
    e.g. realistic radiology prose or a real accession -- fails immediately.
    """
    if value is None:
        return
    if isinstance(value, bool):
        # bool is an int subclass; treat as a non-identifier, allow through.
        return
    if isinstance(value, int):
        if not (RESERVED_ACCESSION_BASE <= value < RESERVED_ACCESSION_BASE + RESERVED_ACCESSION_SPAN):
            raise AssertionError(f"non-synthetic accession value: {value!r}")
        return
    if isinstance(value, str):
        if not value.startswith(SYNTH_MARK) and SYNTH_MARK not in value:
            raise AssertionError(f"identifier/text is not synthetic: {value!r}")
        return
    # float / datetime / Decimal / ... -- not identifiers; nothing to check.
    return


def _iter_identifier_items(obj):
    """Yield (name, value) for every identifier-bearing field on a study/dict."""
    if isinstance(obj, CXRStudy):
        yield "accession_no", obj.accession_no
        for name in IDENTIFIER_TEXT_FIELDS:
            yield name, getattr(obj, name, None)
    elif isinstance(obj, dict):
        for key in DICT_IDENTIFIER_KEYS:
            if key in obj:
                yield key, obj[key]
    else:
        raise TypeError(f"_assert_synthetic_only expects CXRStudy or dict, got {type(obj)!r}")


def _assert_synthetic_only(study_or_dict) -> None:
    """Assert every identifier/text field on *study_or_dict* is synthetic."""
    for name, value in _iter_identifier_items(study_or_dict):
        try:
            assert_no_real_identifiers(value)
        except AssertionError as exc:  # re-raise with the offending field name
            raise AssertionError(f"{name}: {exc}") from exc


# --------------------------------------------------------------------------- #
# Test-database guard
# --------------------------------------------------------------------------- #
def ensure_test_database(alias: str = "default") -> None:
    """Refuse to write unless the current connection is the runner's test DB.

    Two-stage check that a real on-disk database can never satisfy:
      1. Hard-reject any ``*.sqlite``/``*.sqlite3``/``*.db`` file path outright, so a
         production sqlite file such as ``.../db/db.sqlite3`` is stopped here, before
         any acceptance check. (Do NOT compare against ``settings.DATABASES``: the
         runner mutates the configured NAME to the test DB, so it is not a usable
         production signal during tests.)
      2. Accept only the shapes Django's test runner produces: an in-memory SQLite
         (``":memory:"`` or a ``file:...mode=memory...`` URI) or a database named
         under the configured TEST prefix (``test_...``, e.g. PostgreSQL).
    """
    conn = connections[alias]
    name = str(conn.settings_dict.get("NAME", ""))
    base = name.replace("\\", "/").split("/")[-1]

    if base.endswith((".sqlite", ".sqlite3", ".db")):
        raise RuntimeError(
            f"Refusing to write: {name!r} looks like an on-disk database file. "
            "These builders must target the runner's in-memory test database only."
        )
    is_test = (
        name == ":memory:"
        or "memory" in name.lower()
        or base.startswith("test_")
    )
    if not is_test:
        raise RuntimeError(
            "Refusing to write: current database is not the runner's test database "
            f"(NAME={name!r}). Run these builders only inside a Django test database."
        )


# --------------------------------------------------------------------------- #
# Small shared builders
# --------------------------------------------------------------------------- #
def _aware(dt: datetime) -> datetime:
    """Make *dt* timezone-aware using the configured timezone when USE_TZ is on."""
    if getattr(dj_settings, "USE_TZ", False):
        return dt.replace(tzinfo=dj_timezone.get_current_timezone())
    return dt


def _iso(dt: datetime | None) -> str | None:
    return None if dt is None else dt.isoformat()


def _synthetic_identity(index: int) -> dict:
    """Deterministic synthetic identifier fields for a study (index drives the id)."""
    acc = RESERVED_ACCESSION_BASE + index
    suffix = f"{index:04d}"
    return {
        "accession_no": acc,
        "patient_name": f"SYNTH PATIENT {suffix}",
        "patient_id": f"SYNTH-PID-{suffix}",
        "study_id": f"SYNTH-STUDY-{suffix}",
        "study_description": f"SYNTH-STUDY-DESC {acc}",
        "text_report": f"{TEXT_REPORT_PREFIX} {acc}",
        "patient_age": 40 + (index % 30),
        "patient_gender": GENDERS[index % len(GENDERS)],
    }


def _baseline_findings(overrides: dict | None = None) -> dict:
    """All findings present and valid (require-all satisfiable); default 5.0."""
    findings = {name: 5.0 for name in ALL_FINDINGS}
    if overrides:
        findings.update(overrides)
    return findings


# --------------------------------------------------------------------------- #
# (A) In-memory record constructors -- NO ORM access
# --------------------------------------------------------------------------- #
def _binary_inmemory(gts, preds, site=SITES[0], base=1) -> list[dict]:
    recs = []
    for i, (gt, pred) in enumerate(zip(gts, preds)):
        findings = _baseline_findings({
            BINARY_DESIGNATED_FINDING: 20.0 if pred == 1 else 5.0
        })
        recs.append({
            "accession": RESERVED_ACCESSION_BASE + base + i,
            "gt_label": gt,
            "pred_label": pred,
            "gt_class": None,
            "pred_class": None,
            "classes": [],
            "site": site,
            "procedure_start_date": "2026-08-15T09:00:00+00:00",
            "duration_seconds": 300.0,
            "findings": findings,
            "in_coverage": True,
            "missing_field": None,
        })
    return recs


def binary_fixture(site: str = SITES[0]) -> list[dict]:
    """Six eligible records: GT [1,1,1,0,0,0], pred [1,1,0,1,0,0].

    Matches the runbook "Binary comparison" hand-check (TP=2,FN=1,FP=1,TN=2).
    """
    gts = [1, 1, 1, 0, 0, 0]
    preds = [1, 1, 0, 1, 0, 0]
    return _binary_inmemory(gts, preds, site=site, base=1)


def binary_fixture_with_missing_gt(site: str = SITES[0]) -> list[dict]:
    """The six eligible records plus one extra in-coverage row whose GT is None.

    => matching=7, eligible=6, excluded=1 (the extra row is in coverage but has
    no ground-truth, so it is excluded from eligibility).
    """
    recs = _binary_inmemory([1, 1, 1, 0, 0, 0], [1, 1, 0, 1, 0, 0], site=site, base=11)
    extra = dict(recs[-1])
    extra["accession"] = RESERVED_ACCESSION_BASE + 11 + 6
    extra["gt_label"] = None
    extra["in_coverage"] = True
    extra["missing_field"] = "gt_label"
    extra["findings"] = _baseline_findings({BINARY_DESIGNATED_FINDING: 5.0})
    recs.append(extra)
    return recs


def binary_fixture_no_positive_gt(site: str = SITES[0]) -> list[dict]:
    """Six eligible records with every GT positive removed (all GT=0).

    Sensitivity must therefore be null (no positives), never zero.
    """
    gts = [0, 0, 0, 0, 0, 0]
    preds = [1, 1, 0, 1, 0, 0]
    return _binary_inmemory(gts, preds, site=site, base=21)


def three_class_fixture(site: str = SITES[0]) -> list[dict]:
    """Six records over classes ['A','B','C']; GT [A,A,B,B,C,C], pred [A,B,B,C,C,A]."""
    gts = ["A", "A", "B", "B", "C", "C"]
    preds = ["A", "B", "B", "C", "C", "A"]
    recs = []
    for i, (gt, pred) in enumerate(zip(gts, preds)):
        recs.append({
            "accession": RESERVED_ACCESSION_BASE + 31 + i,
            "gt_label": None,
            "pred_label": None,
            "gt_class": gt,
            "pred_class": pred,
            "classes": list(CLASS_ORDER),
            "site": site,
            "procedure_start_date": "2026-08-20T09:00:00+00:00",
            "duration_seconds": 300.0,
            "findings": _baseline_findings({
                THREECLASS_DESIGNATED_FINDING: CLASS_BANDS[gt],
            }),
            "in_coverage": True,
            "missing_field": None,
        })
    return recs


# Reference value used by timing so downstream code can present 300s as 5 min.
TIMING_REFERENCE_SECONDS = 300.0
# Documented negative sentinel marking an invalid duration measurement.
INVALID_DURATION_SENTINEL = -1.0


def timing_fixture(site: str = SITES[0]) -> list[dict]:
    """Synthetic duration rows covering every timing edge case, seeded by FIXED_SEED.

    Covers: a normal spread, a single-value case, a MISSING (None) case, an
    INVALID (negative sentinel) case, an OUTLIER (Tukey 1.5*IQR whisker) case,
    and includes the reference value 300.0 (= 5 minutes).
    """
    rng = _rng(101)
    recs = []

    def add(index, ttd, e2e, note):
        recs.append({
            "accession": RESERVED_ACCESSION_BASE + 41 + index,
            "gt_label": 1,
            "pred_label": 1,
            "gt_class": None,
            "pred_class": None,
            "classes": [],
            "site": site,
            "procedure_start_date": "2026-08-22T09:00:00+00:00",
            "duration_seconds": e2e,
            "ttd_seconds": ttd,
            "findings": _baseline_findings(),
            "in_coverage": True,
            "missing_field": note,
        })

    # normal spread (seeded), plus the fixed reference 300.0 s
    for i in range(4):
        base = rng.uniform(120.0, 480.0)
        add(i, round(base, 2), round(base + 60.0, 2), None)
    add(4, TIMING_REFERENCE_SECONDS, TIMING_REFERENCE_SECONDS, "reference_300")
    # single-value case (all equal -> IQR = 0, no whiskers)
    for i in (5, 6, 7):
        add(i, 210.0, 210.0, "single_value")
    # missing (None) case
    add(8, None, None, "missing")
    # invalid (negative sentinel) case
    add(9, INVALID_DURATION_SENTINEL, INVALID_DURATION_SENTINEL, "invalid")
    # outlier suitable for a 1.5*IQR Tukey whisker
    add(10, 54000.0, 61000.0, "outlier")
    return recs


def missing_field_fixture(site: str = SITES[0]) -> list[dict]:
    """Rows each missing one required field, documented via ``missing_field``.

    (a) missing ground-truth, (b) one constituent finding score None (require-all
    ineligible), (c) missing duration value.
    """
    base = 61
    recs = []
    # (a) missing ground truth
    recs.append({
        "accession": RESERVED_ACCESSION_BASE + base + 0,
        "gt_label": None,
        "pred_label": 1,
        "gt_class": None, "pred_class": None, "classes": [],
        "site": site,
        "procedure_start_date": "2026-08-24T09:00:00+00:00",
        "duration_seconds": 300.0,
        "findings": _baseline_findings({BINARY_DESIGNATED_FINDING: 20.0}),
        "in_coverage": True,
        "missing_field": "gt_label",
    })
    # (b) constituent finding score None (require-all ineligible)
    findings = _baseline_findings()
    findings[BINARY_DESIGNATED_FINDING] = None
    recs.append({
        "accession": RESERVED_ACCESSION_BASE + base + 1,
        "gt_label": 1,
        "pred_label": 1,
        "gt_class": None, "pred_class": None, "classes": [],
        "site": site,
        "procedure_start_date": "2026-08-24T09:10:00+00:00",
        "duration_seconds": 300.0,
        "findings": findings,
        "in_coverage": True,
        "missing_field": f"findings.{BINARY_DESIGNATED_FINDING}",
    })
    # (c) missing duration value
    recs.append({
        "accession": RESERVED_ACCESSION_BASE + base + 2,
        "gt_label": 0,
        "pred_label": 0,
        "gt_class": None, "pred_class": None, "classes": [],
        "site": site,
        "procedure_start_date": "2026-08-24T09:20:00+00:00",
        "duration_seconds": None,
        "ttd_seconds": None,
        "findings": _baseline_findings(),
        "in_coverage": True,
        "missing_field": "duration_seconds",
    })
    return recs


def older_subgroup_fixture(site: str = SITES[0]) -> list[dict]:
    """Rows whose ``procedure_start_date`` layout fixes the cohort anchor D.

    Layout (in-coverage, required-complete rows only advance D):
      * latest COMPLETE event date -> D = 2026-09-01  (anchor)
      * older subgroup reaches only through 2026-08-28
      * a widget's required fields are complete only through 2026-08-30
      * a NEWER row (2026-09-10) whose required fields are INCOMPLETE so it
        must NOT advance D.
    All dates are inside the synthetic window 2025-01-01 .. 2026-09-15.
    """
    def rec(index, date, complete, widget_complete):
        return {
            "accession": RESERVED_ACCESSION_BASE + 61 + index,
            "gt_label": 1 if complete else None,
            "pred_label": 1,
            "gt_class": None, "pred_class": None, "classes": list(CLASS_ORDER),
            "site": site,
            "procedure_start_date": _iso(_aware(date)),
            "duration_seconds": 300.0 if widget_complete else None,
            "findings": _baseline_findings(),
            "in_coverage": True,
            "complete": complete,
            "widget_required_complete": widget_complete,
            "missing_field": None if complete else "gt_label",
        }

    recs = [
        rec(0, datetime(2026, 9, 1), True, True),    # anchor D
        rec(1, datetime(2026, 8, 28), True, True),   # older subgroup last
        rec(2, datetime(2026, 8, 30), True, True),   # widget-complete boundary
        rec(3, datetime(2026, 8, 20), True, True),   # older subgroup interior
        rec(4, datetime(2026, 9, 10), False, False), # newer but incomplete -> no advance
    ]
    return recs


# --------------------------------------------------------------------------- #
# (B) DB-row builders -- CREATE rows via the ORM inside the test database
# --------------------------------------------------------------------------- #
def _save(rows: list[dict]) -> list[CXRStudy]:
    """Assert synthetic-only on every identifier field, then bulk_create.

    Each row dict uses *model field names*; expanding ``findings`` into the
    concrete score columns first. The synthetic-only check runs on the
    constructed (unsaved) ``CXRStudy`` instances so it validates ``accession_no``
    and ``workplace`` via the model-attribute branch of _assert_synthetic_only.
    """
    ensure_test_database()
    studies = []
    for r in rows:
        findings = r.pop("findings", None) or {}
        for name in ALL_FINDINGS:
            r.setdefault(name, findings.get(name, 5.0))
        study = CXRStudy(**r)
        _assert_synthetic_only(study)  # validates accession_no + identifier text
        studies.append(study)
    CXRStudy.objects.bulk_create(studies)
    return studies


def _binary_rows(index_base, site, gts, preds, gt_field="gt_manual") -> list[dict]:
    rows = []
    for offset, (gt, pred) in enumerate(zip(gts, preds)):
        kwargs = _synthetic_identity(index_base + offset)
        kwargs["workplace"] = site
        kwargs["instances"] = 1 + offset
        kwargs["procedure_start_date"] = _aware(datetime(2026, 8, 15) + timedelta(days=offset))
        findings = _baseline_findings({
            BINARY_DESIGNATED_FINDING: 20.0 if pred == 1 else 5.0
        })
        kwargs[gt_field] = gt
        # lunit_binarised stored for convenience only; v2 RECOMPUTES it from the
        # designated finding under a strict >10 policy, and the fixture is made
        # consistent with that policy (score 20 -> 1, score 5 -> 0).
        kwargs["lunit_binarised"] = pred
        kwargs["findings"] = findings
        rows.append(kwargs)
    return rows


def binary_fixture_db(site: str = SITES[0], base: int = 1) -> list[CXRStudy]:
    """DB rows for the binary comparison case (see :func:`binary_fixture`)."""
    rows = _binary_rows(base, site,
                        [1, 1, 1, 0, 0, 0], [1, 1, 0, 1, 0, 0])
    return _save(rows)


def binary_fixture_with_missing_gt_db(site: str = SITES[0], base: int = 11) -> list[CXRStudy]:
    """DB rows: six eligible + one in-coverage row with gt_manual=None."""
    rows = _binary_rows(base, site,
                        [1, 1, 1, 0, 0, 0, 0], [1, 1, 0, 1, 0, 0, 1])
    rows[-1]["gt_manual"] = None  # in coverage but excluded (no ground truth)
    return _save(rows)


def binary_fixture_no_positive_gt_db(site: str = SITES[1], base: int = 21) -> list[CXRStudy]:
    """DB rows: all GT positives removed (sensitivity must be null)."""
    rows = _binary_rows(base, site,
                        [0, 0, 0, 0, 0, 0], [1, 1, 0, 1, 0, 0])
    return _save(rows)


def three_class_fixture_db(site: str = SITES[0], base: int = 31) -> list[CXRStudy]:
    """DB rows for the 3-class case; class encoded via the designated band.

    Mapping: consolidation score < 10 -> "A", 10..30 -> "B", > 30 -> "C"
    (consistent with the strict >10 binary threshold). See :data:`CLASS_BANDS`.
    """
    gts = ["A", "A", "B", "B", "C", "C"]
    preds = ["A", "B", "B", "C", "C", "A"]
    rows = []
    for offset, (gt, pred) in enumerate(zip(gts, preds)):
        kwargs = _synthetic_identity(base + offset)
        kwargs["workplace"] = site
        kwargs["instances"] = 1 + offset
        kwargs["procedure_start_date"] = _aware(datetime(2026, 8, 20) + timedelta(days=offset))
        kwargs["findings"] = _baseline_findings({
            THREECLASS_DESIGNATED_FINDING: CLASS_BANDS[gt],
            "nodule": CLASS_BANDS[pred],  # second designated finding for pred side
        })
        kwargs["gt_manual"] = {"A": 0, "B": 1, "C": 1}[gt]
        kwargs["lunit_binarised"] = {"A": 0, "B": 1, "C": 1}[pred]
        rows.append(kwargs)
    return _save(rows)


def timing_fixture_db(site: str = SITES[0], base: int = 41) -> list[CXRStudy]:
    """DB rows mirroring :func:`timing_fixture`'s edge cases onto duration fields."""
    inmem = timing_fixture(site=site)
    # base=41 in-memory uses 41; shift DB base to keep distinct accessions.
    rows = []
    for offset, r in enumerate(inmem):
        kwargs = _synthetic_identity(base + offset)
        kwargs["workplace"] = site
        kwargs["instances"] = 1 + offset
        kwargs["procedure_start_date"] = _aware(datetime(2026, 8, 22) + timedelta(days=offset))
        kwargs["time_to_clinical_decision_seconds"] = r.get("ttd_seconds")
        kwargs["time_end_to_end_seconds"] = r.get("duration_seconds")
        kwargs["gt_manual"] = 1
        kwargs["lunit_binarised"] = 1
        kwargs["findings"] = _baseline_findings()
        rows.append(kwargs)
    return _save(rows)


def missing_field_fixture_db(site: str = SITES[0], base: int = 61) -> list[CXRStudy]:
    """DB rows: (a) gt None, (b) designated finding None, (c) durations None."""
    rows = []
    # (a) missing ground truth
    a = _synthetic_identity(base + 0)
    a.update({"workplace": site, "instances": 1,
              "procedure_start_date": _aware(datetime(2026, 8, 24, 9, 0)),
              "gt_manual": None, "lunit_binarised": 1,
              "findings": _baseline_findings({BINARY_DESIGNATED_FINDING: 20.0})})
    rows.append(a)
    # (b) constituent finding None (require-all ineligible)
    b = _synthetic_identity(base + 1)
    b.update({"workplace": site, "instances": 2,
              "procedure_start_date": _aware(datetime(2026, 8, 24, 9, 10)),
              "gt_manual": 1, "lunit_binarised": 1,
              "findings": _baseline_findings({BINARY_DESIGNATED_FINDING: None})})
    rows.append(b)
    # (c) missing duration value
    c = _synthetic_identity(base + 2)
    c.update({"workplace": site, "instances": 3,
              "procedure_start_date": _aware(datetime(2026, 8, 24, 9, 20)),
              "gt_manual": 0, "lunit_binarised": 0,
              "time_to_clinical_decision_seconds": None,
              "time_end_to_end_seconds": None,
              "findings": _baseline_findings()})
    rows.append(c)
    return _save(rows)


def older_subgroup_fixture_db(site: str = SITES[1], base: int = 71) -> list[CXRStudy]:
    """DB rows laying out the cohort anchor D (see :func:`older_subgroup_fixture`)."""
    dates = [
        datetime(2026, 9, 1), datetime(2026, 8, 28), datetime(2026, 8, 30),
        datetime(2026, 8, 20), datetime(2026, 9, 10),
    ]
    complete = [True, True, True, True, False]  # last is newer but incomplete
    rows = []
    for offset, (date, comp) in enumerate(zip(dates, complete)):
        kwargs = _synthetic_identity(base + offset)
        kwargs["workplace"] = site
        kwargs["instances"] = 1 + offset
        kwargs["procedure_start_date"] = _aware(date)
        kwargs["gt_manual"] = 1 if comp else None  # incomplete -> missing GT
        kwargs["lunit_binarised"] = 1 if comp else 0
        kwargs["time_end_to_end_seconds"] = 300.0 if comp else None
        kwargs["time_to_clinical_decision_seconds"] = 300.0 if comp else None
        kwargs["findings"] = _baseline_findings()
        rows.append(kwargs)
    return _save(rows)


def create_default_population(base: int = 91) -> list[CXRStudy]:
    """Lay down a small deterministic mix across the two sites for DB tests.

    A handful per site drawn from the families above; every identifier/text field
    is checked with :func:`assert_no_real_identifiers` before saving.
    """
    ensure_test_database()
    rows = []
    # 3 per site from the binary case
    rows += _binary_rows(base, SITES[0],
                         [1, 1, 0], [1, 0, 1])
    rows += _binary_rows(base + 3, SITES[1],
                         [1, 0, 0], [1, 1, 0])
    # explicit pre-save identifier sweep (per hard rule); _save also re-checks.
    for r in rows:
        assert_no_real_identifiers(r["accession_no"])
        for field in IDENTIFIER_TEXT_FIELDS:
            assert_no_real_identifiers(r.get(field))
    return _save(rows)

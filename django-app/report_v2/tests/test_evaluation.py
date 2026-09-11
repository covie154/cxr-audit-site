# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Database-free coverage for the report-v2 widget evaluator and the request contract.

Every test here pins exactly one frozen invariant of :func:`report_v2.evaluation.evaluate` /
:class:`report_v2.evaluation.RequestContract` and asserts it *directly*:

* two different measurements over the *same* rows come to different captured anchors ``D``;
* an older (filtered) subgroup keeps the global anchor ``D`` preserved while its own
  ``subgroup_latest_date`` is exposed and is strictly earlier than ``D``;
* the counting ledger reconciles -- ``matching == eligible + excluded_incomplete`` with no other
  drop, and the per-reason exclusion map is a mutually exclusive partition whose values sum to
  ``total_dropped`` (every dropped row carries exactly one reason);
* the four rejection paths raise their exact typed errors -- unknown widget id, a disallowed
  override (raised at *construction*, before evaluation), an unknown measurement id and an
  unknown policy reference;
* a paired widget's :class:`~report_v2.results.CommonPopulation` has *equal* ``n_complete`` on
  both arms because both are derived from the same shared ``complete_rows`` filter;
* the hard bounds fire -- raw rows on an aggregate widget -> ``NonAggregateRowsError``, group
  cardinality over the cap -> ``GroupCardinalityError``, page size over the cap ->
  ``PaginationBoundError``;
* every published payload's ``to_dict()`` carries the four metadata groups non-empty, and the
  guard is *real* -- building a :class:`~report_v2.results.ResultPayload` without one group raises
  ``PayloadContractError``.

The module under test is pure: no ORM / database import is reachable through it (asserted). All
rows are synthetic, built through the reserved non-clinical accession block from
:mod:`report_v2.tests.factories` (``FIXED_SEED`` / ``RESERVED_ACCESSION_BASE``) and vetted by
:func:`assert_no_real_identifiers`. The whole suite is :class:`django.test.SimpleTestCase`.
"""

from __future__ import annotations

import inspect
from datetime import date

from django.test import SimpleTestCase

from report_v2 import evaluation as evaluation_module
from report_v2 import results as results_module
from report_v2.evaluation import (
    DisallowedOverrideError,
    EvaluationError,
    GroupCardinalityError,
    InvalidWidgetReferenceError,
    NonAggregateRowsError,
    PaginationBoundError,
    PUBLISHED_WIDGETS,
    RequestContract,
    UnknownMeasurementError,
    UnknownPolicyError,
    WidgetSpec,
    evaluate,
)
from report_v2.measurements import complete_rows
from report_v2.results import (
    CommonPopulation,
    CountAccounting,
    DateMetadata,
    PayloadContractError,
    ResultPayload,
    SourceMetadata,
    VersionMetadata,
)
from report_v2.tests.factories import (
    FIXED_SEED,
    RESERVED_ACCESSION_BASE,
    assert_no_real_identifiers,
)


# ---------------------------------------------------------------------------
# Synthetic, database-free fixtures. A tiny duck-typed project stands in for a
# real ProjectDefinition; rows are plain Mappings over the reserved accession
# block so nothing near a clinical identifier is ever constructed.
# ---------------------------------------------------------------------------
class _StubProject:
    project_id = "synth-eval-proj"
    timezone = "Asia/Singapore"
    policies: dict = {}


def _acc(index: int) -> int:
    # Stay *inside* the reserved non-clinical block [base, base + span); the offset is
    # derived deterministically from the frozen suite seed so accessions never drift.
    return RESERVED_ACCESSION_BASE + (FIXED_SEED % 1_000) + index


def _row(index, when, *, gt=1, pred=1, dur=300.0, site="A", category="X",
         eligible=True, **extra):
    row = {
        "accession": _acc(index),
        "event_date": when,
        "gt_label": gt,
        "pred_label": pred,
        "duration_seconds": dur,
        "site": site,
        "category": category,
        "eligible": eligible,
    }
    row.update(extra)
    return row


class RequestContractAndEvaluationTests(SimpleTestCase):
    """One named test per frozen Task-10 invariant."""

    # -- helpers -----------------------------------------------------------
    def _run(self, rows, widget_id, **kw):
        request = kw.pop("request", None) or RequestContract(widget_id=widget_id)
        payload = evaluate(
            request=request,
            project=_StubProject(),
            catalog=kw.pop("catalog", None),
            rows=rows,
            measurement=kw.pop("measurement", None),
            policy=kw.pop("policy", None),
            ci_registry=kw.pop("ci_registry", None),
            grouping=kw.pop("grouping", None),
            buckets=kw.pop("buckets", None),
            page_size=kw.pop("page_size", None),
            max_groups=kw.pop("max_groups", 1_000),
            published_widget_ids=kw.pop("published_widget_ids", evaluation_module.PUBLISHED_WIDGET_IDS),
            widgets=kw.pop("widgets", PUBLISHED_WIDGETS),
            include_rows=kw.pop("include_rows", False),
        )
        assert not kw, f"unexpected kwargs {sorted(kw)}"
        assert_no_real_identifiers(rows)
        return payload

    # -- 1. different measurements -> different captured anchors -----------
    def test_different_measurements_yield_different_anchors(self):
        """binary's newest-complete date != duration's: the newest row is complete for only one."""
        rows = [
            _row(1, date(2026, 9, 1), gt=1, pred=1, dur=200.0),
            _row(2, date(2026, 9, 2), gt=0, pred=0, dur=400.0),
            # newest row: missing ground truth -> incomplete for binary, complete for duration
            _row(3, date(2026, 9, 10), gt=None, pred=1, dur=500.0),
        ]
        binary = self._run(rows, "widget.binary")
        duration = self._run(rows, "widget.duration")

        self.assertEqual(binary.dates.anchor_date, "2026-09-02")
        self.assertEqual(duration.dates.anchor_date, "2026-09-10")
        self.assertNotEqual(binary.dates.anchor_date, duration.dates.anchor_date)

    # -- 2. preserved D + subgroup_latest_date earlier than D --------------
    def test_preserved_anchor_with_older_subgroup_latest_date(self):
        """The global anchor D survives a subgroup narrowing; the subgroup's own latest is exposed."""
        rows = [
            _row(1, date(2026, 9, 20), site="B", gt=1, pred=1),  # global max -> D
            _row(2, date(2026, 9, 10), site="A", gt=1, pred=1),  # subgroup (A) max
            _row(3, date(2026, 9, 5), site="A", gt=0, pred=0),
        ]
        request = RequestContract(
            widget_id="widget.binary", filter_overrides={"site": "A"}
        )
        payload = self._run(rows, "widget.binary", request=request)

        # The window still ends at the *global* captured anchor D = 2026-09-20.
        self.assertEqual(payload.dates.anchor_date, "2026-09-20")
        self.assertEqual(payload.dates.window_end, "2026-09-20")
        # The subgroup's real latest eligible date is exposed and is strictly before D.
        self.assertEqual(payload.dates.subgroup_latest_date, "2026-09-10")
        self.assertLess(payload.dates.subgroup_latest_date, payload.dates.anchor_date)

    # -- 3a. matching == eligible + excluded_incomplete (no other drop) ----
    def test_matching_equals_eligible_plus_excluded_incomplete(self):
        # Anchor D is the newest COMPLETE eligible date (09-04). The one incomplete row sits
        # *older* than D (09-01) so it stays inside the window -> it is counted as `matching`
        # and only then dropped by the completeness pass. No other reason fires.
        rows = [
            _row(1, date(2026, 9, 1), gt=None, pred=1),  # incomplete (no gt) -> missing_required
            _row(2, date(2026, 9, 2), gt=1, pred=1),     # eligible
            _row(3, date(2026, 9, 3), gt=0, pred=0),     # eligible
            _row(4, date(2026, 9, 4), gt=1, pred=0),     # eligible; newest complete -> D
        ]
        payload = self._run(rows, "widget.binary")
        c = payload.counts
        self.assertEqual(c.matching, c.eligible + c.excluded_incomplete)
        # No other drop happened, so incoming == matching.
        self.assertEqual(c.incoming, c.matching)
        self.assertEqual(c.excluded_by_reason["out_of_window"], 0)
        self.assertEqual(c.excluded_by_reason["filtered_out"], 0)
        self.assertEqual(c.excluded_by_reason["foreign_identifier"], 0)

    # -- 3b. mutually exclusive single-reason partition -------------------
    def test_exclusion_partition_is_mutually_exclusive_and_sums_to_dropped(self):
        rows = [
            _row(1, date(2026, 9, 1), gt=1, pred=1),                 # eligible
            _row(2, date(2026, 9, 2), gt=None, pred=1),               # missing_required
            _row(3, date(2019, 1, 1), gt=1, pred=1),                  # out_of_window (far)
            _row(4, date(2026, 9, 2), site="Z", gt=1, pred=1),       # filtered_out (site!=A)
            _row(5, date(2026, 9, 2), cross_project=True, gt=1, pred=1),  # foreign_identifier
        ]
        request = RequestContract(
            widget_id="widget.binary", filter_overrides={"site": "A"}
        )
        payload = self._run(rows, "widget.binary", request=request)
        c = payload.counts
        partition_sum = sum(c.excluded_by_reason.values())
        self.assertEqual(partition_sum, c.total_dropped)
        # every dropped row landed in exactly one bucket: bucket each expected reason is present
        self.assertEqual(c.excluded_by_reason["missing_required"], 1)
        self.assertEqual(c.excluded_by_reason["out_of_window"], 1)
        self.assertEqual(c.excluded_by_reason["filtered_out"], 1)
        self.assertEqual(c.excluded_by_reason["foreign_identifier"], 1)
        self.assertEqual(c.total_dropped, 4)
        self.assertGreaterEqual(c.matching, c.eligible + c.excluded_incomplete)

    # -- 4a. unknown widget id --------------------------------------------
    def test_unknown_widget_id_raises_invalid_reference(self):
        with self.assertRaises(InvalidWidgetReferenceError):
            self._run([_row(1, date(2026, 9, 1))], "widget.does-not-exist")

    # -- 4b. disallowed override rejected before evaluation ---------------
    def test_disallowed_override_raises_before_evaluation(self):
        for field, value in (
            ("measurement_override", "duration_summary"),
            ("policy_version_override", 9),
            ("ci_override", {"metric": "wilson"}),
            ("layout_override", {"columns": 4}),
        ):
            with self.subTest(field=field):
                with self.assertRaises(DisallowedOverrideError):
                    RequestContract(widget_id="widget.binary", **{field: value})

    # -- 4c. unknown measurement id ---------------------------------------
    def test_unknown_measurement_raises_typed_error(self):
        bogus = {"widget.bogus": WidgetSpec(
            widget_id="widget.bogus", display="Bogus",
            measurement="not_a_real_measurement", aggregate=True,
        )}
        with self.assertRaises(UnknownMeasurementError):
            self._run(
                [_row(1, date(2026, 9, 1))], "widget.bogus",
                widgets=bogus, published_widget_ids=frozenset({"widget.bogus"}),
            )

    # -- 4d. unknown policy reference -----------------------------------
    def test_unknown_policy_raises_typed_error(self):
        with self.assertRaises(UnknownPolicyError):
            self._run([_row(1, date(2026, 9, 1))], "widget.binary", policy="ghost-policy@7")

    # -- 5. paired widget shares one complete population ------------------
    def test_paired_widget_common_population_equal_on_both_sides(self):
        rows = [
            _row(1, date(2026, 9, 1), gt=1, pred=1),
            _row(2, date(2026, 9, 2), gt=0, pred=1),
            _row(3, date(2026, 9, 3), gt=1, pred=0),
            _row(4, date(2026, 9, 4), gt=None, pred=1),  # incomplete -> dropped from complete_rows
            _row(5, date(2026, 9, 5), gt=1, pred=99),    # out-of-vocabulary pred -> dropped
        ]
        payload = self._run(rows, "widget.kappa")
        common = payload.common_population
        self.assertIsInstance(common, CommonPopulation)
        self.assertEqual(common.sides["reference"], common.sides["prediction"])
        self.assertEqual(common.sides["reference"], common.n_complete)
        self.assertEqual(common.sides["prediction"], common.n_complete)
        # independently reproduce the *shared* filter and pin the exact number.
        shared = complete_rows(
            [r["gt_label"] for r in rows], [r["pred_label"] for r in rows]
        )
        self.assertEqual(common.n_complete, shared.complete)

    # -- 6a. aggregate widget may not publish raw rows ------------------
    def test_aggregate_widget_raw_rows_rejected(self):
        with self.assertRaises(NonAggregateRowsError):
            self._run(
                [_row(1, date(2026, 9, 1))], "widget.binary", include_rows=True
            )

    # -- 6b. group cardinality bound ------------------------------------
    def test_group_cardinality_bound(self):
        rows = [
            _row(1, date(2026, 9, 1), site="A"),
            _row(2, date(2026, 9, 2), site="B"),
            _row(3, date(2026, 9, 3), site="C"),
        ]
        with self.assertRaises(GroupCardinalityError):
            self._run(rows, "widget.prevalence", grouping=("site",), max_groups=2)

    # -- 6c. pagination bound -------------------------------------------
    def test_pagination_bound(self):
        with self.assertRaises(PaginationBoundError):
            self._run(
                [_row(1, date(2026, 9, 1))], "widget.cases",
                page_size=evaluation_module.MAX_PAGE_SIZE + 1,
            )

    # -- 7a. every published payload carries the four metadata groups ---
    def test_to_dict_carries_all_four_metadata_groups(self):
        payload = self._run(
            [
                _row(1, date(2026, 9, 1), gt=1, pred=1),
                _row(2, date(2026, 9, 2), gt=0, pred=0),
            ],
            "widget.binary",
        )
        out = payload.to_dict()
        for group in ("sources", "versions", "dates", "units"):
            self.assertIn(group, out)
            self.assertTrue(out[group], f"{group} must be non-empty")
        self.assertTrue(out["sources"]["modules"])
        self.assertTrue(out["units"])

    # -- 7b. the publish gate is real -----------------------------------
    def test_payload_contract_guard_is_real(self):
        def build(**override):
            base = dict(
                widget_id="widget.binary", display="Binary", aggregate=True,
                aggregates={"accuracy": {"value": 0.5}},
                rows=(),
                counts=CountAccounting(
                    incoming=2, matching=2, eligible=2, excluded_incomplete=0,
                    excluded_by_reason={},
                ),
                sources=SourceMetadata(
                    modules=("report_v2.measurements",), project_id="synth-eval-proj"
                ),
                versions=VersionMetadata(
                    policy_version=None, policy_ref=None, measurement_id="binary_classification"
                ),
                dates=DateMetadata(
                    anchor_date="2026-09-02", window_start="2026-08-03",
                    window_end="2026-09-02", timezone="Asia/Singapore",
                ),
                units={"accuracy": "rate[0,1]"},
            )
            base.update(override)
            return ResultPayload(**base)

        # Baseline is well-formed...
        self.assertTrue(build().to_dict())
        # ...and dropping any single required group trips the guard.
        for missing in ("sources", "versions", "dates", "units"):
            with self.subTest(missing=missing):
                with self.assertRaises(PayloadContractError):
                    build(**{missing: None})

    # -- 8. the orchestrator stays pure -----------------------------------
    def test_evaluation_module_is_pure(self):
        """No ORM / database handle is reachable from the evaluation module's own surface."""
        module_globals = {
            name: value
            for name, value in vars(evaluation_module).items()
            if not name.startswith("__")
        }
        for name, value in module_globals.items():
            module = getattr(value, "__module__", "") or ""
            self.assertNotIn("django.db", module, f"{name} leaks an ORM module")
            self.assertNotIn("django.orm", module, f"{name} leaks an ORM module")
        source = inspect.getsource(evaluation_module)
        for forbidden in (
            "from django.db", "import django.db", "from django.db import",
            "django.db.models", "django.db.connection", ".objects.", "connection.cursor",
        ):
            self.assertNotIn(forbidden, source)
        # The module never imports Django at all -- it is pure value computation.
        self.assertNotIn("import django", source)

    # -- 9. the suite is seed-pinned & reserved-block only ----------------
    def test_synthetic_fixtures_use_reserved_block_and_seed(self):
        self.assertEqual(FIXED_SEED, 20260910)
        for index in range(1, 6):
            accession = _acc(index)
            self.assertGreaterEqual(accession, RESERVED_ACCESSION_BASE)
            self.assertLess(accession, RESERVED_ACCESSION_BASE + 1_000_000)
        # a fully built row survives the real-identifier guard untouched
        assert_no_real_identifiers([_row(1, date(2026, 9, 1))])

    # -- 10. the evaluator imports-and-calls, never reimplements ----------
    def test_calls_existing_modules_not_reimplemented(self):
        """evaluation delegates to projects/dates/measurements + results (named imports)."""
        source = inspect.getsource(evaluation_module)
        for callee in (
            "require_project_context",   # report_v2.projects
            "capture_anchor",            # report_v2.dates
            "resolve_request",            # report_v2.dates
            "bucket_range",               # report_v2.dates
            "complete_rows",              # report_v2.measurements (shared filter)
            "binary_classification_metrics",  # report_v2.measurements
            "cohen_kappa",                # report_v2.measurements
        ):
            self.assertIn(callee, source, f"{callee} must be imported/called, not reimplemented")

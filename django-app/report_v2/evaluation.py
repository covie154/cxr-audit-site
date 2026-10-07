# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Widget evaluation orchestrator and the frozen request contract for report-v2.

This module is the *orchestrator* of Task 10. It does **not** reimplement any of the
lower layers: it imports and *calls* the already-built, database-free building blocks --

* :mod:`report_v2.projects` (:func:`require_project_context`, ``CrossProjectReferenceError``,
  ``ProjectCatalogError``) for the locked project scope and the cross-project guard,
* :mod:`report_v2.dates` (:func:`capture_anchor`, :func:`resolve_request`,
  :func:`bucket_range`) for the captured anchor ``D``, the inclusive window and the buckets,
* :mod:`report_v2.measurements` (classification / agreement / descriptive / confidence entry
  points) for every reported statistic, the shared complete-row filter and the CI registry,
* :mod:`report_v2.results` for the frozen publication envelope.

The single entry point :func:`evaluate` runs a fixed, observable eight-step pipeline; the order
is part of the frozen contract and is reproduced verbatim in the :func:`evaluate` docstring and
in ``steps`` recorded on the returned payload's provenance:

1. **scope** -- resolve the project through the Task-04 registry guard; a *foreign* identifier
   reference propagates :class:`report_v2.projects.CrossProjectReferenceError` (never caught away).
2. **completeness** -- drop rows failing the measurement's required-column completeness, counting
   them as ``missing_required``. Together with the window / filter / foreign drops this forms a
   *mutually exclusive* partition of every dropped row (one reason per row; the per-reason counts
   sum to ``total_dropped``).
3. **D capture** -- :func:`capture_anchor` derives the anchor ``D`` as the latest *complete,
   eligible* date; a newer incomplete row does **not** advance ``D``. Different measurements
   therefore may legitimately yield different anchors, and the widget's own measurement is used.
4. **widget window** -- :func:`resolve_request` resolves the inclusive window ending at ``D``
   (a subgroup narrowing is reported as ``subgroup_latest_date`` / coverage only, never moves the
   window), buckets via :func:`bucket_range`.
5. **user filters** -- apply :attr:`RequestContract.filter_overrides`.
6. **eligible sample** -- the surviving rows; ``matching`` is counted *after* dates + filters but
   *before* the completeness drop, so ``matching == eligible + excluded_incomplete`` and the ledger
   reconciles (``matching >= eligible + excluded_incomplete`` and the four reasons sum to the drop).
7. **grouping / buckets** -- bounded group cardinality (over ``max_groups`` ->
   :class:`GroupCardinalityError`) and bounded pagination (``page_size`` over the cap ->
   :class:`PaginationBoundError``); an aggregate payload may never carry raw rows
   (:class:`NonAggregateRowsError`).
8. **measurement** -- dispatch through :mod:`report_v2.measurements`; an unknown measurement id ->
   :class:`UnknownMeasurementError`, an unknown policy -> :class:`UnknownPolicyError`. The four
   metadata groups (sources / versions / dates / units) are always populated non-empty so the
   :meth:`report_v2.results.ResultPayload.to_dict` publish gate is satisfied.

The module is pure: it imports no ORM and touches no database -- every row is passed in by the
caller and every row is a :class:`collections.abc.Mapping`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from math import isfinite as _isfinite
from typing import Any, Callable, Iterable, Optional, Sequence

from report_v2.projects import (
    CrossProjectReferenceError,
    ProjectCatalogError,
    ProjectRegistry,
    require_project_context,
)
from report_v2.dates import bucket_range, capture_anchor, resolve_request
from report_v2.measurements import (
    BinaryClassVocabulary,
    binary_classification_metrics,
    categorical_count,
    classification_summary as _classification_summary,
    cohen_kappa,
    complete_rows,
    confusion_matrix as _confusion_matrix,
    duration_summary,
    fn_fp_cases,
    label_count as _label_count_primitive,
    mcnemar,
    pairs_from_rows,
    record_count,
    require_proportion_ci,
    wilson_interval,
)
from report_v2.results import (
    CountAccounting,
    CommonPopulation,
    DateMetadata,
    EVALUATOR_NAME,
    ResultPayload,
    SCHEMA_VERSION,
    SourceMetadata,
    VersionMetadata,
)

# ---------------------------------------------------------------------------
# Module-level binary vocabulary reused by every label-stream handler.
# ---------------------------------------------------------------------------
_BINARY_VOCAB = BinaryClassVocabulary(positive_class=1, negative_class=0, label="binary")


# ---------------------------------------------------------------------------
# Typed error model. Every rejection this module raises descends from
# :class:`EvaluationError` so a caller can trap the whole surface with one except.
# ---------------------------------------------------------------------------


class EvaluationError(Exception):
    """Common base for every report-v2 widget-evaluation rejection."""


class InvalidWidgetReferenceError(EvaluationError):
    """The requested ``widget_id`` is not on the published-widget allow-list."""


class DisallowedOverrideError(EvaluationError):
    """A request attempted to override an immutable dimension (measurement / policy / CI / layout).

    Raised at :class:`RequestContract` construction -- i.e. *before* any evaluation runs.
    """


class UnknownMeasurementError(EvaluationError):
    """The widget's measurement id is outside the set this evaluator knows how to compute."""


class UnknownPolicyError(EvaluationError):
    """A requested policy reference is not registered on the addressed project.

    A genuinely *foreign* reference is not translated -- :class:`CrossProjectReferenceError`
    propagates instead; this error is only for a reference that is simply unknown locally.
    """


class NonAggregateRowsError(EvaluationError):
    """An aggregate widget attempted to publish raw, case-level rows."""


class GroupCardinalityError(EvaluationError):
    """The grouping produced more distinct groups than ``max_groups`` permits."""


class PaginationBoundError(EvaluationError):
    """A requested ``page_size`` exceeds the hard :data:`MAX_PAGE_SIZE` cap."""


# ---------------------------------------------------------------------------
# Bounded-pagination / cardinality caps (frozen module constants).
# ---------------------------------------------------------------------------
MAX_PAGE_SIZE = 500
DEFAULT_MAX_GROUPS = 1_000
DEFAULT_TIMEZONE = "Asia/Singapore"

#: The mutually exclusive exclusion vocabulary. A dropped row is attributed *exactly one*
#: of these reasons -- never more -- so the per-reason counts form a partition of the drop.
EXCLUSION_REASONS = frozenset(
    {"missing_required", "out_of_window", "foreign_identifier", "filtered_out"}
)


# ---------------------------------------------------------------------------
# Published widget catalogue. A widget is immutable and *declares* its measurement; a caller
# can never change that at request time (that would be a disallowed override).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WidgetSpec:
    """Immutable published definition of one report-v2 widget."""

    widget_id: str
    display: str
    measurement: str
    aggregate: bool
    paired: bool = False
    window: str = "D-30"
    filters: frozenset = frozenset()
    dimensions: frozenset = frozenset()


def _ws(widget_id, display, measurement, *, aggregate=True, paired=False,
        window="D-30", filters=(), dimensions=()) -> WidgetSpec:
    return WidgetSpec(
        widget_id=widget_id,
        display=display,
        measurement=measurement,
        aggregate=aggregate,
        paired=paired,
        window=window,
        filters=frozenset(filters),
        dimensions=frozenset(dimensions),
    )


#: The published widgets. The keys are the *only* widget ids ``evaluate`` accepts.
PUBLISHED_WIDGETS: dict[str, WidgetSpec] = {
    spec.widget_id: spec
    for spec in (
        _ws("widget.binary", "Binary classification", "binary_classification",
            filters=("site", "gt_label", "pred_label"), dimensions=("site",)),
        _ws("widget.prevalence", "Prevalence by site", "prevalence",
            filters=("site",), dimensions=("site",)),
        _ws("widget.duration", "Reporting duration", "duration_summary",
            filters=("site",), dimensions=("site",)),
        _ws("widget.category", "Category mix", "categorical_count",
            filters=("category",), dimensions=("category",)),
        _ws("widget.kappa", "Cohen's kappa", "agreement_kappa",
            paired=True, filters=("site",), dimensions=("site",)),
        _ws("widget.mcnemar", "McNemar test", "agreement_mcnemar",
            paired=True, filters=("site",), dimensions=("site",)),
        _ws("widget.fnfp", "FN / FP cases", "fn_fp_cases",
            paired=True, filters=("site",), dimensions=("site",)),
        _ws("widget.cases", "Case listing", "record_count",
            aggregate=False, filters=("site",), dimensions=("site",)),
    )
}

#: Frozen allow-list -- an unknown id is an :class:`InvalidWidgetReferenceError`.
PUBLISHED_WIDGET_IDS = frozenset(PUBLISHED_WIDGETS)

#: The measurement ids this evaluator knows how to compute -- an id outside this set is an
#: :class:`UnknownMeasurementError`.
SUPPORTED_MEASUREMENTS = frozenset(
    {
        "binary_classification",
        "prevalence",
        "duration_summary",
        "categorical_count",
        "agreement_kappa",
        "agreement_mcnemar",
        "fn_fp_cases",
        "record_count",
        "label_count",
        "accuracy",
        "sensitivity",
        "specificity",
        "balanced_accuracy",
        "classification_summary",
        "reference_agreement",
        "paired_reference_comparison",
        "false_negatives",
        "false_positives",
        "confusion_matrix",
    }
)

#: Required (non-null) columns a row must carry for a measurement to be *complete* for it.
#: The newest row may be missing these for one measurement while satisfying another -- which is
#: exactly how different measurements come to different anchors.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "binary_classification": ("gt_label", "pred_label"),
    "agreement_kappa": ("gt_label", "pred_label"),
    "agreement_mcnemar": ("gt_label", "pred_label"),
    "fn_fp_cases": ("gt_label", "pred_label"),
    "duration_summary": ("duration_seconds",),
    "categorical_count": ("category",),
    "prevalence": (),
    "record_count": (),
    "label_count": (),
    "accuracy": ("gt_label", "pred_label"),
    "sensitivity": ("gt_label", "pred_label"),
    "specificity": ("gt_label", "pred_label"),
    "balanced_accuracy": ("gt_label", "pred_label"),
    "classification_summary": ("gt_label", "pred_label"),
    "reference_agreement": ("gt_label", "pred_label"),
    "paired_reference_comparison": ("gt_label", "pred_label"),
    "false_negatives": ("gt_label", "pred_label"),
    "false_positives": ("gt_label", "pred_label"),
    "confusion_matrix": ("gt_label", "pred_label"),
}

#: Per-measurement human units for the ``units`` metadata group (always non-empty).
MEASUREMENT_UNITS: dict[str, dict[str, str]] = {
    "binary_classification": {
        "sensitivity": "rate[0,1]",
        "specificity": "rate[0,1]",
        "positive_predictive_value": "rate[0,1]",
        "counts": "count",
    },
    "agreement_kappa": {"kappa": "index[-1,1]", "n": "count"},
    "agreement_mcnemar": {"p_value": "probability[0,1]", "discordant": "count"},
    "fn_fp_cases": {"false_negative": "count", "false_positive": "count"},
    "duration_summary": {"mean": "seconds", "median": "seconds", "n": "count"},
    "prevalence": {"count": "count"},
    "categorical_count": {"count": "count"},
    "record_count": {"n": "count"},
    "label_count": {"label_count": "count", "n": "count"},
    "accuracy": {"accuracy": "rate[0,1]", "n": "count"},
    "sensitivity": {"sensitivity": "rate[0,1]", "n": "count"},
    "specificity": {"specificity": "rate[0,1]", "n": "count"},
    "balanced_accuracy": {"balanced_accuracy": "rate[0,1]", "n": "count"},
    "classification_summary": {
        "accuracy": "rate[0,1]", "balanced_accuracy": "rate[0,1]",
        "sensitivity": "rate[0,1]", "specificity": "rate[0,1]",
        "ppv": "rate[0,1]", "npv": "rate[0,1]",
        "n": "count", "tp": "count", "tn": "count", "fp": "count", "fn": "count",
    },
    "reference_agreement": {
        "agreement": "rate[0,1]", "kappa": "index[-1,1]", "n": "count",
    },
    "paired_reference_comparison": {
        "p_value": "probability[0,1]", "statistic": "index[0,\u221e)",
        "b": "count", "c": "count", "n": "count",
    },
    "false_negatives": {
        "false_negatives": "count", "n_total": "count",
        "n_complete": "count", "excluded_incomplete": "count",
    },
    "false_positives": {
        "false_positives": "count", "n_total": "count",
        "n_complete": "count", "excluded_incomplete": "count",
    },
    "confusion_matrix": {
        "cell": "count", "row_total": "count", "column_total": "count",
        "n": "count", "accuracy": "rate[0,1]",
    },
}


# ---------------------------------------------------------------------------
# The frozen request contract. Only *date*, *filter* and a *single comparison* are permitted
# overrides; measurement-selection / policy-version / CI-config / layout are structurally
# forbidden and are rejected at construction time (before any evaluation).
# ---------------------------------------------------------------------------
#: Fields whose mere presence (non-``None``) is a disallowed override.
_DISALLOWED_OVERRIDE_FIELDS = (
    "measurement_override",
    "policy_version_override",
    "ci_override",
    "layout_override",
)


@dataclass(frozen=True)
class RequestContract:
    """The only request shape :func:`evaluate` accepts.

    Permitted overrides: :attr:`date_override`, :attr:`filter_overrides` and a single
    :attr:`comparison` selector. Any attempt to carry a measurement-selection / policy-version /
    CI-config / layout override is a :class:`DisallowedOverrideError`, raised from
    :meth:`__post_init__` -- i.e. before evaluation, so no data is ever read for a bad request.
    """

    widget_id: str
    date_override: Optional[object] = None
    filter_overrides: Mapping = field(default_factory=dict)
    comparison: Optional[str] = None

    # These exist purely so an override attempt is representable *and* rejectable up-front; a
    # legitimate request always leaves them ``None``.
    measurement_override: Optional[str] = None
    policy_version_override: Optional[object] = None
    ci_override: Optional[object] = None
    layout_override: Optional[object] = None

    def __post_init__(self) -> None:
        for field_name in _DISALLOWED_OVERRIDE_FIELDS:
            if getattr(self, field_name) is not None:
                raise DisallowedOverrideError(
                    f"{field_name} is not an overridable dimension of a published widget; "
                    "only date, filter and a single comparison selector may be overridden"
                )
        if not isinstance(self.widget_id, str) or not self.widget_id.strip():
            raise InvalidWidgetReferenceError(
                f"widget_id must be a non-empty string; got {self.widget_id!r}"
            )
        if self.filter_overrides is None:
            object.__setattr__(self, "filter_overrides", {})
        elif not isinstance(self.filter_overrides, Mapping):
            raise DisallowedOverrideError(
                "filter_overrides must be a Mapping of field -> expected value"
            )


# ---------------------------------------------------------------------------
# Small, total helpers (no exceptions escape to callers except the typed ones above).
# ---------------------------------------------------------------------------
def _snapshot(value: Any) -> Any:
    """Best-effort JSON-friendly snapshot of a measurement result object."""
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        try:
            return as_dict()
        except Exception:  # pragma: no cover - defensive
            pass
    if is_dataclass(value) and not isinstance(value, type):
        return asdict(value)
    if isinstance(value, Mapping):
        return {key: _snapshot(item) for key, item in value.items()}
    return value


def _to_date(value: object) -> date | None:
    """Coerce a row's date field to a plain :class:`datetime.date`, or ``None`` if unusable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1]
        head = text[:10]
        try:
            return date.fromisoformat(head)
        except ValueError:
            try:
                return datetime.fromisoformat(text).date()
            except (ValueError, TypeError):
                return None
    return None


def _row_date(row: Mapping) -> date | None:
    for key in ("event_date", "procedure_start_date", "created_date"):
        if key in row:
            coerced = _to_date(row[key])
            if coerced is not None:
                return coerced
    return None


def _is_missing(value: object) -> bool:
    return value is None


def _row_complete(row: Mapping, measurement: str) -> bool:
    """A row is complete for ``measurement`` when every required column is present and non-null."""
    if not bool(row.get("complete", True)):
        return False
    if row.get("missing_field") not in (None, ""):
        return False
    for column in REQUIRED_COLUMNS.get(measurement, ()):
        if _is_missing(row.get(column)):
            return False
    return True


def _row_eligible(row: Mapping) -> bool:
    return bool(row.get("eligible", True))


def _row_is_foreign(row: Mapping) -> bool:
    return bool(row.get("cross_project"))


def _passes_filters(row: Mapping, filters: Mapping) -> bool:
    for key, expected in filters.items():
        observed = row.get(key)
        if isinstance(expected, (frozenset, set, list, tuple)):
            if observed not in expected:
                return False
        else:
            if observed != expected:
                return False
    return True


def _max_date(rows: Iterable[Mapping], measurement: str) -> date | None:
    candidate: date | None = None
    for row in rows:
        if _row_is_foreign(row) or not _row_eligible(row):
            continue
        if not _row_complete(row, measurement):
            continue
        when = _row_date(row)
        if when is None:
            continue
        if candidate is None or when > candidate:
            candidate = when
    return candidate


def _iso(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


# ---------------------------------------------------------------------------
# Measurement dispatch -- every branch *calls* report_v2.measurements; none recomputes a
# statistic locally. ``eligible_rows`` are the post-scope/window/filter/complete sample.
# ---------------------------------------------------------------------------
def _labels(rows: Sequence[Mapping], key: str) -> list:
    return [row.get(key) for row in rows]


def _measure_binary(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    pairs = pairs_from_rows(
        rows, ground_truth_key="gt_label", prediction_key="pred_label"
    )
    metrics = binary_classification_metrics(pairs, vocabulary=_BINARY_VOCAB)
    return metrics.as_dict(), {}


def _measure_kappa(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    ref = _labels(rows, "gt_label")
    pred = _labels(rows, "pred_label")
    kappa = cohen_kappa(ref, pred)
    return {"kappa": _snapshot(kappa)}, {}


def _measure_mcnemar(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    ref = _labels(rows, "gt_label")
    pred = _labels(rows, "pred_label")
    return {"mcnemar": _snapshot(mcnemar(ref, pred))}, {}


def _measure_fnfp(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    ref = _labels(rows, "gt_label")
    pred = _labels(rows, "pred_label")
    ids = [row.get("accession", index) for index, row in enumerate(rows)]
    return {"fn_fp": _snapshot(fn_fp_cases(ref, pred, ids))}, {}


def _measure_duration(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    values = [row.get("duration_seconds") for row in rows]
    snap = _snapshot(duration_summary(values))
    chart: dict[str, Any] = {}
    if ctx.get("display") == "boxplot":
        grouping = ctx.get("grouping") or ()
        if not grouping:
            chart["summaries"] = [{"name": "values", "unit": "seconds", "summary": snap}]
        else:
            chart["summaries"] = []
            for sig, sub in _partition_by_grouping(rows, grouping):
                sub_vals = [r.get("duration_seconds") for r in sub]
                chart["summaries"].append(
                    {"name": sig, "unit": "seconds", "summary": _snapshot(duration_summary(sub_vals))}
                )
    return {"duration": snap}, {"chart": chart}


def _measure_prevalence(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    by_site = categorical_count(rows, column="site")
    chart: dict[str, Any] = {}
    if ctx.get("display") == "pie":
        chart["categories"] = [{"label": k, "count": v} for k, v in sorted(by_site.items())]
    return {"by_site": by_site}, {"chart": chart}


def _measure_categorical(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    grouping = ctx.get("grouping") or ()
    by_category = categorical_count(rows, column=grouping[0] if grouping else "category")
    chart: dict[str, Any] = {}
    if ctx.get("display") == "pie":
        chart["categories"] = [{"label": k, "count": v} for k, v in sorted(by_category.items())]
    chart["series"] = [{"group": "Studies", "category": str(k), "value": v, "unit": "count"} for k, v in sorted(by_category.items(), key=lambda item: str(item[0]))]
    return {"by_category": by_category}, {"chart": chart}


def _measure_record(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    return {"n": record_count(rows)}, {}


# ---------------------------------------------------------------------------
# Shared helpers for the new measurement handlers (Task-16 A2).
# ---------------------------------------------------------------------------

def _score_columns_from_inputs(ctx: dict) -> tuple[str, ...]:
    """Physical columns of every bound source in ``ctx["inputs"]`` whose kind is score."""
    cols: list[str] = []
    for source_id in (ctx.get("inputs") or {}).values():
        try:
            source = ctx["project"].source(str(source_id))
        except Exception:
            continue
        if getattr(source, "kind", None) == "score" and source.field not in cols:
            cols.append(source.field)
    return tuple(sorted(cols))


def _bound_column(ctx: dict, role: str, default: Any = None) -> Any:
    """Resolve a role binding to the physical column name via the project source catalog."""
    inputs = ctx.get("inputs") or {}
    sid = inputs.get(role)
    if sid is None:
        return default
    try:
        return ctx["project"].source(str(sid)).field
    except Exception:
        raise UnknownMeasurementError(
            f"cannot resolve role {role!r} from source {sid!r}"
        )


def _comparison(ctx: dict) -> dict:
    """Extract the comparison source-id mapping from widget inputs."""
    inputs = ctx.get("inputs") or {}
    result: dict[str, Any] = {
        "reference": inputs.get("ground_truth"),
        "prediction": inputs.get("prediction"),
    }
    alt = inputs.get("alternative_reference")
    if alt is not None:
        result["alternative_reference"] = alt
    return result


def _labels2(rows: Sequence[Mapping]) -> tuple[list, list]:
    """Extract parallel (gt_labels, pred_labels) lists from rows."""
    return (
        [r.get("gt_label") for r in rows],
        [r.get("pred_label") for r in rows],
    )


def _partition_by_grouping(
    rows: Sequence[Mapping], keys: tuple[str, ...]
) -> list[tuple[str, list[Mapping]]]:
    """Partition rows by grouping-key tuples in first-seen order, returning (label, sub-rows) pairs."""
    seen: dict[tuple, list] = {}
    for row in rows:
        sig = tuple(str(row.get(key)) for key in keys)
        seen.setdefault(sig, []).append(row)
    return [
        (
            " | ".join(f"{key}={val}" for key, val in zip(keys, sig)),
            sub,
        )
        for sig, sub in seen.items()
    ]


def _summary_columns(summary: Any) -> dict:
    """Extract the 12-column row dict from a ClassificationSummary (binary branch)."""
    c = summary.counts
    m = summary.metrics

    def _rv(rate: Any) -> float | None:
        return rate.value

    return {
        "n": c.eligible,
        "accuracy": _rv(m.accuracy),
        "balanced_accuracy": _rv(m.balanced_accuracy),
        "sensitivity": _rv(m.sensitivity),
        "specificity": _rv(m.specificity),
        "ppv": _rv(m.ppv),
        "npv": _rv(m.npv),
        "tp": c.tp,
        "tn": c.tn,
        "fp": c.fp,
        "fn": c.fn,
        "predicted_negative_fraction": _rv(m.predicted_negative_fraction),
    }


def _bucket_rows(
    rows: Sequence[Mapping], bucket: Mapping,
) -> list[Mapping]:
    """Filter rows whose date falls within a bucket's [start_date, end_date] window."""
    sd_raw = bucket.get("start_date")
    ed_raw = bucket.get("end_date")
    sd = date.fromisoformat(sd_raw) if isinstance(sd_raw, str) else sd_raw
    ed = date.fromisoformat(ed_raw) if isinstance(ed_raw, str) else ed_raw
    if sd is None or ed is None:
        return []
    out: list[Mapping] = []
    for row in rows:
        when = _row_date(row)
        if when is not None and sd <= when <= ed:
            out.append(row)
    return out


def _rate_series_cells(
    rows: Sequence[Mapping],
    buckets: tuple[Mapping, ...],
    grouping: tuple[str, ...],
    metric_name: str,
) -> tuple[list[dict], dict[str, str]]:
    """Build line-chart series cells from bucket/group partitions, recomputing per-partition rates."""
    cells: list[dict] = []
    extra_units: dict[str, str] = {}
    for bucket_idx, bucket in enumerate(buckets):
        b_rows = _bucket_rows(rows, bucket)
        if grouping:
            groups = _partition_by_grouping(b_rows, grouping)
        else:
            groups = [("value", b_rows)]
        for gname, grows in groups:
            if gname not in extra_units:
                extra_units[gname] = "rate[0,1]"
            if not grows:
                cells.append({
                    "group": gname, "category": None,
                    "bucket_index": bucket_idx, "value": None,
                })
            else:
                pairs = pairs_from_rows(
                    grows, ground_truth_key="gt_label", prediction_key="pred_label",
                )
                if not pairs:
                    cells.append({
                        "group": gname, "category": None,
                        "bucket_index": bucket_idx, "value": None,
                    })
                else:
                    m = binary_classification_metrics(pairs, vocabulary=_BINARY_VOCAB)
                    r = m.rate(metric_name)
                    cells.append({
                        "group": gname, "category": None,
                        "bucket_index": bucket_idx, "value": r.value,
                    })
    return cells, extra_units


def _bar_series_cells(
    rows: Sequence[Mapping],
    grouping: tuple[str, ...],
    metric_name: str,
) -> tuple[list[dict], dict[str, str]]:
    """Build bar-chart cells (one per group, no buckets)."""
    cells: list[dict] = []
    extra_units: dict[str, str] = {}
    if grouping:
        groups = _partition_by_grouping(rows, grouping)
    else:
        groups = [("value", list(rows))]
    for gname, grows in groups:
        if gname not in extra_units:
            extra_units[gname] = "rate[0,1]"
        if not grows:
            cells.append({
                "group": gname, "category": gname,
                "bucket_index": None, "value": None,
            })
        else:
            pairs = pairs_from_rows(
                grows, ground_truth_key="gt_label", prediction_key="pred_label",
            )
            if not pairs:
                cells.append({
                    "group": gname, "category": gname,
                    "bucket_index": None, "value": None,
                })
            else:
                m = binary_classification_metrics(pairs, vocabulary=_BINARY_VOCAB)
                r = m.rate(metric_name)
                cells.append({
                    "group": gname, "category": gname,
                    "bucket_index": None, "value": r.value,
                })
    return cells, extra_units


# ---------------------------------------------------------------------------
# New measurement handlers (Task-16 A2).
# ---------------------------------------------------------------------------

def _measure_label_count(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    col = _bound_column(ctx, "value")
    if col is None:
        raise UnknownMeasurementError(
            "label_count requires a 'value' role binding; none found in widget inputs"
        )
    counts = _label_count_primitive(rows, label_key=col, vocabulary=None)
    return (
        {"label_count": int(sum(counts.values())), "n": record_count(rows)},
        {
            "units": {"label_count": "count", "n": "count"},
            "chart": {"comparison": _comparison(ctx)},
        },
    )


def _make_binary_rate_handler(metric_name: str):
    """Return a handler that calls binary_classification_metrics and extracts the named rate."""
    def handler(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
        pairs = pairs_from_rows(
            rows, ground_truth_key="gt_label", prediction_key="pred_label",
        )
        metrics = binary_classification_metrics(pairs, vocabulary=_BINARY_VOCAB)
        rate = metrics.rate(metric_name)
        n = rate.denominator if rate.denominator is not None else record_count(rows)
        aggregates: dict[str, Any] = {metric_name: rate.value, "n": n}
        units: dict[str, str] = {metric_name: "rate[0,1]", "n": "count"}
        chart: dict[str, Any] = {
            "comparison": _comparison(ctx),
            "rate_detail": {
                "label": rate.label,
                "numerator": rate.numerator,
                "denominator": rate.denominator,
                "null_reason": rate.null_reason,
            },
        }
        display = ctx.get("display")
        grouping = ctx.get("grouping") or ()
        if display == "line":
            buckets = ctx.get("buckets") or ()
            if buckets:
                cells, extra_units = _rate_series_cells(rows, buckets, grouping, metric_name)
                chart["series"] = cells
                units.update(extra_units)
        elif display == "bar":
            cells, extra_units = _bar_series_cells(rows, grouping, metric_name)
            chart["series"] = cells
            units.update(extra_units)
        return aggregates, {"units": units, "chart": chart}
    return handler


_measure_accuracy = _make_binary_rate_handler("accuracy")
_measure_sensitivity = _make_binary_rate_handler("sensitivity")
_measure_specificity = _make_binary_rate_handler("specificity")
_measure_balanced_accuracy = _make_binary_rate_handler("balanced_accuracy")


def _measure_classification_summary(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    pairs = pairs_from_rows(
        rows, ground_truth_key="gt_label", prediction_key="pred_label",
    )
    summary = _classification_summary(pairs, vocabulary=_BINARY_VOCAB)
    aggregates: dict[str, Any] = {"summary": _snapshot(summary.as_dict())}
    grouping = ctx.get("grouping") or ()
    if not grouping:
        extra_rows: tuple[Mapping, ...] = ({"group": "overall", **_summary_columns(summary)},)
    else:
        extra_rows_list: list[dict] = []
        for _label, sub_rows in _partition_by_grouping(rows, grouping):
            sub_pairs = pairs_from_rows(
                sub_rows, ground_truth_key="gt_label", prediction_key="pred_label",
            )
            if not sub_pairs:
                continue
            sub_summary = _classification_summary(sub_pairs, vocabulary=_BINARY_VOCAB)
            first = sub_rows[0]
            row: dict[str, Any] = {}
            for k in grouping:
                row[k] = first.get(k)
            row.update(_summary_columns(sub_summary))
            extra_rows_list.append(row)
        extra_rows_list.append({**{key: "Overall" for key in grouping}, **_summary_columns(summary)})
        extra_rows = tuple(extra_rows_list)
    comparison = _comparison(ctx)
    chart: dict[str, Any] = {
        "overall_row": bool(grouping),
        "comparison": comparison,
        "caption": "Reference {} versus prediction {}".format(
            comparison.get("reference"), comparison.get("prediction"),
        ),
    }
    units: dict[str, str] = {
        "accuracy": "rate[0,1]", "balanced_accuracy": "rate[0,1]",
        "sensitivity": "rate[0,1]", "specificity": "rate[0,1]",
        "ppv": "rate[0,1]", "npv": "rate[0,1]",
        "predicted_negative_fraction": "rate[0,1]",
        "n": "count", "tp": "count", "tn": "count", "fp": "count", "fn": "count",
    }
    return aggregates, {"rows": extra_rows, "units": units, "chart": chart}


def _measure_reference_agreement(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    ref, pred = _labels2(rows)
    rate = cohen_kappa(ref, pred)
    # The agreement rate is taken from the *same* classification primitive every other reported rate
    # reads (the single source of truth), never from local arithmetic; it therefore stays undefined
    # (None) over an empty complete population rather than collapsing to 0.
    pairs = pairs_from_rows(
        rows, ground_truth_key="gt_label", prediction_key="pred_label"
    )
    metrics = binary_classification_metrics(pairs, vocabulary=_BINARY_VOCAB)
    agreement_rate = metrics.rate("accuracy")
    agreement_value: float | None = agreement_rate.value  # None when undefined -- never 0
    kappa_value = rate.value  # may be None for degenerate marginals
    n = record_count(rows)
    aggregates: dict[str, Any] = {"agreement": agreement_value, "kappa": kappa_value, "n": n}
    units: dict[str, str] = {"agreement": "rate[0,1]", "kappa": "index[-1,1]", "n": "count"}
    comparison = _comparison(ctx)
    chart: dict[str, Any] = {
        "comparison": comparison,
        "caption": "Reference {} versus prediction {} agreement".format(
            comparison.get("reference"), comparison.get("prediction"),
        ),
        "rate_detail": {
            "label": rate.label,
            "numerator": rate.numerator,
            "denominator": rate.denominator,
            "null_reason": rate.null_reason,
        },
        "agreement_detail": {
            "label": agreement_rate.label,
            "numerator": agreement_rate.numerator,
            "denominator": agreement_rate.denominator,
            "null_reason": agreement_rate.null_reason,
        },
    }
    extra_rows: tuple[Mapping, ...] = ({
        "n": n, "agreement": agreement_value, "kappa": kappa_value,
    },)
    return aggregates, {"rows": extra_rows, "units": units, "chart": chart}


def _measure_paired_reference_comparison(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    alt_col = _bound_column(ctx, "alternative_reference")
    if alt_col is None:
        raise UnknownMeasurementError(
            "paired_reference_comparison requires an 'alternative_reference' role binding"
        )
    ref_ok: list[int] = []
    alt_ok: list[int] = []
    excluded_missing_alternate = 0
    for row in rows:
        gt = row.get("gt_label")
        pred = row.get("pred_label")
        alt = row.get(alt_col)
        if gt is None or pred is None:
            continue
        if alt is None:
            excluded_missing_alternate += 1
            continue
        ref_ok.append(1 if gt == pred else 0)
        alt_ok.append(1 if alt == pred else 0)
    result = mcnemar(ref_ok, alt_ok)
    n = len(ref_ok)
    aggregates: dict[str, Any] = {"mcnemar": _snapshot(result), "n": n}
    units: dict[str, str] = {
        "p_value": "probability[0,1]",
        "statistic": "index[0,\u221e)",
        "b": "count", "c": "count", "n": "count",
    }
    comparison = _comparison(ctx)
    chart: dict[str, Any] = {
        "comparison": comparison,
        "caption": "Reference {} versus alternative reference {} against prediction {}".format(
            comparison.get("reference"), comparison.get("alternative_reference"),
            comparison.get("prediction"),
        ),
        "excluded_missing_alternate": excluded_missing_alternate,
    }
    extra_rows: tuple[Mapping, ...] = ({
        "n": n, "b": result.b, "c": result.c, "p_value": result.p_value,
    },)
    return aggregates, {"rows": extra_rows, "units": units, "chart": chart}


def _highest_score_cell(row: Mapping, columns: Sequence[str]) -> tuple[str | None, float | None]:
    """Return ``(highest_finding, highest_score)`` for the finite-numeric maximum over ``columns``.

    The single implementation shared by both the explicit-binding and the catalog-fallback branch of the
    FN/FP case columns. It reproduces the legacy display exactly: the maximum over the finite numeric
    values, rounded to one decimal place, labelled by the physical column name spelled out (underscores
    turned into spaces and title-cased). **No threshold is applied** -- the raw maximum, the same posture
    as the legacy export. An empty / none-finite column set yields ``(None, None)`` rather than a fabrication.
    """
    highest_score: float | None = None
    highest_finding: str | None = None
    best_val = float("-inf")
    for col in columns:
        raw = row.get(col)
        if raw is None:
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if not _isfinite(v):
            continue
        if v > best_val:
            best_val = v
            highest_score = v
            highest_finding = col.replace("_", " ").title()
    if best_val == float("-inf"):
        highest_score = None
        highest_finding = None
    elif highest_score is not None:
        highest_score = round(highest_score, 1)
    return highest_finding, highest_score


def _catalog_score_columns(ctx: dict) -> tuple[str, ...]:
    """Physical fields of every score-kind source in the project catalog, in deterministic order.

    A *fallback only*, consulted when the widget binds no score source explicitly. The set is derived from
    the catalog alone -- no new names, no literals; the reviewed PRIME catalog contributes exactly its ten
    ``kind == "score"`` sources. When the catalog yields none the caller keeps both case columns ``None``
    rather than fabricate a score.
    """
    try:
        sources = getattr(ctx["project"], "sources", {}) or {}
        ordered = sorted(
            sources.values(),
            key=lambda s: (str(getattr(s, "field", "")), str(getattr(s, "source_id", ""))),
        )
        fields = [
            source.field
            for source in ordered
            if getattr(source, "kind", None) == "score"
            and getattr(source, "field", None) is not None
        ]
    except Exception:  # any catalog error -> treat as "no score sources", never crash the export
        return ()
    seen: dict[str, None] = {}
    for field in fields:
        seen.setdefault(field, None)
    return tuple(seen)


# FN/FP case-column precedence (a documented *parity* decision, not a clinical rule):
#   explicit widget role binding  >  reviewed PRIME catalog default  >  None.
# The reviewed catalog already names the canonical physical columns, so an unbound role falls back to it
# instead of publishing None; an *explicit* binding always wins and is never overridden. No threshold is
# applied to the score display -- the highest score is the raw maximum, the same posture as the legacy export.
def _make_fnfp_handler(measurement_id: str):
    """Return a handler for false_negatives or false_positives."""
    is_fn = measurement_id == "false_negatives"

    def handler(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
        ref, pred = _labels2(rows)
        ids = [row.get("accession", i) for i, row in enumerate(rows)]
        res = fn_fp_cases(ref, pred, ids, reference="manual", prediction="llm")
        selected_ids = res.false_negative_ids if is_fn else res.false_positive_ids
        # Build a lookup from id -> row
        id_to_row = {row.get("accession", i): row for i, row in enumerate(rows)}
        # Highest-score column set: explicit widget bindings win; else fall back to the reviewed catalog's
        # score-kind sources (never fabricated -- an empty catalog leaves both columns None).
        score_cols = ctx.get("score_columns") or ()
        fallback_score_cols = () if score_cols else _catalog_score_columns(ctx)
        # Report-text column: an explicit 'report_text' binding wins; else the reviewed catalog source id
        # 'report_text' (its .field is the physical row key); else None.
        report_text_col = _bound_column(ctx, "report_text", None)
        if report_text_col is None:
            try:
                report_text_col = ctx["project"].source("report_text").field
            except Exception:  # catalog error -> no key, publish None rather than fabricate
                report_text_col = None
        case_rows: list[dict] = []
        for sid in selected_ids:
            row = id_to_row.get(sid, {})
            if score_cols:
                highest_finding, highest_score = _highest_score_cell(row, score_cols)
            elif fallback_score_cols:
                highest_finding, highest_score = _highest_score_cell(row, fallback_score_cols)
            else:
                highest_finding = None
                highest_score = None
            report_text = (
                row.get(report_text_col) if report_text_col is not None else None
            )
            case_rows.append({
                "accession": sid,
                "site": row.get("site"),
                "study_date": row.get("event_date"),
                "highest_finding": highest_finding,
                "highest_score": highest_score,
                "report_text": report_text,
            })
        count_key = measurement_id
        aggregates: dict[str, Any] = {
            count_key: len(selected_ids),
            "n_total": res.n_total,
            "n_complete": res.n_complete,
            "excluded_incomplete": res.excluded_incomplete,
        }
        units: dict[str, str] = {
            count_key: "count", "n_total": "count",
            "n_complete": "count", "excluded_incomplete": "count",
        }
        chart: dict[str, Any] = {
            "comparison": _comparison(ctx),
            "direction": _comparison(ctx),
        }
        return aggregates, {"rows": tuple(case_rows), "units": units, "chart": chart}
    return handler


_measure_false_negatives = _make_fnfp_handler("false_negatives")
_measure_false_positives = _make_fnfp_handler("false_positives")


def _measure_confusion_matrix(rows: Sequence[Mapping], ctx: dict) -> tuple[dict, dict]:
    pairs = pairs_from_rows(
        rows, ground_truth_key="gt_label", prediction_key="pred_label",
    )
    # Collect distinct non-None labels from both streams
    all_labels: set = set()
    for gt, pred in pairs:
        if gt is not None:
            all_labels.add(gt)
        if pred is not None:
            all_labels.add(pred)
    if not all_labels:
        raise UnknownMeasurementError(
            "confusion_matrix requires at least two distinct non-None label classes"
        )
    # Binary sources retain both classes even when the selected population has only one.
    if all_labels <= {0, 1}:
        pairs = [(int(gt), int(pred)) for gt, pred in pairs]
        all_labels = {0, 1}
    # Check for mixed str/int
    types = {type(label) for label in all_labels}
    if len(types) > 1:
        raise UnknownMeasurementError(
            f"confusion_matrix cannot mix label types: {types}"
        )
    classes = sorted(all_labels, key=repr)
    if len(classes) < 2:
        raise UnknownMeasurementError(
            "confusion_matrix requires at least two distinct non-None label classes"
        )
    matrix = _confusion_matrix(pairs, classes=classes)
    matrix_dict = _snapshot(matrix.as_dict()) if hasattr(matrix, "as_dict") else _snapshot(matrix)
    # Build renderer contract keys matching confusion.mjs expectations
    cells_2d = [list(row) for row in matrix.cells]
    row_totals = list(matrix.row_totals)
    accuracy_rate = matrix.accuracy
    aggregates: dict[str, Any] = {
        "matrix": matrix_dict,
        "classes": [str(c) for c in classes],
    }
    comparison = _comparison(ctx)
    chart: dict[str, Any] = {
        "comparison": comparison,
        "caption": "Declared ground-truth rows versus prediction columns",
        "classes": [str(c) for c in classes],
        "cells": cells_2d,
        "row_totals": row_totals,
        "accuracy": {"value": accuracy_rate.value},
    }
    return aggregates, {"chart": chart}


_MEASUREMENT_DISPATCH: dict[str, Callable[..., tuple[dict, dict]]] = {
    "binary_classification": _measure_binary,
    "agreement_kappa": _measure_kappa,
    "agreement_mcnemar": _measure_mcnemar,
    "fn_fp_cases": _measure_fnfp,
    "duration_summary": _measure_duration,
    "prevalence": _measure_prevalence,
    "categorical_count": _measure_categorical,
    "record_count": _measure_record,
    "label_count": _measure_label_count,
    "accuracy": _measure_accuracy,
    "sensitivity": _measure_sensitivity,
    "specificity": _measure_specificity,
    "balanced_accuracy": _measure_balanced_accuracy,
    "classification_summary": _measure_classification_summary,
    "reference_agreement": _measure_reference_agreement,
    "paired_reference_comparison": _measure_paired_reference_comparison,
    "false_negatives": _measure_false_negatives,
    "false_positives": _measure_false_positives,
    "confusion_matrix": _measure_confusion_matrix,
}

#: Measurements that compare two label streams and therefore require a *common* population.
PAIRED_MEASUREMENTS = frozenset(
    {
        "agreement_kappa", "agreement_mcnemar", "fn_fp_cases",
        "accuracy", "sensitivity", "specificity", "balanced_accuracy",
        "classification_summary", "reference_agreement",
        "paired_reference_comparison", "false_negatives", "false_positives",
        "confusion_matrix",
    }
)


def _common_population(rows: Sequence[Mapping], widget: WidgetSpec) -> CommonPopulation:
    """Build the :class:`CommonPopulation` from the *single shared* complete-row filter.

    Both sides read their count from the very same :func:`complete_rows` result, so
    ``sides['reference'] == sides['prediction'] == n_complete`` by construction -- a structural
    proof that the paired widget measured identical rows on both arms.
    """
    ref = _labels(rows, "gt_label")
    pred = _labels(rows, "pred_label")
    shared = complete_rows(ref, pred)
    n_complete = shared.complete
    return CommonPopulation(
        filter_identity=f"{widget.widget_id}:complete_rows",
        n_complete=n_complete,
        sides={"reference": n_complete, "prediction": n_complete},
    )


def _maybe_ci(widget: WidgetSpec, aggregates: dict, ci_registry: object) -> dict:
    """Resolve the CI config through the measurements CI registry + :func:`wilson_interval`."""
    if not ci_registry:
        return {}
    metric = "positive_predictive_value"
    if isinstance(ci_registry, Mapping):
        wanted = set(ci_registry)
    else:
        wanted = set(ci_registry)
    if metric not in wanted:
        return {}
    try:  # prove the gate is consulted through the shared registry before publication
        require_proportion_ci(metric, "wilson")
    except Exception:  # UnsupportedCiError -> omit the column rather than fabricate one
        return {metric: {"available": False, "reason": "unregistered"}}
    cells = aggregates.get("counts", {}) if isinstance(aggregates, Mapping) else {}
    tp = int(cells.get("tp", 0) or 0)
    fp = int(cells.get("fp", 0) or 0)
    n = tp + fp
    if n <= 0:
        return {metric: {"available": False, "reason": "zero_denominator", "n": 0}}
    interval = wilson_interval(tp, n)
    return {metric: {"available": True, **asdict(interval)}}


# ---------------------------------------------------------------------------
# Grouping / bucketing with hard bounds.
# ---------------------------------------------------------------------------
def _normalise_grouping(grouping: object) -> tuple[str, ...]:
    if grouping is None:
        return ()
    if isinstance(grouping, str):
        return (grouping,)
    return tuple(str(key) for key in grouping)


def _distinct_groups(rows: Sequence[Mapping], keys: tuple[str, ...]) -> tuple[str, ...]:
    seen: dict[tuple, None] = {}
    for row in rows:
        sig = tuple(str(row.get(key)) for key in keys)
        seen.setdefault(sig, None)
    return tuple(
        " | ".join(f"{key}={value}" for key, value in zip(keys, sig))
        for sig in seen
    )


def _resolve_policy(
    project: object, catalog: ProjectRegistry | None, policy: object
) -> tuple[str | None, int | None]:
    """Return ``(policy_ref, policy_version)``; propagate foreign refs; unknown -> typed error."""
    if policy is None:
        return (None, None)

    if isinstance(policy, str):
        policy_ref = policy
    else:
        policy_id = getattr(policy, "policy_id", None)
        version = getattr(policy, "version", None)
        if policy_id is None:
            policy_ref = str(policy)
        else:
            policy_ref = f"{policy_id}@{version}" if version is not None else str(policy_id)

    bare = policy_ref.partition("@")[0]
    policies = getattr(project, "policies", {}) or {}
    if bare in policies:
        if hasattr(project, "policy"):
            try:
                project.policy(policy_ref)
            except ProjectCatalogError as exc:
                raise UnknownPolicyError("unknown threshold policy version") from exc
        version = getattr(policies[bare], "version", None)
        return (policy_ref, int(version) if version is not None else None)

    if catalog is not None:
        try:
            require_project_context(
                str(getattr(project, "project_id", "")),
                registry=catalog,
                policy_ref=policy_ref,
            )
        except CrossProjectReferenceError:
            raise  # a genuinely foreign reference is never swallowed or translated
        except ProjectCatalogError as exc:
            raise UnknownPolicyError(f"unknown policy {policy_ref!r}: {exc}") from exc
    raise UnknownPolicyError(f"unknown policy {policy_ref!r} for this project")


# ---------------------------------------------------------------------------
# The orchestrator.
# ---------------------------------------------------------------------------
def evaluate(
    *,
    request: RequestContract,
    project: object,
    catalog: ProjectRegistry | None,
    rows: Sequence[Mapping],
    measurement: Optional[str] = None,
    policy: object = None,
    ci_registry: object = None,
    grouping: object = None,
    buckets: Optional[str] = None,
    page_size: Optional[int] = None,
    max_groups: int = DEFAULT_MAX_GROUPS,
    published_widget_ids: frozenset = PUBLISHED_WIDGET_IDS,
    widgets: Mapping = PUBLISHED_WIDGETS,
    include_rows: bool = False,
    widget_inputs: Optional[Mapping] = None,
    selected_rows: list | None = None,
) -> ResultPayload:
    """Run the frozen eight-step widget pipeline and publish a :class:`ResultPayload`.

    The order below is the contract; each step is observable through the returned ledger, dates,
    buckets and groups. Steps: ``scope -> completeness -> D-capture -> widget-window -> user-filters
    -> eligible-sample -> grouping/buckets -> measurement``.
    """
    rows = list(rows)
    timezone = getattr(project, "timezone", None) or DEFAULT_TIMEZONE
    project_id = str(getattr(project, "project_id", ""))

    # ---- 0. request validity (widget allow-list; disallowed overrides already raised) -----
    widget_id = request.widget_id
    if widget_id not in published_widget_ids:
        raise InvalidWidgetReferenceError(f"widget {widget_id!r} is not published")
    widget = widgets[widget_id]

    measurement_id = widget.measurement if measurement is None else measurement
    if measurement_id != widget.measurement:
        # An explicit measurement differing from the widget's declared one is a measurement
        # *selection* override -> structurally forbidden.
        raise DisallowedOverrideError(
            f"measurement {measurement_id!r} does not match the published widget's "
            f"{widget.measurement!r}; measurement selection is not overridable"
        )
    if measurement_id not in SUPPORTED_MEASUREMENTS:
        raise UnknownMeasurementError(
            f"unsupported measurement {measurement_id!r} for widget {widget_id!r}"
        )

    called_modules: list[str] = ["report_v2.projects", "report_v2.dates", "report_v2.measurements"]

    # ---- 1. project scope: resolve through the Task-04 guard; propagate foreign refs ------
    if catalog is not None:
        try:
            require_project_context(project_id, registry=catalog)
        except CrossProjectReferenceError:
            raise
    policy_ref, policy_version = _resolve_policy(project, catalog, policy)

    # ---- 3. D capture (needs the full picture; done before the window which depends on D) -
    #  capture_anchor derives D from the latest complete, eligible candidate; a newer
    #  incomplete candidate does not advance it. Different measurements -> possibly different D.
    candidates = [
        {
            "event_date": _row_date(row),
            "complete": _row_complete(row, measurement_id),
            "eligible": _row_eligible(row) and not _row_is_foreign(row),
        }
        for row in rows
        if _row_date(row) is not None
    ]
    captured = capture_anchor(candidates, timezone=timezone)
    anchor = captured.date if captured is not None else None

    # subgroup-latest is coverage-only metadata over the rows that survive the *user filters*
    # and completeness for this measurement (window membership is irrelevant to the coverage note).
    filtered_candidates = [
        row
        for row in rows
        if (not _row_is_foreign(row))
        and _row_eligible(row)
        and _passes_filters(row, request.filter_overrides)
    ]
    subgroup_latest = _max_date(filtered_candidates, measurement_id)

    # ---- 4. widget window: resolve the inclusive [start, end] ending at D ----------------
    user_request: dict[str, Any] = {}
    override = request.date_override
    if isinstance(override, Mapping):
        if "start" in override:
            user_request["start"] = override.get("start")
            user_request["end"] = override.get("end", "D")
        elif "relative" in override:
            user_request["relative"] = override.get("relative")
        else:
            user_request["relative"] = widget.window
    elif override is not None:
        coerced = _to_date(override)
        if coerced is None:
            user_request["relative"] = widget.window
        else:
            user_request["start"] = coerced.isoformat()
            user_request["end"] = "D"
    else:
        user_request["relative"] = widget.window

    window = None
    if anchor is not None:
        window = resolve_request(
            user_request,
            captured_anchor=anchor,
            timezone=timezone,
            subgroup_latest_eligible_date=subgroup_latest,
        )
    start_date = window.start_date if window is not None else None
    end_date = window.end_date if window is not None else None

    # ---- 2 + 5 + 6. window/filter/foreign drops, then completeness drop -------------------
    reasons = {reason: 0 for reason in EXCLUSION_REASONS}
    matching_rows: list[Mapping] = []
    for row in rows:
        if _row_is_foreign(row):
            reasons["foreign_identifier"] += 1
            continue
        when = _row_date(row)
        in_window = (
            when is not None
            and start_date is not None
            and end_date is not None
            and start_date <= when <= end_date
        )
        if not in_window:
            reasons["out_of_window"] += 1
            continue
        if not _row_eligible(row) or not _passes_filters(row, request.filter_overrides):
            reasons["filtered_out"] += 1
            continue
        matching_rows.append(row)

    matching = len(matching_rows)
    eligible_rows: list[Mapping] = []
    for row in matching_rows:
        if not _row_complete(row, measurement_id):
            reasons["missing_required"] += 1
            continue
        eligible_rows.append(row)
    eligible = len(eligible_rows)
    if selected_rows is not None:
        selected_rows.extend(dict(row) for row in eligible_rows)
    incoming = len(rows)
    excluded_incomplete = matching - eligible

    # ---- 7. grouping / buckets with hard bounds --------------------------------------------
    group_keys = _normalise_grouping(grouping)
    group_labels: tuple[str, ...] = ()
    if group_keys:
        group_labels = _distinct_groups(eligible_rows, group_keys)
        if len(group_labels) > max_groups:
            raise GroupCardinalityError(
                f"grouping produced {len(group_labels)} groups, exceeding max_groups={max_groups}"
            )

    bucket_payloads: tuple[Mapping, ...] = ()
    if buckets is not None and start_date is not None and end_date is not None:
        called_modules.append("report_v2.dates.bucket_range")
        bucket_payloads = tuple(
            bucket.as_dict() for bucket in bucket_range(
                start_date=start_date, end_date=end_date, size=buckets, timezone=timezone
            )
        )

    if page_size is not None:
        if not isinstance(page_size, int) or isinstance(page_size, bool) or page_size <= 0:
            raise PaginationBoundError(f"page_size must be a positive int; got {page_size!r}")
        if page_size > MAX_PAGE_SIZE:
            raise PaginationBoundError(
                f"page_size {page_size} exceeds the hard cap {MAX_PAGE_SIZE}"
            )

    # ---- build the evaluation context for the measurement handlers ---------------------------
    bare_policy = (policy_ref or "").partition("@")[0]
    resolved_policy = None
    if bare_policy:
        resolved_policy = (getattr(project, "policies", {}) or {}).get(bare_policy)
    ctx: dict[str, Any] = {
        "inputs": dict(widget_inputs or {}),
        "project": project,
        "policy": resolved_policy,
        "policy_ref": policy_ref,
        "grouping": group_keys,
        "buckets": bucket_payloads,
        "score_columns": _score_columns_from_inputs(
            {"inputs": dict(widget_inputs or {}), "project": project}
        ),
        "display": widget.display,
    }

    # ---- 8. measurement: call report_v2.measurements ---------------------------------------
    if measurement_id not in _MEASUREMENT_DISPATCH:
        raise UnknownMeasurementError(f"no dispatcher for measurement {measurement_id!r}")
    called_modules.append(f"report_v2.measurements ({measurement_id})")
    aggregates, extra = (_MEASUREMENT_DISPATCH[measurement_id](eligible_rows, ctx)
                         if eligible_rows else ({}, {}))
    handler = _MEASUREMENT_DISPATCH[measurement_id]
    if group_keys and widget.display == "value":
        grouped_values = []
        for label, subgroup in _partition_by_grouping(eligible_rows, group_keys):
            values, _ = handler(subgroup, {**ctx, "grouping": ()})
            grouped_values.append({"name": label, "aggregates": values,
                                   "ci": _maybe_ci(widget, values, ci_registry)})
        extra.setdefault("chart", {})["grouped_values"] = grouped_values
    if eligible_rows and group_keys and widget.display == "table" and measurement_id in {
        "reference_agreement", "paired_reference_comparison", "duration_summary", "record_count", "label_count"
    }:
        def summary_row(subgroup):
            values, details = handler(subgroup, {**ctx, "grouping": ()})
            if details.get("rows"):
                return dict(details["rows"][0])
            return dict(values.get("duration") or values)
        grouped_rows = []
        for _, subgroup in _partition_by_grouping(eligible_rows, group_keys):
            grouped_rows.append({**{key: subgroup[0].get(key) for key in group_keys}, **summary_row(subgroup)})
        grouped_rows.append({**{key: "Overall" for key in group_keys}, **summary_row(eligible_rows)})
        extra["rows"] = tuple(grouped_rows)
        extra.setdefault("chart", {})["overall_row"] = True
    if group_keys and measurement_id in {"false_negatives", "false_positives"}:
        source_rows = {row.get("accession"): row for row in eligible_rows}
        extra["rows"] = tuple({**{key: source_rows.get(row["accession"], {}).get(key) for key in group_keys}, **row}
                              for row in extra.get("rows", ()))
        extra["rows"] = tuple(sorted(extra["rows"], key=lambda row: tuple(str(row.get(key)) for key in group_keys)))


    # ---- 7b. row payload (after dispatch so handlers can supply rows via extra) ---------------
    row_payload: tuple[Mapping, ...] = ()
    if "rows" in extra:
        row_source = tuple(dict(r) for r in extra["rows"])
    else:
        row_source = tuple(dict(r) for r in eligible_rows)

    if include_rows:
        if widget.aggregate:
            raise NonAggregateRowsError(
                f"aggregate widget {widget_id!r} cannot publish raw case-level rows"
            )
        row_payload = row_source
    elif extra.get("rows") is not None and not widget.aggregate:
        row_payload = row_source

    # pagination recomputed from the FINAL row_payload
    pagination = None
    if page_size is not None:
        pagination = {
            "page_size": page_size,
            "returned": len(row_payload),
            "truncated": len(row_payload) > page_size,
        }

    common_population = None
    if measurement_id in PAIRED_MEASUREMENTS:
        called_modules.append("report_v2.measurements.agreement.complete_rows")
        common_population = _common_population(eligible_rows, widget)

    ci = _maybe_ci(widget, aggregates, ci_registry)

    # ---- build the four always-non-empty metadata groups -----------------------------------
    # de-duplicate while preserving first-seen order
    seen: dict[str, None] = {}
    modules: list[str] = []
    for module in called_modules:
        seen.setdefault(module, None)
        modules.append(module)

    sources = SourceMetadata(modules=tuple(modules), project_id=project_id or "unknown")
    versions = VersionMetadata(
        policy_version=policy_version,
        policy_ref=policy_ref,
        schema_version=SCHEMA_VERSION,
        evaluator_version=EVALUATOR_NAME,
        measurement_id=measurement_id,
    )
    coverage_note = None
    if start_date is not None and end_date is not None:
        coverage_note = f"coverage {start_date.isoformat()}..{end_date.isoformat()}"
        if subgroup_latest is not None and end_date is not None and subgroup_latest < end_date:
            coverage_note += (
                f"; selected subgroup available through {subgroup_latest.isoformat()}"
            )
    dates = DateMetadata(
        anchor_date=_iso(anchor),
        window_start=_iso(start_date),
        window_end=_iso(end_date),
        timezone=timezone,
        subgroup_latest_date=_iso(subgroup_latest),
        coverage_note=coverage_note,
    )
    units = dict(MEASUREMENT_UNITS.get(measurement_id, {"n": "count"}))
    units.update(extra.get("units") or {})

    chart_extras: dict[str, Any] = dict(extra.get("chart") or {})

    counts = CountAccounting(
        incoming=incoming,
        matching=matching,
        eligible=eligible,
        excluded_incomplete=excluded_incomplete,
        excluded_by_reason=dict(reasons),
    )

    return ResultPayload(
        widget_id=widget.widget_id,
        display=widget.display,
        aggregate=widget.aggregate,
        aggregates=aggregates,
        rows=row_payload,
        counts=counts,
        sources=sources,
        versions=versions,
        dates=dates,
        units=units,
        ci=ci,
        common_population=common_population,
        pagination=pagination,
        buckets=bucket_payloads,
        groups=group_labels,
        chart=chart_extras,
    )


__all__ = [
    "EvaluationError",
    "InvalidWidgetReferenceError",
    "DisallowedOverrideError",
    "UnknownMeasurementError",
    "UnknownPolicyError",
    "NonAggregateRowsError",
    "GroupCardinalityError",
    "PaginationBoundError",
    "RequestContract",
    "WidgetSpec",
    "PUBLISHED_WIDGETS",
    "PUBLISHED_WIDGET_IDS",
    "SUPPORTED_MEASUREMENTS",
    "REQUIRED_COLUMNS",
    "EXCLUSION_REASONS",
    "MAX_PAGE_SIZE",
    "evaluate",
]

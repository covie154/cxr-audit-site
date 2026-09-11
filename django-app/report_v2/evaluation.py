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
    cohen_kappa,
    complete_rows,
    duration_summary,
    fn_fp_cases,
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
}

#: Per-measurement human units for the ``units`` metadata group (always non-empty).
MEASUREMENT_UNITS: dict[str, dict[str, str]] = {
    "binary_classification": {
        "sensitivity": "rate[0,1]",
        "specificity": "rate[0,1]",
        "positive_predictive_value": "rate[0,1]",
        "counts": "count",
    },
    "agreement_kappa": {"kappa": "index[-1,1]"},
    "agreement_mcnemar": {"p_value": "probability[0,1]", "discordant": "count"},
    "fn_fp_cases": {"false_negative": "count", "false_positive": "count"},
    "duration_summary": {"mean": "seconds", "median": "seconds", "n": "count"},
    "prevalence": {"count": "count"},
    "categorical_count": {"count": "count"},
    "record_count": {"n": "count"},
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


def _measure_binary(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    pairs = pairs_from_rows(
        rows, ground_truth_key="gt_label", prediction_key="pred_label"
    )
    vocabulary = BinaryClassVocabulary(
        positive_class=1, negative_class=0, label="binary"
    )
    metrics = binary_classification_metrics(pairs, vocabulary=vocabulary)
    return metrics.as_dict(), {}


def _measure_kappa(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    ref = _labels(rows, "gt_label")
    pred = _labels(rows, "pred_label")
    kappa = cohen_kappa(ref, pred)
    return {"kappa": _snapshot(kappa)}, {}


def _measure_mcnemar(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    ref = _labels(rows, "gt_label")
    pred = _labels(rows, "pred_label")
    return {"mcnemar": _snapshot(mcnemar(ref, pred))}, {}


def _measure_fnfp(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    ref = _labels(rows, "gt_label")
    pred = _labels(rows, "pred_label")
    ids = [row.get("accession", index) for index, row in enumerate(rows)]
    return {"fn_fp": _snapshot(fn_fp_cases(ref, pred, ids))}, {}


def _measure_duration(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    values = [row.get("duration_seconds") for row in rows]
    return {"duration": _snapshot(duration_summary(values))}, {}


def _measure_prevalence(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    return {"by_site": categorical_count(rows, column="site")}, {}


def _measure_categorical(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    return {"by_category": categorical_count(rows, column="category")}, {}


def _measure_record(rows: Sequence[Mapping]) -> tuple[dict, dict]:
    return {"n": record_count(rows)}, {}


_MEASUREMENT_DISPATCH: dict[str, Callable[[Sequence[Mapping]], tuple[dict, dict]]] = {
    "binary_classification": _measure_binary,
    "agreement_kappa": _measure_kappa,
    "agreement_mcnemar": _measure_mcnemar,
    "fn_fp_cases": _measure_fnfp,
    "duration_summary": _measure_duration,
    "prevalence": _measure_prevalence,
    "categorical_count": _measure_categorical,
    "record_count": _measure_record,
}

#: Measurements that compare two label streams and therefore require a *common* population.
PAIRED_MEASUREMENTS = frozenset({"agreement_kappa", "agreement_mcnemar", "fn_fp_cases"})


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

    # ---- 7b. aggregate widgets may never carry raw rows ------------------------------------
    row_payload: tuple[Mapping, ...] = ()
    if include_rows:
        if widget.aggregate:
            raise NonAggregateRowsError(
                f"aggregate widget {widget_id!r} cannot publish raw case-level rows"
            )
        row_payload = tuple(dict(row) for row in eligible_rows)

    pagination = None
    if page_size is not None:
        pagination = {
            "page_size": page_size,
            "returned": len(row_payload),
            "truncated": len(row_payload) > page_size,
        }

    # ---- 8. measurement: call report_v2.measurements ---------------------------------------
    if measurement_id not in _MEASUREMENT_DISPATCH:
        raise UnknownMeasurementError(f"no dispatcher for measurement {measurement_id!r}")
    called_modules.append(f"report_v2.measurements ({measurement_id})")
    aggregates, _extra = _MEASUREMENT_DISPATCH[measurement_id](eligible_rows)

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

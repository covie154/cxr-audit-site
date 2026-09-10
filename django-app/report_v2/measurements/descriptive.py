# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Pure descriptive helpers for the report_v2 measurement layer.

Everything here is side-effect free: it takes plain values in and hands plain
values (or frozen dataclasses) back out. No Django, ORM, DB, or network imports.

Quantile convention (MANDATORY, used everywhere -- never switched per call site)
    For the ascending-sorted list ``s`` of ``n`` valid values, the p-quantile is
    the LOWER order statistic::

        Q(p) = s[floor(p * (n - 1))]        # 0-based index, clamped to [0, n-1]

    There is NO interpolation between two observations. For ``[1..10, 100]``
    (n = 11) this yields Q1 = 3, median = 6, Q3 = 8 (IQR = 5).

Tukey box rules built on that convention
    * fences: ``Q1 - 1.5 * IQR`` and ``Q3 + 1.5 * IQR``;
    * whiskers are OBSERVED data values, never the fence values: the largest
      observed value ``<= upper fence`` and the smallest observed value ``>= lower fence``;
    * outliers are observed values STRICTLY beyond a fence -- reported in an
      ``outliers`` list and NEVER dropped from ``n`` or the ``mean``;
    * p5 / p95 are SEPARATE tail summaries using the same convention with their own
      method note -- they are not the box whiskers and are not folded into q1/q3.

Duration exclusion policy (never silently read as 0)
    ``None`` counts toward ``excluded_missing``; ``bool`` (a Number subclass, but a
    flag not a duration), non-numeric, non-finite (NaN/inf) and negative durations
    count toward ``excluded_invalid``. Zero is a valid duration.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from numbers import Number

__all__ = [
    "QUANTILE_METHOD",
    "TAIL_METHOD",
    "DescriptiveError",
    "UnexpectedQuantileMethod",
    "DurationSummary",
    "record_count",
    "label_count",
    "categorical_count",
    "duration_summary",
]

#: The one quantile convention this module computes. Callers document it verbatim;
#: a mismatching documented method is rejected rather than silently tolerated.
QUANTILE_METHOD = (
    "lower order statistic: Q(p) = sorted[floor(p * (n - 1))], 0-based, "
    "clamped to [0, n-1], no interpolation"
)

#: Separate method note for the p5/p95 tail summaries. Same convention, but they
#: are reported on their own and never reused as the box whiskers.
TAIL_METHOD = (
    "tail summaries use the same lower-order-statistic convention "
    "(p5 = Q(0.05), p95 = Q(0.95)); reported separately, not the Tukey whiskers"
)


class DescriptiveError(Exception):
    """Base class for typed errors raised by this module."""


class UnexpectedQuantileMethod(DescriptiveError):
    """Raised when a caller documents a quantile method other than ``QUANTILE_METHOD``."""


@dataclass(frozen=True)
class DurationSummary:
    """Frozen summary of a set of durations.

    Every numeric field is ``None`` when there is nothing to summarise (``n == 0``).
    ``excluded_missing`` / ``excluded_invalid`` count the values removed by the
    exclusion policy so callers can see what was dropped without it leaking into
    ``n`` / ``mean``.
    """

    n: int
    excluded_missing: int
    excluded_invalid: int
    min: float | None
    max: float | None
    mean: float | None
    q1: float | None
    median: float | None
    q3: float | None
    iqr: float | None
    lower_fence: float | None
    upper_fence: float | None
    lower_whisker: float | None
    upper_whisker: float | None
    outliers: list
    p5: float | None
    p95: float | None
    quantile_method: str
    tail_method: str
    note: str


def _is_eligible(row: object) -> bool:
    """A row counts when it is present and mapping-like (duck-typed: exposes .get)."""
    return row is not None and hasattr(row, "get")


def record_count(rows: object) -> int:
    """Count eligible rows (present mappings) in an iterable of rows."""
    return sum(1 for row in rows if _is_eligible(row))


def label_count(rows: object, *, label_key: str, vocabulary: object = None) -> dict:
    """Count ``label_key`` values across eligible rows.

    When ``vocabulary`` is provided (an iterable of allowed labels) the result is
    restricted to it: every declared label is present, seeded to ``0``, and only
    declared labels may be counted -- values outside the vocabulary are ignored.
    With ``vocabulary=None`` every observed non-``None`` label is tallied freely.
    """
    counts: dict = {}
    if vocabulary is not None:
        counts = {label: 0 for label in vocabulary}
    for row in rows:
        if not _is_eligible(row):
            continue
        value = row.get(label_key)
        if value is None:
            continue
        if vocabulary is not None and value not in counts:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def categorical_count(rows: object, *, column: str) -> dict:
    """Tally ``column`` values across eligible rows (no vocabulary restriction).

    ``None`` (missing) values are skipped; everything else, including ``""`` and
    ``0``, is counted as its own category.
    """
    counts: dict = {}
    for row in rows:
        if not _is_eligible(row):
            continue
        value = row.get(column)
        if value is None:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _quantile(sorted_vals: list, p: float) -> float:
    """Lower order statistic: ``s[floor(p * (n - 1))]`` clamped to ``[0, n-1]``."""
    n = len(sorted_vals)
    idx = floor(p * (n - 1))
    idx = max(0, min(n - 1, idx))
    return sorted_vals[idx]


def _is_valid_duration(value: object) -> bool:
    """True for a real, finite, non-negative duration; flags/garbage are rejected."""
    if isinstance(value, bool):  # bool is an Integral -- but it is a flag, not a duration
        return False
    if not isinstance(value, Number):
        return False
    try:
        numeric = float(value)
    except (TypeError, ValueError):  # pragma: no cover - exotic Number impls
        return False
    if not isfinite(numeric):
        return False
    return numeric >= 0


def duration_summary(values: object, *, documented_quantile_method: str = QUANTILE_METHOD) -> DurationSummary:
    """Summarise durations with the single, mandatory quantile convention.

    ``documented_quantile_method`` is a guardrail: the numbers are ALWAYS computed
    with ``QUANTILE_METHOD``; if a caller documents a different method the call is
    rejected with :class:`UnexpectedQuantileMethod` so the convention cannot drift.
    """
    if documented_quantile_method != QUANTILE_METHOD:
        raise UnexpectedQuantileMethod(
            f"this module only computes the documented method {QUANTILE_METHOD!r}; "
            f"got {documented_quantile_method!r}"
        )

    excluded_missing = 0
    excluded_invalid = 0
    valid: list = []
    for value in values:
        if value is None:
            excluded_missing += 1
            continue
        if _is_valid_duration(value):
            valid.append(value)
        else:
            excluded_invalid += 1

    n = len(valid)
    if n == 0:
        return DurationSummary(
            n=0,
            excluded_missing=excluded_missing,
            excluded_invalid=excluded_invalid,
            min=None,
            max=None,
            mean=None,
            q1=None,
            median=None,
            q3=None,
            iqr=None,
            lower_fence=None,
            upper_fence=None,
            lower_whisker=None,
            upper_whisker=None,
            outliers=[],
            p5=None,
            p95=None,
            quantile_method=QUANTILE_METHOD,
            tail_method=TAIL_METHOD,
            note="no valid durations; all quantiles and whiskers are None",
        )

    ordered = sorted(valid)
    q1 = _quantile(ordered, 0.25)
    median = _quantile(ordered, 0.50)
    q3 = _quantile(ordered, 0.75)
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr

    # Whiskers: observed values inside the fences, never the fences themselves.
    lower_whisker = min(value for value in ordered if value >= lower_fence)
    upper_whisker = max(value for value in ordered if value <= upper_fence)

    # Outliers: observed values strictly beyond a fence -- reported, never removed.
    outliers = [value for value in ordered if value < lower_fence or value > upper_fence]

    p5 = _quantile(ordered, 0.05)
    p95 = _quantile(ordered, 0.95)

    if n == 1:
        note = "single observation: all quantiles and both whiskers equal that value"
    else:
        note = (
            "tukey box on observed-value whiskers; outliers reported but kept in "
            "n/mean; p5/p95 are separate tail summaries"
        )

    return DurationSummary(
        n=n,
        excluded_missing=excluded_missing,
        excluded_invalid=excluded_invalid,
        min=min(ordered),
        max=max(ordered),
        mean=sum(ordered) / n,
        q1=q1,
        median=median,
        q3=q3,
        iqr=iqr,
        lower_fence=lower_fence,
        upper_fence=upper_fence,
        lower_whisker=lower_whisker,
        upper_whisker=upper_whisker,
        outliers=outliers,
        p5=p5,
        p95=p95,
        quantile_method=QUANTILE_METHOD,
        tail_method=TAIL_METHOD,
        note=note,
    )


if __name__ == "__main__":  # ponytail: one runnable check, not a test file
    # Hand-check from the spec: [1..10, 100] under the lower order statistic.
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100]
    summary = duration_summary(data)
    assert summary.n == 11, summary.n
    assert summary.q1 == 3 and summary.median == 6 and summary.q3 == 8
    assert summary.iqr == 5
    assert summary.lower_fence == 3 - 1.5 * 5
    assert summary.upper_fence == 8 + 1.5 * 5 == 15.5
    assert summary.outliers == [100], summary.outliers
    assert summary.upper_whisker == 10, summary.upper_whisker  # largest obs <= 15.5
    assert summary.lower_whisker == 1, summary.lower_whisker  # smallest obs >= -4.5
    assert summary.p5 == 1 and summary.p95 == 10, (summary.p5, summary.p95)
    assert summary.quantile_method == QUANTILE_METHOD

    # Exclusion policy: None->missing, flags/garbage/negatives->invalid; zero is valid.
    mixed = duration_summary([None, True, "x", float("nan"), float("inf"), -3, 0, 10])
    assert mixed.excluded_missing == 1, mixed.excluded_missing
    assert mixed.excluded_invalid == 5, mixed.excluded_invalid  # True,x,nan,inf,-3
    assert mixed.n == 2, mixed.n
    assert mixed.min == 0 and mixed.max == 10 and mixed.mean == 5.0

    # n == 1 -> everything collapses onto the single value; n == 0 -> all None.
    one = duration_summary([42])
    assert one.q1 == one.median == one.q3 == one.lower_whisker == one.upper_whisker == 42
    assert one.p5 == one.p95 == 42 and one.outliers == []
    assert "single observation" in one.note
    empty = duration_summary([None, "bad"])
    assert empty.n == 0 and empty.min is None and empty.outliers == []

    try:
        duration_summary([1, 2], documented_quantile_method="linear interpolation")
    except UnexpectedQuantileMethod:
        pass
    else:
        raise AssertionError("mismatching quantile method should be rejected")

    rows = [{"label": "a"}, None, {"label": "b"}, {}, {"label": "a"}]
    assert record_count(rows) == 4, record_count(rows)
    assert label_count(rows, label_key="label", vocabulary=["a", "b", "c"]) == {"a": 2, "b": 1, "c": 0}
    assert label_count(rows, label_key="label") == {"a": 2, "b": 1}
    assert categorical_count(rows, column="label") == {"a": 2, "b": 1}
    print("descriptive self-check OK")

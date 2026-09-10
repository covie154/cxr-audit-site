# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Inter-rater agreement helpers for the report_v2 measurements layer.

Pure, stdlib-only helpers (no Django / ORM / DB imports). Three entry points
share ONE row-completeness filter (:func:`complete_rows`) so that Cohen's
kappa, McNemar's test, and the FN/FP case listing all reason over the exact
same complete population:

* :func:`cohen_kappa` -- observed vs expected agreement, returned as a
  :class:`Rate` value object (``value=None`` plus a ``null_reason`` whenever
  the ratio is undefined -- never ``0``).
* :func:`mcnemar` -- exact two-sided binomial McNemar p-value plus the
  continuity-corrected chi-square statistic over the discordant cells.
* :func:`fn_fp_cases` -- canonical false-negative / false-positive id lists
  that page INDEPENDENTLY from each other and from the aggregate counts.

Conventions (fixed, documented, never switched between call sites):

* Direction is FIXED: ``reference`` is the ground truth (``'manual'``),
  ``prediction`` is the model output (``'llm'``).
  A FALSE NEGATIVE is reference-positive & prediction-negative;
  a FALSE POSITIVE is reference-negative & prediction-positive. Never swapped.
* The label vocabulary is exactly two values: ``positive`` and ``negative``
  (default ``1`` / ``0``). Any other value -- ``None``, a missing entry, an
  out-of-the-two-value-vocabulary value, or a ``bool`` where an ``int`` is
  expected -- makes the row INCOMPLETE; such rows are excluded AND counted,
  never coerced to ``0``.
* Ratios here avoid floats where exactness matters: the McNemar p-value and
  the kappa ratios are computed with :class:`fractions.Fraction` and only
  converted to ``float`` at the very end.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Any, Optional, Sequence


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AgreementError(Exception):
    """Base class for every typed error raised by this module."""


class AgreementValidationError(AgreementError):
    """Bad input: length mismatch, bool-where-int, negative/non-sense paging args."""


class AgreementConfigurationError(AgreementError):
    """The caller asked for an impossible analysis direction (e.g. reference == prediction)."""


# ---------------------------------------------------------------------------
# Scalar coercion helpers
# ---------------------------------------------------------------------------


def _as_non_negative_int(value: Any, *, what: str) -> int:
    """Return ``value`` as a plain, non-negative ``int``; ``bool`` is rejected."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgreementValidationError(
            f"{what} must be a plain int (bool is not accepted), "
            f"got {type(value).__name__}: {value!r}"
        )
    if value < 0:
        raise AgreementValidationError(f"{what} must be non-negative, got {value!r}")
    return value


def _as_label(value: Any, *, what: str) -> int:
    """Return ``value`` as a plain ``int`` label (may be negative); ``bool`` rejected."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgreementValidationError(
            f"{what} must be a plain int label (bool is not accepted), "
            f"got {type(value).__name__}: {value!r}"
        )
    return value


def _as_norm_seq(seq: Any, *, what: str) -> list:
    """Materialise an input sequence into a list; reject a raw string/bytes."""
    if isinstance(seq, (str, bytes)):
        raise AgreementValidationError(
            f"{what} must be a sequence of items, not a raw {type(seq).__name__}"
        )
    try:
        return list(seq)
    except TypeError as exc:
        raise AgreementValidationError(f"{what} must be an iterable sequence: {exc}") from exc


# ---------------------------------------------------------------------------
# Shared row-completeness filter (identical for all three entry points)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompleteRows:
    """The common complete population shared by kappa / mcnemar / fn_fp_cases.

    A row is *complete* when the reference label equals ``positive`` or
    ``negative`` AND the prediction label likewise equals ``positive`` or
    ``negative``. Anything else on either side (``None``, a missing entry, an
    out-of-the-two-value-vocabulary value, or a ``bool`` masquerading as an
    ``int``) makes the row incomplete: it is *excluded and counted*, never
    coerced to ``0``.
    """

    total: int
    excluded_incomplete: int
    ref: tuple = ()
    pred: tuple = ()
    ids: Optional[tuple] = None

    @property
    def complete(self) -> int:
        """Number of rows where both sides carry an in-vocabulary label."""
        return len(self.ref)


def complete_rows(
    ref_labels: Sequence[Any],
    pred_labels: Sequence[Any],
    ids: Optional[Sequence[Any]] = None,
    *,
    positive: int = 1,
    negative: int = 0,
) -> CompleteRows:
    """Filter (reference, prediction) pairs down to the common complete population.

    This is the *single* completeness rule used identically by every entry
    point in this module, so kappa, McNemar, and the FN/FP listing always
    agree about which rows they reason over.

    ``positive`` / ``negative`` define the two-value label vocabulary. The
    optional ``ids`` are carried through positionally (kept as opaque,
    unvalidated tokens) so id-based entry points reuse the very same pass.
    """
    positive = _as_label(positive, what="positive")
    negative = _as_label(negative, what="negative")
    if positive == negative:
        raise AgreementValidationError(
            f"positive and negative labels must be distinct, both are {positive!r}"
        )

    refs = _as_norm_seq(ref_labels, what="ref_labels")
    preds = _as_norm_seq(pred_labels, what="pred_labels")
    if len(refs) != len(preds):
        raise AgreementValidationError(
            f"ref_labels and pred_labels must have equal length, got {len(refs)} vs {len(preds)}"
        )

    id_seq: Optional[list] = None
    if ids is not None:
        id_seq = _as_norm_seq(ids, what="ids")
        if len(id_seq) != len(refs):
            raise AgreementValidationError(
                f"ids must have the same length as the label sequences, "
                f"got {len(id_seq)} vs {len(refs)}"
            )

    vocabulary = (positive, negative)
    keep_ref: list = []
    keep_pred: list = []
    keep_ids: Optional[list] = None if id_seq is None else []
    total = len(refs)
    for idx, (r, p) in enumerate(zip(refs, preds)):
        if isinstance(r, bool) or not isinstance(r, int):
            continue
        if isinstance(p, bool) or not isinstance(p, int):
            continue
        if r not in vocabulary or p not in vocabulary:
            continue
        keep_ref.append(r)
        keep_pred.append(p)
        if keep_ids is not None:
            keep_ids.append(id_seq[idx])

    return CompleteRows(
        total=total,
        excluded_incomplete=total - len(keep_ref),
        ref=tuple(keep_ref),
        pred=tuple(keep_pred),
        ids=None if keep_ids is None else tuple(keep_ids),
    )


# ---------------------------------------------------------------------------
# Rate value object (defined locally in this module)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rate:
    """A named ratio that may be undefined.

    A *defined* rate carries ``value`` together with ``null_reason=None``. An
    *undefined* rate carries ``value=None`` together with a non-empty
    ``null_reason`` sentence naming the cause -- an undefined ratio is never
    reported as ``0`` / ``0.0``.

    ``numerator`` is the observed-agreement count and ``denominator`` the
    complete-pair count (plain non-negative ``int`` values) for the Cohen's
    kappa rates produced by this module.
    """

    label: str
    numerator: Optional[int] = None
    denominator: Optional[int] = None
    value: Optional[float] = None
    null_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.numerator is not None:
            _as_non_negative_int(self.numerator, what=f"{self.label} numerator")
        if self.denominator is not None:
            _as_non_negative_int(self.denominator, what=f"{self.label} denominator")
        if self.value is not None:
            if self.null_reason is not None:
                raise AgreementValidationError(
                    f"{self.label}: a defined rate must not carry a null_reason"
                )
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise AgreementValidationError(
                    f"{self.label} value must be a number or None"
                )
        else:
            if not isinstance(self.null_reason, str) or not self.null_reason.strip():
                raise AgreementValidationError(
                    f"{self.label}: an undefined rate must carry a non-empty null_reason"
                )

    @property
    def defined(self) -> bool:
        """True when the ratio has a real value (``value is not None``)."""
        return self.value is not None

    @classmethod
    def with_value(
        cls,
        label: str,
        value: float,
        *,
        numerator: Optional[int] = None,
        denominator: Optional[int] = None,
    ) -> Rate:
        """Build a defined rate (``null_reason`` is forced to ``None``)."""
        return cls(
            label=label,
            numerator=numerator,
            denominator=denominator,
            value=float(value),
            null_reason=None,
        )

    @classmethod
    def without_value(cls, label: str, reason: str) -> Rate:
        """Build an undefined rate carrying ``value=None`` plus a naming reason."""
        if not isinstance(reason, str) or not reason.strip():
            raise AgreementValidationError(
                f"{label}: an undefined rate requires a non-empty null_reason"
            )
        return cls(label=label, value=None, null_reason=reason)


# ---------------------------------------------------------------------------
# Cohen's kappa
# ---------------------------------------------------------------------------

COHEN_KAPPA_LABEL = "Cohen's kappa"


def cohen_kappa(
    ref_labels: Sequence[Any],
    pred_labels: Sequence[Any],
    *,
    positive: int = 1,
    negative: int = 0,
) -> Rate:
    """Cohen's kappa over the common complete population.

    Returns a :class:`Rate`:

    * perfect agreement -> ``value == 1.0`` exactly;
    * empty complete population -> ``value is None`` with a ``null_reason``;
    * degenerate marginals (expected agreement == 1, e.g. every label falls in
      a single class) -> ``value is None`` with a ``null_reason`` -- never ``0``.

    ``numerator`` is the observed-agreement count and ``denominator`` the
    complete-pair count.
    """
    rows = complete_rows(ref_labels, pred_labels, positive=positive, negative=negative)
    complete = rows.complete
    if complete == 0:
        return Rate.without_value(
            COHEN_KAPPA_LABEL,
            "kappa is undefined: the complete population is empty (no pair had both "
            "the reference and the prediction carrying an in-vocabulary label)",
        )

    agree = sum(1 for r, p in zip(rows.ref, rows.pred) if r == p)
    observed = Fraction(agree, complete)

    expected = Fraction(0, 1)
    for lab in sorted({*rows.ref, *rows.pred}):
        p_r = Fraction(sum(1 for r in rows.ref if r == lab), complete)
        p_p = Fraction(sum(1 for p in rows.pred if p == lab), complete)
        expected += p_r * p_p

    if expected == 1:
        return Rate.without_value(
            COHEN_KAPPA_LABEL,
            "kappa is undefined: degenerate marginals give an expected agreement of 1 "
            "(e.g. every label falls in a single class), so the denominator 1 - expected is 0",
        )

    if agree == complete:
        value = 1.0  # exact, documented perfect-agreement result
    else:
        value = float((observed - expected) / (Fraction(1, 1) - expected))

    return Rate.with_value(
        COHEN_KAPPA_LABEL,
        value,
        numerator=agree,
        denominator=complete,
    )


# ---------------------------------------------------------------------------
# McNemar's test
# ---------------------------------------------------------------------------

MCNEMAR_METHOD = (
    "Exact two-sided binomial McNemar test on the discordant cells: "
    "p = 2 * sum(C(n, k) * 0.5 ** n for k <= min(b, c)) with n = b + c, "
    "clipped to 1.0 (computed exactly with fractions). 'statistic' is the "
    "McNemar chi-square with continuity correction, "
    "(abs(b - c) - 1) ** 2 / (b + c)."
)


@dataclass(frozen=True)
class McNemarResult:
    """Outcome of :func:`mcnemar` over the common complete population.

    ``b`` = reference-positive & prediction-negative; ``c`` = reference-negative
    & prediction-positive. When ``n_discordant == 0`` both ``statistic`` and
    ``p_value`` are ``None`` and ``p_note`` names the cause.
    """

    b: int
    c: int
    n_discordant: int
    statistic: Optional[float]
    p_value: Optional[float]
    p_note: Optional[str]
    method: str
    n_total: int
    n_complete: int
    excluded_incomplete: int


def _exact_binomial_lower_tail(n: int, k_max: int) -> Fraction:
    """Exact ``P(X <= k_max)`` for ``X ~ Binomial(n, 1/2)`` as a :class:`Fraction`."""
    half_pow_n = Fraction(1, 2) ** n
    total = Fraction(0, 1)
    for k in range(0, k_max + 1):
        total += Fraction(math.comb(n, k)) * half_pow_n
    return total


def mcnemar(
    ref_labels: Sequence[Any],
    pred_labels: Sequence[Any],
    *,
    positive: int = 1,
    negative: int = 0,
) -> McNemarResult:
    """Exact two-sided McNemar test computed on the common complete rows.

    Uses the very same :func:`complete_rows` filter that feeds kappa and the
    FN/FP listing, so the discordant counts are computed over the identical
    population. ``b`` counts reference-positive/prediction-negative pairs,
    ``c`` counts reference-negative/prediction-positive pairs.
    """
    rows = complete_rows(ref_labels, pred_labels, positive=positive, negative=negative)
    b = sum(1 for r, p in zip(rows.ref, rows.pred) if r == positive and p == negative)
    c = sum(1 for r, p in zip(rows.ref, rows.pred) if r == negative and p == positive)
    n_discordant = b + c

    common = dict(
        b=b,
        c=c,
        n_discordant=n_discordant,
        method=MCNEMAR_METHOD,
        n_total=rows.total,
        n_complete=rows.complete,
        excluded_incomplete=rows.excluded_incomplete,
    )

    if n_discordant == 0:
        if rows.complete == 0:
            note = (
                "McNemar is undefined: the complete population is empty, so there are "
                "no discordant pairs (n_discordant == 0)"
            )
        else:
            note = (
                "McNemar is undefined: there are no discordant pairs "
                "(n_discordant == 0), so b + c is 0 and the test carries no information"
            )
        return McNemarResult(statistic=None, p_value=None, p_note=note, **common)

    # Chi-square with continuity correction (computed exactly, then float).
    statistic = float(Fraction((abs(b - c) - 1) ** 2, n_discordant))

    # Exact two-sided binomial p-value, clipped to 1.0.
    p = 2 * _exact_binomial_lower_tail(n_discordant, min(b, c))
    if p > 1:
        p = Fraction(1, 1)
    return McNemarResult(statistic=statistic, p_value=float(p), p_note=None, **common)


# ---------------------------------------------------------------------------
# FN / FP case listing (independent paging)
# ---------------------------------------------------------------------------

DIRECTION_MANUAL = "manual"
DIRECTION_LLM = "llm"
_VALID_DIRECTIONS = (DIRECTION_MANUAL, DIRECTION_LLM)


def _check_direction(reference: str, prediction: str) -> None:
    """Enforce the FIXED direction (manual reference / llm prediction)."""
    for name, value in (("reference", reference), ("prediction", prediction)):
        if value not in _VALID_DIRECTIONS:
            raise AgreementConfigurationError(
                f"unknown {name} direction name {value!r}; "
                f"valid directions are {_VALID_DIRECTIONS}"
            )
    if reference == prediction:
        raise AgreementConfigurationError(
            f"reference and prediction must name different directions, both are {reference!r}"
        )
    if reference != DIRECTION_MANUAL or prediction != DIRECTION_LLM:
        raise AgreementConfigurationError(
            "direction is fixed: the reference must be 'manual' and the prediction must be 'llm'"
        )


def _normalize_window(name: str, offset: Any, limit: Any) -> tuple:
    """Validate an (offset, limit) paging pair; ``limit=None`` means 'to the end'."""
    off = _as_non_negative_int(offset, what=f"{name} offset")
    if limit is None:
        return off, None
    return off, _as_non_negative_int(limit, what=f"{name} limit")


@dataclass(frozen=True)
class FnFpCases:
    """Canonical FN/FP id lists plus independently paged views over them.

    ``false_negative_ids`` (reference-positive & prediction-negative) and
    ``false_positive_ids`` (reference-negative & prediction-positive) are the
    FULL canonical lists; ``false_negative_count`` / ``false_positive_count``
    are the aggregate counts. The ``*_offset``/``*_limit`` fields configure a
    paging window that applies *only* to the ``false_negative_ids_view`` /
    ``false_positive_ids_view`` properties -- it never truncates the canonical
    lists or the counts. Because the FN and FP offset/limit pairs are
    separate, the two lists page INDEPENDENTLY from each other and from the
    aggregate counts.
    """

    reference: str
    prediction: str
    positive: int
    negative: int

    n_total: int
    n_complete: int
    excluded_incomplete: int

    false_negative_ids: tuple = ()
    false_positive_ids: tuple = ()
    false_negative_count: int = 0
    false_positive_count: int = 0

    false_negative_offset: Optional[int] = None
    false_negative_limit: Optional[int] = None
    false_positive_offset: Optional[int] = None
    false_positive_limit: Optional[int] = None

    def __post_init__(self) -> None:
        _check_direction(self.reference, self.prediction)
        if self.false_negative_offset is not None:
            _as_non_negative_int(self.false_negative_offset, what="false_negative offset")
        if self.false_negative_limit is not None:
            _as_non_negative_int(self.false_negative_limit, what="false_negative limit")
        if self.false_positive_offset is not None:
            _as_non_negative_int(self.false_positive_offset, what="false_positive offset")
        if self.false_positive_limit is not None:
            _as_non_negative_int(self.false_positive_limit, what="false_positive limit")

    @staticmethod
    def _slice(seq: tuple, offset: Optional[int], limit: Optional[int]) -> tuple:
        start = offset or 0
        end = None if limit is None else start + limit
        return tuple(seq[start:end])

    @property
    def false_negative_ids_view(self) -> tuple:
        """Paged window over the canonical false-negative ids."""
        return self._slice(
            self.false_negative_ids, self.false_negative_offset, self.false_negative_limit
        )

    @property
    def false_positive_ids_view(self) -> tuple:
        """Paged window over the canonical false-positive ids."""
        return self._slice(
            self.false_positive_ids, self.false_positive_offset, self.false_positive_limit
        )

    def with_paging(
        self,
        *,
        fn_offset: Optional[int] = None,
        fn_limit: Optional[int] = None,
        fp_offset: Optional[int] = None,
        fp_limit: Optional[int] = None,
    ) -> FnFpCases:
        """Return a copy with independent FN / FP paging windows set.

        Each list's window is controlled by its own ``offset``/``limit`` pair,
        so the false-negative and false-positive views page separately from
        one another and from the aggregate counts. Leaving *both* members of a
        pair at ``None`` leaves that list's window untouched (so you can re-page
        one list without disturbing the other). To widen a window back to the
        full range pass ``<x>_offset=0`` together with ``<x>_limit=None``.
        """
        changes: dict = {}
        if fn_offset is not None or fn_limit is not None:
            off, lim = _normalize_window(
                "false_negative", 0 if fn_offset is None else fn_offset, fn_limit
            )
            changes["false_negative_offset"] = off
            changes["false_negative_limit"] = lim
        if fp_offset is not None or fp_limit is not None:
            off, lim = _normalize_window(
                "false_positive", 0 if fp_offset is None else fp_offset, fp_limit
            )
            changes["false_positive_offset"] = off
            changes["false_positive_limit"] = lim
        return replace(self, **changes)


def fn_fp_cases(
    ref_labels: Sequence[Any],
    pred_labels: Sequence[Any],
    ids: Sequence[Any],
    *,
    reference: str = DIRECTION_MANUAL,
    prediction: str = DIRECTION_LLM,
    positive: int = 1,
    negative: int = 0,
    fn_offset: int = 0,
    fn_limit: Optional[int] = None,
    fp_offset: int = 0,
    fp_limit: Optional[int] = None,
) -> FnFpCases:
    """Collect canonical FN/FP id lists using the shared complete-row filter.

    Direction is FIXED: ``reference`` is ``'manual'`` (the ground truth) and
    ``prediction`` is ``'llm'`` (the model). A FALSE NEGATIVE is
    reference-positive & prediction-negative; a FALSE POSITIVE is
    reference-negative & prediction-positive. Passing ``reference == prediction``
    or an unknown direction name raises :class:`AgreementConfigurationError`.

    Incomplete pairs (``None``/missing/out-of-the-two-value-vocabulary on either
    side, or a ``bool`` where an ``int`` is expected) are *excluded and counted*
    via ``excluded_incomplete`` and are never coerced. The returned
    :class:`FnFpCases` carries the full canonical lists plus aggregate counts,
    and exposes ``false_negative_ids_view`` / ``false_positive_ids_view``
    windows whose offsets/limits are set independently -- so the two lists page
    separately from each other and from the counts.
    """
    _check_direction(reference, prediction)

    fn_off, fn_lim = _normalize_window("fn", fn_offset, fn_limit)
    fp_off, fp_lim = _normalize_window("fp", fp_offset, fp_limit)

    rows = complete_rows(ref_labels, pred_labels, ids, positive=positive, negative=negative)
    assert rows.ids is not None  # ids were supplied -> carried through positionally

    fn_ids: list = []
    fp_ids: list = []
    for r, p, ident in zip(rows.ref, rows.pred, rows.ids):
        if r == positive and p == negative:
            fn_ids.append(ident)
        elif r == negative and p == positive:
            fp_ids.append(ident)

    return FnFpCases(
        reference=reference,
        prediction=prediction,
        positive=positive,
        negative=negative,
        n_total=rows.total,
        n_complete=rows.complete,
        excluded_incomplete=rows.excluded_incomplete,
        false_negative_ids=tuple(fn_ids),
        false_positive_ids=tuple(fp_ids),
        false_negative_count=len(fn_ids),
        false_positive_count=len(fp_ids),
        false_negative_offset=fn_off,
        false_negative_limit=fn_lim,
        false_positive_offset=fp_off,
        false_positive_limit=fp_lim,
    )

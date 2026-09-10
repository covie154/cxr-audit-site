# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Pure, side-effect-free classification measurement primitives for the report-v2 layer.

This module turns *already-extracted* ground-truth / prediction **class values** (plain Python data, never
ORM rows) into immutable confusion counts and rate value objects: binary counts, the seven binary rates,
an NxN confusion matrix with a *stable declared* class order, target-class one-versus-rest rates and a
single aggregate entry point. It deliberately contains **no** web-framework import, no ORM import and no
database access -- these are *computed values*, not stored columns, and nothing here may touch persisted
state, the filesystem or the network. It depends only on the standard library and the pure frozen
dataclasses in :mod:`report_v2.projects.base`.

Design rules relied upon by the rest of the layer (mirroring :mod:`report_v2.measurements.predictions`):

* Every ratio is a :class:`Rate` built through :func:`safe_rate`, the single gate implementing the
  "null plus a reason, never a zero" contract: a rate whose denominator is zero is ``value=None`` with a
  non-empty ``null_reason``, and a *legitimate* ``0.0`` (a real zero over a positive denominator) stays a
  defined ``0.0``. The two are never conflated.
* Confusion matrices declare ``rows_are="ground_truth"`` / ``columns_are="prediction"`` and are laid out by
  the **declared** ``classes`` sequence the caller supplies -- never by data-encounter order -- so the matrix
  geometry is stable and reproducible regardless of how rows arrive.
* A multiclass sensitivity / PPV must name an explicit ``target_class`` (one versus rest). There is no
  silent per-class averaging and no unqualified multiclass rate: :func:`require_target_class` fails
  validation *before* any counting happens.
* ``pairs_from_rows`` / :func:`binary_confusion_counts` treat a ``None`` value as *absent*: such a pair is
  EXCLUDED under a non-overlapping reason (ground truth takes precedence), never coerced to the negative
  class, so ``matching == eligible + exclusions`` always reconciles.
* Score-based ranking metrics (which would require a continuous score source and a defined score-ranking
  implementation) are out of scope for this release. The mean of sensitivity and specificity is reported as
  :data:`BALANCED_ACCURACY_LABEL` -- it is *balanced accuracy*, not a ranking metric -- and no cross-class
  macro average of per-class rates is produced anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping, Sequence

__all__ = [
    "ClassificationError",
    "OutOfVocabularyClassError",
    "MissingTargetClassError",
    "InvalidClassOrderError",
    "IncompatiblePairError",
    "EmptyPopulationError",
    "BALANCED_ACCURACY_LABEL",
    "BinaryClassVocabulary",
    "vocabulary_from_outcome",
    "pairs_from_rows",
    "BinaryConfusionCounts",
    "binary_confusion_counts",
    "Rate",
    "safe_rate",
    "BinaryClassificationMetrics",
    "binary_classification_metrics",
    "ConfusionMatrix",
    "confusion_matrix",
    "TargetClassMetrics",
    "one_vs_rest_metrics",
    "require_target_class",
    "ClassificationSummary",
    "classification_summary",
]

#: The honest label for ``(sensitivity + specificity) / 2``. This is *balanced accuracy*; it is a mean of
#: two recall-style rates, not a score-ranking statistic, and must never be relabelled as such.
BALANCED_ACCURACY_LABEL = "Balanced accuracy"


# ---------------------------------------------------------------------------
# Error model (mirrors the predictions.PolicyEvaluationError / base.ProjectCatalogError shape).
# ---------------------------------------------------------------------------
class ClassificationError(Exception):
    """Common base for every classification-measurement rejection.

    Carries a single human ``message`` plus a stable machine-readable ``kind`` discriminator that subclasses
    override. The string form prefixes the message with the ``kind`` so logs and editors can triage without
    parsing. The constructor is ``Exception.__init__(message)``-compatible, so a subclass is built with a
    single positional message (``OutOfVocabularyClassError("...")``).
    """

    kind = "classification"

    def __init__(self, message: str) -> None:
        self.message = str(message)
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.kind}] {self.message}"


class OutOfVocabularyClassError(ClassificationError):
    """A ground-truth or prediction value was outside the declared class vocabulary."""

    kind = "out-of-vocabulary-class"


class MissingTargetClassError(ClassificationError):
    """A multiclass one-versus-rest rate was requested without naming an explicit target class."""

    kind = "missing-target-class"


class InvalidClassOrderError(ClassificationError):
    """The declared class order was empty, duplicated or otherwise not usable as an authoritative sequence."""

    kind = "invalid-class-order"


class IncompatiblePairError(ClassificationError):
    """A row could not be lifted into a ``(ground_truth, prediction)`` pair, or a pairs container was malformed."""

    kind = "incompatible-pairs"


class EmptyPopulationError(ClassificationError):
    """No pairs at all were supplied to a counting entry point (distinct from rows present but all excluded)."""

    kind = "empty-population"


class _InvalidRateOperandError(ClassificationError):
    """A :func:`safe_rate` operand was negative, a ``bool`` or otherwise not a plain non-negative ``int``."""

    kind = "invalid-rate-operand"


class _InvalidVocabularyError(ClassificationError):
    """A :class:`BinaryClassVocabulary` declared identical positive and negative classes."""

    kind = "invalid-vocabulary"


class _InvalidSummaryRequestError(ClassificationError):
    """A :func:`classification_summary` request supplied neither, or both, of ``vocabulary`` / ``classes``."""

    kind = "invalid-summary-request"


# ---------------------------------------------------------------------------
# Shared guards / helpers
# ---------------------------------------------------------------------------
def _is_plain_int(value: object) -> bool:
    """True only for a genuine ``int`` -- ``bool`` is explicitly rejected.

    ``bool`` is a subclass of ``int`` in Python, so ``isinstance(True, int)`` is ``True``; a ``True`` /
    ``False`` is never a count and must not be silently read as ``1`` / ``0``.
    """
    return isinstance(value, int) and not isinstance(value, bool)


def _is_sized_sequence(obj: object) -> bool:
    """True for a non-string, indexable container exposing ``len`` (a list/tuple/etc., not a Mapping)."""
    if isinstance(obj, (str, bytes, bytearray)):
        return False
    if isinstance(obj, Mapping):
        return False
    return isinstance(obj, Sequence) and hasattr(obj, "__len__")


def _validate_pair(pair: object) -> "tuple[object, object]":
    """Normalise one ``(ground_truth, prediction)`` entry, rejecting malformed containers.

    A pair must be a 2-item sequence (not a bare string/Mapping). A ``str`` / ``bytes`` row is rejected
    outright so a two-character token is never mistaken for a two-slot pair.
    """
    if isinstance(pair, (str, bytes, bytearray)) or isinstance(pair, Mapping):
        raise IncompatiblePairError(f"pair is not a 2-item sequence: {pair!r}")
    if not isinstance(pair, Sequence) or len(pair) != 2:
        raise IncompatiblePairError(f"pair is not a 2-item sequence: {pair!r}")
    return (pair[0], pair[1])


def _validate_pairs_container(pairs: object, *, fn: str) -> Sequence:
    """Require ``pairs`` to be a sized sequence; an entirely empty population is a caller error.

    ``matching == 0`` (literally no rows) is reported as :class:`EmptyPopulationError` -- that is distinct
    from "rows were supplied but every one was excluded", which legitimately yields ``eligible == 0`` and
    undefined rates.
    """
    if not _is_sized_sequence(pairs):
        raise IncompatiblePairError(f"{fn} expects a sized sequence of (ground_truth, prediction) pairs")
    if len(pairs) == 0:
        raise EmptyPopulationError(f"{fn} received an empty population (no pairs to classify)")
    return pairs


# ---------------------------------------------------------------------------
# The Rate primitive -- every ratio in this module flows through safe_rate.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Rate:
    """An immutable ratio together with the null-plus-reason contract enforced by :func:`safe_rate`.

    ``value`` is ``None`` exactly when the rate is undefined (a zero denominator), and in that case
    ``null_reason`` is a non-empty sentence. A genuine ``0.0`` (a real zero over a positive denominator)
    is ``defined`` with ``null_reason`` left as ``None`` -- the two states are never conflated.
    """

    label: str
    numerator: int | None
    denominator: int | None
    value: float | None
    null_reason: str | None

    @property
    def defined(self) -> bool:
        """True when the rate has a concrete value (i.e. its denominator was positive)."""
        return self.value is not None

    def as_dict(self) -> dict:
        """Return a deterministic, JSON-friendly snapshot of this single rate."""
        return {
            "label": self.label,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "value": self.value,
            "null_reason": self.null_reason,
            "defined": self.defined,
        }


def safe_rate(label: str, numerator: int, denominator: int) -> Rate:
    """Build a :class:`Rate`, implementing the "null plus a reason, never a zero" contract.

    A zero denominator produces ``value=None`` carrying the true ``numerator`` (usually ``0``) so nothing is
    hidden, plus a non-empty ``null_reason`` that names the rate and states the zero denominator. A positive
    denominator produces ``value = numerator / denominator`` as a ``float``. Operands must be non-negative
    ``int`` values; a ``bool`` or any non-``int`` / negative operand is rejected (``bool`` is an ``int``
    subclass and is refused deliberately, mirroring :func:`_is_plain_int`).
    """
    if not _is_plain_int(numerator) or not _is_plain_int(denominator):
        raise _InvalidRateOperandError(
            f"rate {label!r} operands must be non-negative ints, got "
            f"numerator={numerator!r} ({type(numerator).__name__}) / "
            f"denominator={denominator!r} ({type(denominator).__name__})"
        )
    if numerator < 0 or denominator < 0:
        raise _InvalidRateOperandError(
            f"rate {label!r} operands must be non-negative, got numerator={numerator!r} / denominator={denominator!r}"
        )
    if denominator == 0:
        reason = (
            f"{label} is undefined: zero denominator "
            f"(no eligible cases contribute to this rate in the measured population)"
        )
        return Rate(label=label, numerator=numerator, denominator=0, value=None, null_reason=reason)
    return Rate(
        label=label,
        numerator=numerator,
        denominator=denominator,
        value=numerator / denominator,
        null_reason=None,
    )


def _average_of_two(label: str, first: Rate, second: Rate) -> Rate:
    """Average two defined rates exactly (as rationals), or report the average undefined.

    If either input rate is undefined the combined rate is undefined too, with a ``null_reason`` naming the
    offending component. Otherwise the two rates are added as exact :class:`fractions.Fraction` values taken
    from their stored ``numerator`` / ``denominator`` (never from the rounded float) and divided by ``2``; the
    resulting rational's numerator / denominator are carried verbatim so ``2/3`` stays exactly ``2/3``.
    """
    if first.value is None:
        reason = (
            f"{label} is undefined because its component {first.label!r} ({first.null_reason}) "
            f"is itself undefined"
        )
        return Rate(label=label, numerator=0, denominator=0, value=None, null_reason=reason)
    if second.value is None:
        reason = (
            f"{label} is undefined because its component {second.label!r} ({second.null_reason}) "
            f"is itself undefined"
        )
        return Rate(label=label, numerator=0, denominator=0, value=None, null_reason=reason)
    average = (Fraction(first.numerator, first.denominator) + Fraction(second.numerator, second.denominator)) / 2
    return safe_rate(label, average.numerator, average.denominator)


# ---------------------------------------------------------------------------
# Binary class vocabulary (strictly binary at this layer).
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinaryClassVocabulary:
    """The two declared classes of a binary outcome, in the authoritative ``positive, negative`` order."""

    positive_class: object
    negative_class: object
    label: str = ""

    def __post_init__(self) -> None:
        if self.positive_class == self.negative_class:
            raise _InvalidVocabularyError(
                f"binary vocabulary declares identical positive/negative classes {self.positive_class!r}"
            )

    @property
    def classes(self) -> "tuple[object, object]":
        """The stable declared order: ``(positive_class, negative_class)``."""
        return (self.positive_class, self.negative_class)


def vocabulary_from_outcome(outcome) -> BinaryClassVocabulary:
    """Derive a :class:`BinaryClassVocabulary` from a :class:`report_v2.projects.base.Outcome`.

    The outcome must declare exactly two classes; the positive class is taken straight from
    ``outcome.positive_class`` and the negative class is the other member of the two-tuple. An outcome that
    is not binary raises :class:`InvalidClassOrderError` -- this layer is strictly binary and multiclass
    callers use an explicit ``classes`` sequence instead. There is no registry lookup and no database access.
    """
    classes = tuple(outcome.classes)
    if len(classes) != 2:
        raise InvalidClassOrderError(
            f"outcome {getattr(outcome, 'outcome_id', '?')!r} declares {len(classes)} classes "
            f"{classes!r}; a binary vocabulary requires exactly two"
        )
    positive = outcome.positive_class
    negative = next(cls for cls in classes if cls != positive)
    return BinaryClassVocabulary(positive_class=positive, negative_class=negative, label=outcome.outcome_id)


# ---------------------------------------------------------------------------
# Row lifting -> pairs.
# ---------------------------------------------------------------------------
def pairs_from_rows(rows, *, ground_truth_key, prediction_key) -> "tuple[tuple[object, object], ...]":
    """Lift already-extracted row values into an ordered ``(ground_truth, prediction)`` pair tuple.

    ``rows`` may be a sequence of :class:`~collections.abc.Mapping` (the in-memory dicts the test factories
    emit) or a sequence of 2-item sequences/tuples. Mapping rows must carry both declared keys (a missing key
    fails with :class:`IncompatiblePairError` naming the key); the values are passed straight through so a
    ``None`` -- meaning *absent*, handled downstream -- is preserved and never coerced. The input is never
    mutated. Anything that is neither a Mapping nor a 2-item sequence is rejected.
    """
    if not _is_sized_sequence(rows):
        raise IncompatiblePairError("rows must be a sized sequence of mappings or 2-item sequences")
    lifted: list[tuple[object, object]] = []
    for index, row in enumerate(rows):
        if isinstance(row, Mapping):
            if ground_truth_key not in row:
                raise IncompatiblePairError(f"row {index} is missing the ground-truth key {ground_truth_key!r}")
            if prediction_key not in row:
                raise IncompatiblePairError(f"row {index} is missing the prediction key {prediction_key!r}")
            lifted.append((row[ground_truth_key], row[prediction_key]))
        else:
            gt, pred = _validate_pair(row)
            lifted.append((gt, pred))
    return tuple(lifted)


def _exclusion_reason(ground_truth: object, prediction: object) -> "str | None":
    """Return the single non-overlapping exclusion reason for an absent slot, else ``None``.

    Ground truth takes precedence so a row absent on both sides is counted once, keeping the reason buckets
    disjoint and the ``matching == eligible + exclusions`` reconciliation exact.
    """
    if ground_truth is None:
        return "missing_ground_truth"
    if prediction is None:
        return "missing_prediction"
    return None


def _require_class_in_vocab(value: object, *, classes: "tuple[object, ...]", side: str, fn_hint: str) -> None:
    """Validate one non-absent class value against the declared ``classes`` vocabulary.

    A ``bool`` is refused unless some declared class is itself a ``bool`` that the value literally equals --
    ``True`` is never silently read as the integer ``1``. Any other value outside the declared vocabulary
    raises :class:`OutOfVocabularyClassError` naming the value, the side it was on and the declared classes.
    """
    if isinstance(value, bool):
        declared_has_bool = any(isinstance(member, bool) for member in classes)
        if not declared_has_bool or value not in classes:
            raise OutOfVocabularyClassError(
                f"{side} value {value!r} is a bool and is not a declared class of {classes!r} "
                f"(bools are never coerced to ints) in {fn_hint}"
            )
        return
    if value not in classes:
        raise OutOfVocabularyClassError(
            f"{side} value {value!r} is outside the declared classes {classes!r} in {fn_hint}"
        )


# ---------------------------------------------------------------------------
# Binary confusion counts.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinaryConfusionCounts:
    """Immutable binary confusion counts together with the eligibility / exclusion accounting.

    ``eligible`` is the number of counted pairs (``tp + fn + fp + tn``) and is the *group n*; the per-rate
    denominators (positive / negative case counts, predicted positive / negative counts) are derived from
    the four cells and are kept **distinct** from ``eligible``. ``excluded`` maps each non-overlapping reason
    to its count and reconciles exactly via ``matching == eligible + exclusions``.
    """

    tp: int
    fn: int
    fp: int
    tn: int
    eligible: int
    matching: int
    excluded: Mapping[str, int]

    @property
    def positive_cases(self) -> int:
        """The sensitivity denominator ``tp + fn`` (distinct from ``eligible``)."""
        return self.tp + self.fn

    @property
    def predicted_positives(self) -> int:
        """The PPV denominator ``tp + fp``."""
        return self.tp + self.fp

    @property
    def negative_cases(self) -> int:
        """The specificity denominator ``tn + fp``."""
        return self.tn + self.fp

    @property
    def predicted_negatives(self) -> int:
        """``tn + fn`` -- the numerator of the predicted-negative fraction."""
        return self.tn + self.fn

    @property
    def exclusions(self) -> int:
        """Total excluded pairs == ``matching - eligible`` == sum of the reason counts."""
        return self.matching - self.eligible

    def as_dict(self) -> dict:
        """Return a deterministic, JSON-friendly snapshot (``excluded`` as a plain dict)."""
        return {
            "tp": self.tp,
            "fn": self.fn,
            "fp": self.fp,
            "tn": self.tn,
            "eligible": self.eligible,
            "matching": self.matching,
            "exclusions": self.exclusions,
            "positive_cases": self.positive_cases,
            "predicted_positives": self.predicted_positives,
            "negative_cases": self.negative_cases,
            "predicted_negatives": self.predicted_negatives,
            "excluded": {reason: self.excluded[reason] for reason in sorted(self.excluded) if self.excluded[reason]},
        }


def binary_confusion_counts(pairs, *, vocabulary: BinaryClassVocabulary) -> BinaryConfusionCounts:
    """Count a binary ``(ground_truth, prediction)`` population into ``tp/fn/fp/tn`` with exclusion accounting.

    ``pairs`` must be a sized sequence of 2-item sequences. For each pair an absent ground truth is excluded
    as ``missing_ground_truth`` (taking precedence over an absent prediction), otherwise an absent prediction
    is excluded as ``missing_prediction``; excluded pairs are never counted as a negative nor coerced. A
    non-absent value outside ``vocabulary.classes`` raises :class:`OutOfVocabularyClassError` naming the value,
    its side and the declared vocabulary.
    """
    _validate_pairs_container(pairs, fn="binary_confusion_counts")
    classes = vocabulary.classes
    positive = vocabulary.positive_class
    negative = vocabulary.negative_class
    matching = len(pairs)
    tp = fn = fp = tn = 0
    excluded: dict[str, int] = {}

    for raw in pairs:
        gt, pred = _validate_pair(raw)
        reason = _exclusion_reason(gt, pred)
        if reason is not None:
            excluded[reason] = excluded.get(reason, 0) + 1
            continue
        _require_class_in_vocab(gt, classes=classes, side="ground truth", fn_hint="binary_confusion_counts")
        _require_class_in_vocab(pred, classes=classes, side="prediction", fn_hint="binary_confusion_counts")
        if gt == positive and pred == positive:
            tp += 1
        elif gt == positive and pred == negative:
            fn += 1
        elif gt == negative and pred == positive:
            fp += 1
        else:  # gt == negative and pred == negative
            tn += 1

    eligible = tp + fn + fp + tn
    return BinaryConfusionCounts(
        tp=tp, fn=fn, fp=fp, tn=tn,
        eligible=eligible, matching=matching, excluded=excluded,
    )


# ---------------------------------------------------------------------------
# The seven binary rates.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BinaryClassificationMetrics:
    """The binary confusion counts paired with the seven documented classification rates.

    Every rate is a :class:`Rate` built only from ``counts`` via :func:`safe_rate` (and, for balanced
    accuracy, :func:`_average_of_two` over sensitivity / specificity). ``rate(name)`` and ``rates`` expose
    them by the seven canonical metric names so downstream consumers -- and the aggregate entry point -- read
    a single source of truth instead of re-deriving any arithmetic.
    """

    counts: BinaryConfusionCounts
    accuracy: Rate
    sensitivity: Rate
    specificity: Rate
    ppv: Rate
    npv: Rate
    balanced_accuracy: Rate
    predicted_negative_fraction: Rate

    _RATE_NAMES = (
        "accuracy",
        "sensitivity",
        "specificity",
        "ppv",
        "npv",
        "balanced_accuracy",
        "predicted_negative_fraction",
    )

    def rate(self, name: str) -> Rate:
        """Return the named rate; an unknown metric name is rejected."""
        if name not in BinaryClassificationMetrics._RATE_NAMES:
            raise ClassificationError(
                f"unknown binary metric {name!r}; expected one of {list(BinaryClassificationMetrics._RATE_NAMES)}"
            )
        return getattr(self, name)

    @property
    def rates(self) -> "Mapping[str, Rate]":
        """The seven rates keyed by their canonical names, in the documented order."""
        return {name: getattr(self, name) for name in BinaryClassificationMetrics._RATE_NAMES}

    def as_dict(self) -> dict:
        """Return a deterministic, JSON-friendly snapshot of the counts and all seven rates."""
        view = {"counts": self.counts.as_dict()}
        for name in BinaryClassificationMetrics._RATE_NAMES:
            view[name] = getattr(self, name).as_dict()
        return view


def binary_classification_metrics(pairs, *, vocabulary: BinaryClassVocabulary) -> BinaryClassificationMetrics:
    """Compute the binary confusion counts and the seven rates from them.

    The counts come straight from :func:`binary_confusion_counts` and every rate is derived from those counts
    alone -- there is no second counting implementation and no re-derivation of cells anywhere. Balanced
    accuracy averages the *already computed* sensitivity and specificity rates as exact rationals via
    :func:`_average_of_two`, so it stays undefined (never zero) if either component is undefined.
    """
    counts = binary_confusion_counts(pairs, vocabulary=vocabulary)
    accuracy = safe_rate("Accuracy", counts.tp + counts.tn, counts.eligible)
    sensitivity = safe_rate("Sensitivity", counts.tp, counts.positive_cases)
    specificity = safe_rate("Specificity", counts.tn, counts.negative_cases)
    ppv = safe_rate("PPV", counts.tp, counts.predicted_positives)
    npv = safe_rate("NPV", counts.tn, counts.predicted_negatives)
    balanced = _average_of_two(BALANCED_ACCURACY_LABEL, sensitivity, specificity)
    predicted_negative_fraction = safe_rate(
        "Predicted negative fraction", counts.predicted_negatives, counts.eligible
    )
    return BinaryClassificationMetrics(
        counts=counts,
        accuracy=accuracy,
        sensitivity=sensitivity,
        specificity=specificity,
        ppv=ppv,
        npv=npv,
        balanced_accuracy=balanced,
        predicted_negative_fraction=predicted_negative_fraction,
    )


# ---------------------------------------------------------------------------
# NxN confusion matrix with a stable declared class order.
# ---------------------------------------------------------------------------
def _validate_class_order(classes, *, fn: str) -> "tuple[object, ...]":
    """Normalise + validate the declared ``classes`` into an authoritative tuple.

    The declared order must be a non-empty sequence with no duplicates and every member hashable, so the
    matrix geometry is driven by the *declared* order rather than the order rows happen to be encountered in.
    An empty or duplicated declaration -- or an unhashable member (the natural cause is a nested list) -- is
    reported as :class:`InvalidClassOrderError` (the non-hashable case is deliberately grouped here, since
    the class order itself, not a value being classified, is what is malformed).
    """
    if isinstance(classes, (str, bytes, bytearray)) or isinstance(classes, Mapping) or not isinstance(classes, Sequence):
        raise InvalidClassOrderError(f"{fn} requires a sequence of declared classes, got {classes!r}")
    declared = tuple(classes)
    if not declared:
        raise InvalidClassOrderError(f"{fn} requires a non-empty declared class order")
    try:
        distinct = set(declared)
    except TypeError as exc:  # an unhashable member -- the class order itself is malformed.
        raise InvalidClassOrderError(
            f"{fn} declared class order contains an unhashable member {exc}: {classes!r}"
        ) from None
    if len(distinct) != len(declared):
        raise InvalidClassOrderError(f"{fn} declared class order contains duplicates: {declared!r}")
    return declared


@dataclass(frozen=True)
class ConfusionMatrix:
    """An immutable NxN confusion matrix laid out with rows = ground truth, columns = prediction.

    ``classes`` is the authoritative declared order; ``cells[i][j]`` counts the pairs whose ground truth is
    ``classes[i]`` and whose prediction is ``classes[j]``. Only the counts and the trace-based accuracy live
    here -- no aggregate is averaged across classes -- so this object stays a pure counting surface.
    """

    classes: "tuple[str, ...]"
    cells: "tuple[tuple[int, ...], ...]"
    rows_are: str = "ground_truth"
    columns_are: str = "prediction"

    @property
    def row_totals(self) -> "tuple[int, ...]":
        """Per ground-truth class totals (one per declared row)."""
        return tuple(sum(row) for row in self.cells)

    @property
    def column_totals(self) -> "tuple[int, ...]":
        """Per prediction-class totals (one per declared column)."""
        return tuple(sum(row[j] for row in self.cells) for j in range(len(self.classes)))

    @property
    def n(self) -> int:
        """Total number of counted (eligible) pairs == sum over every cell."""
        return sum(sum(row) for row in self.cells)

    @property
    def trace(self) -> int:
        """Sum of the diagonal cells (agreements between ground truth and prediction)."""
        return sum(self.cells[i][i] for i in range(len(self.classes)))

    @property
    def accuracy(self) -> Rate:
        """Trace over ``n`` -- the plain matrix accuracy, null (never zero) when ``n`` is zero."""
        return safe_rate("Accuracy", self.trace, self.n)

    def cell(self, ground_truth, prediction) -> int:
        """Return the count for one (ground truth, prediction) cell, validating membership first."""
        try:
            i = self.classes.index(ground_truth)
        except ValueError:
            raise OutOfVocabularyClassError(
                f"ground truth value {ground_truth!r} is outside the declared classes {self.classes!r} in cell()"
            ) from None
        try:
            j = self.classes.index(prediction)
        except ValueError:
            raise OutOfVocabularyClassError(
                f"prediction value {prediction!r} is outside the declared classes {self.classes!r} in cell()"
            ) from None
        return self.cells[i][j]

    def as_dict(self) -> dict:
        """Return a deterministic, JSON-friendly snapshot of the matrix geometry and its accuracy."""
        return {
            "classes": list(self.classes),
            "rows_are": self.rows_are,
            "columns_are": self.columns_are,
            "cells": [list(row) for row in self.cells],
            "row_totals": list(self.row_totals),
            "column_totals": list(self.column_totals),
            "n": self.n,
            "accuracy": self.accuracy.as_dict(),
        }


def _matrix(classes: "tuple[object, ...]", pairs) -> ConfusionMatrix:
    """Build the NxN matrix once -- the single confusion-counting implementation used by every matrix caller.

    Validates the declared class order, lifts each pair, excludes absent slots under the same disjoint
    reasons as the binary case, rejects any other out-of-vocabulary value, and bins the survivors by the
    *declared* order. ``one_vs_rest_metrics`` and ``classification_summary`` both go through here so there is
    exactly one place that turns pairs into cells.
    """
    _validate_pairs_container(pairs, fn="confusion matrix")
    size = len(classes)
    index = {cls: position for position, cls in enumerate(classes)}
    cells = [[0] * size for _ in range(size)]

    for raw in pairs:
        gt, pred = _validate_pair(raw)
        if gt is None or pred is None:
            continue  # absent slot -- excluded (missing ground truth / missing prediction), never counted.
        _require_class_in_vocab(gt, classes=classes, side="ground truth", fn_hint="confusion matrix")
        _require_class_in_vocab(pred, classes=classes, side="prediction", fn_hint="confusion matrix")
        cells[index[gt]][index[pred]] += 1

    return ConfusionMatrix(
        classes=tuple(classes),
        cells=tuple(tuple(row) for row in cells),
    )


def confusion_matrix(pairs, *, classes: "Sequence[str]") -> ConfusionMatrix:
    """Build an NxN confusion matrix over an explicitly declared ``classes`` order.

    The declared order is validated immediately (non-empty, unique, hashable) and becomes the authoritative
    geometry. Non-absent values outside the declaration raise :class:`OutOfVocabularyClassError`; absent slots
    are excluded exactly as in the binary case. ``n`` is the eligible count and ``accuracy`` is null (never
    zero) when ``n`` is zero.
    """
    declared = _validate_class_order(classes, fn="confusion_matrix")
    return _matrix(declared, pairs)


# ---------------------------------------------------------------------------
# Target-class one-versus-rest rates.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TargetClassMetrics:
    """The one-versus-rest counts and rates for a single explicitly named target class.

    The counts are derived from the shared matrix: ``tp`` is the target diagonal cell, ``fn`` the rest of the
    target row, ``fp`` the rest of the target column and ``tn`` the remainder. Every rate flows through
    :func:`safe_rate`, so a zero denominator is ``None`` plus a reason -- never ``0``.
    """

    target_class: str
    classes: "tuple[str, ...]"
    tp: int
    fn: int
    fp: int
    tn: int
    positive_cases: int
    negative_cases: int
    predicted_positives: int
    predicted_negatives: int
    eligible: int
    sensitivity: Rate
    specificity: Rate
    ppv: Rate
    npv: Rate

    def as_dict(self) -> dict:
        """Return a deterministic, JSON-friendly snapshot of this target-class view."""
        return {
            "target_class": self.target_class,
            "classes": list(self.classes),
            "tp": self.tp,
            "fn": self.fn,
            "fp": self.fp,
            "tn": self.tn,
            "positive_cases": self.positive_cases,
            "negative_cases": self.negative_cases,
            "predicted_positives": self.predicted_positives,
            "predicted_negatives": self.predicted_negatives,
            "eligible": self.eligible,
            "sensitivity": self.sensitivity.as_dict(),
            "specificity": self.specificity.as_dict(),
            "ppv": self.ppv.as_dict(),
            "npv": self.npv.as_dict(),
        }


def require_target_class(target_class, *, classes) -> str:
    """Validate an explicit one-versus-rest target class before any counting happens.

    ``target_class`` must be a non-empty, non-blank string that is a member of ``classes``. A missing
    (``None`` / non-string / empty / whitespace) target fails with :class:`MissingTargetClassError` -- no class
    may be averaged or assumed -- and an unknown class fails with :class:`OutOfVocabularyClassError`. It exists
    so every multiclass entry point can fail validation *before* it binarises anything.
    """
    if target_class is None or not isinstance(target_class, str) or not target_class.strip():
        raise MissingTargetClassError(
            "a multiclass one-versus-rest rate requires an explicit target_class; no class may be averaged or assumed"
        )
    declared = tuple(classes)
    if target_class not in declared:
        raise OutOfVocabularyClassError(
            f"target class {target_class!r} is outside the declared classes {declared!r}"
        )
    return target_class


def one_vs_rest_metrics(pairs, *, classes: "Sequence[str]", target_class: str) -> TargetClassMetrics:
    """Compute one-versus-rest counts and rates for an explicit ``target_class`` over declared ``classes``.

    ``target_class`` is a *required* keyword-only argument (omitting it is a ``TypeError``) and is validated
    through :func:`require_target_class` *before* the matrix is built, so a missing target fails validation
    ahead of any out-of-vocabulary value that might also be present. The counting reuses the single
    :func:`_matrix` helper -- there is no forked counting implementation -- and the four rates go through
    :func:`safe_rate`.
    """
    declared = _validate_class_order(classes, fn="one_vs_rest_metrics")
    target = require_target_class(target_class, classes=declared)
    matrix = _matrix(declared, pairs)

    row = matrix.cells
    size = len(declared)
    i = declared.index(target)
    tp = row[i][i]
    fn = sum(row[i]) - tp
    fp = sum(row[r][i] for r in range(size)) - tp
    tn = matrix.n - tp - fn - fp

    positive_cases = tp + fn
    negative_cases = tn + fp
    predicted_positives = tp + fp
    predicted_negatives = tn + fn

    return TargetClassMetrics(
        target_class=target,
        classes=declared,
        tp=tp, fn=fn, fp=fp, tn=tn,
        positive_cases=positive_cases,
        negative_cases=negative_cases,
        predicted_positives=predicted_positives,
        predicted_negatives=predicted_negatives,
        eligible=matrix.n,
        sensitivity=safe_rate("Sensitivity", tp, positive_cases),
        specificity=safe_rate("Specificity", tn, negative_cases),
        ppv=safe_rate("PPV", tp, predicted_positives),
        npv=safe_rate("NPV", tn, predicted_negatives),
    )


# ---------------------------------------------------------------------------
# Aggregate entry point -- a thin composition of the primitives above.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ClassificationSummary:
    """The aggregate classification result for the ``classification_summary`` measurement.

    Exactly one branch is populated: the *binary* branch (from a :class:`BinaryClassVocabulary`) exposes the
    counts and the seven rates; the *multiclass* branch (from a declared ``classes`` sequence) exposes the
    shared matrix plus the target-class one-versus-rest view. ``as_dict`` / ``rates_view`` never surface an
    unqualified multiclass rate -- the per-class rates always travel with their ``target_class``.
    """

    kind: str
    counts: "BinaryConfusionCounts | None"
    matrix: "ConfusionMatrix | None"
    metrics: "BinaryClassificationMetrics | None"
    target: "TargetClassMetrics | None"
    target_class: "str | None"
    classes: "tuple[object, ...]"

    def rates_view(self) -> dict:
        """Expose the rates: the seven binary rates directly, or the four target rates under their target."""
        if self.kind == "binary":
            return {name: rate.as_dict() for name, rate in self.metrics.rates.items()}
        return {
            "target_class": self.target_class,
            "rates": {
                "sensitivity": self.target.sensitivity.as_dict(),
                "specificity": self.target.specificity.as_dict(),
                "ppv": self.target.ppv.as_dict(),
                "npv": self.target.npv.as_dict(),
            },
        }

    def as_dict(self) -> dict:
        """Return a stable, JSON-friendly aggregate view with ``None`` branches as ``None``."""
        view: dict = {"kind": self.kind, "classes": list(self.classes)}
        if self.kind == "binary":
            view["counts"] = self.counts.as_dict()
            view["matrix"] = None
            view["target_class"] = None
            view["target"] = None
            # Documented column set (seed-to-code mapping): n, tp/tn/fp/fn and the seven rates.
            view["n"] = self.counts.eligible
            view["tp"] = self.counts.tp
            view["tn"] = self.counts.tn
            view["fp"] = self.counts.fp
            view["fn"] = self.counts.fn
            for name in BinaryClassificationMetrics._RATE_NAMES:
                view[name] = self.metrics.rate(name).as_dict()
        else:
            view["counts"] = None
            view["metrics"] = None
            view["matrix"] = self.matrix.as_dict() if self.matrix is not None else None
            view["target_class"] = self.target_class
            view["target"] = {
                "target_class": self.target_class,
                "sensitivity": self.target.sensitivity.as_dict(),
                "specificity": self.target.specificity.as_dict(),
                "ppv": self.target.ppv.as_dict(),
                "npv": self.target.npv.as_dict(),
            }
        return view


def classification_summary(
    pairs,
    *,
    classes: "Sequence[str] | None" = None,
    vocabulary: "BinaryClassVocabulary | None" = None,
    target_class: "str | None" = None,
) -> ClassificationSummary:
    """Compose the classification measurement from the shared primitives (no independent arithmetic here).

    Exactly one of ``vocabulary`` (binary) / ``classes`` (multiclass) must be supplied. The binary path
    reads its counts and rates straight off :func:`binary_classification_metrics`; the multiclass path
    validates the target class first (so a missing target fails *before* any counting) and then reads the
    shared :func:`_matrix` and :func:`one_vs_rest_metrics`. The result never exposes an unqualified
    multiclass sensitivity / PPV -- those rates always carry their ``target_class``.
    """
    if (vocabulary is None) == (classes is None):
        raise _InvalidSummaryRequestError(
            f"classification_summary needs exactly one of vocabulary/classes; got "
            f"vocabulary={'given' if vocabulary is not None else 'None'} "
            f"classes={'given' if classes is not None else 'None'}"
        )

    if vocabulary is not None:
        metrics = binary_classification_metrics(pairs, vocabulary=vocabulary)
        return ClassificationSummary(
            kind="binary",
            counts=metrics.counts,
            matrix=None,
            metrics=metrics,
            target=None,
            target_class=None,
            classes=vocabulary.classes,
        )

    declared = _validate_class_order(classes, fn="classification_summary")
    # Validation-before-counting: a missing target class fails here, ahead of any out-of-vocabulary value.
    target = require_target_class(target_class, classes=declared)
    matrix = _matrix(declared, pairs)
    target_metrics = one_vs_rest_metrics(pairs, classes=declared, target_class=target)
    return ClassificationSummary(
        kind="multiclass",
        counts=None,
        matrix=matrix,
        metrics=None,
        target=target_metrics,
        target_class=target,
        classes=declared,
    )

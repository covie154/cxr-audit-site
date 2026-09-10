# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Report-v2 measurement entry points (threshold binarisation + label pass-through predictions and classification).

The heavy lifting lives in :mod:`report_v2.measurements.predictions` (prediction) and
:mod:`report_v2.measurements.classification` (confusion counts, rates and one-versus-rest matrices, added by
the Task-07 classification measurements); this package marker re-exports both public surfaces so callers can
``from report_v2.measurements import classify_prediction`` or ``classification_summary`` directly. Nothing here
touches the ORM or the database -- the whole package computes immutable prediction and classification *values*.
"""

from __future__ import annotations

from .classification import (
    BALANCED_ACCURACY_LABEL,
    BinaryClassVocabulary,
    BinaryClassificationMetrics,
    BinaryConfusionCounts,
    ClassificationError,
    ClassificationSummary,
    ConfusionMatrix,
    EmptyPopulationError,
    IncompatiblePairError,
    InvalidClassOrderError,
    MissingTargetClassError,
    OutOfVocabularyClassError,
    Rate,
    TargetClassMetrics,
    binary_classification_metrics,
    binary_confusion_counts,
    classification_summary,
    confusion_matrix,
    one_vs_rest_metrics,
    pairs_from_rows,
    require_target_class,
    safe_rate,
    vocabulary_from_outcome,
)
from .agreement import (
    AgreementConfigurationError,
    AgreementError,
    AgreementValidationError,
    CompleteRows,
    FnFpCases,
    McNemarResult,
    Rate as AgreementRate,
    cohen_kappa,
    complete_rows,
    fn_fp_cases,
    mcnemar,
)
from .descriptive import (
    QUANTILE_METHOD,
    TAIL_METHOD,
    DescriptiveError,
    DurationSummary,
    UnexpectedQuantileMethod,
    categorical_count,
    duration_summary,
    label_count,
    record_count,
)
from .predictions import (
    AGGREGATE_ANY_POSITIVE,
    FindingDecision,
    InvalidPolicyConfigurationError,
    LabelPredictionResult,
    MissingPolicyError,
    NonFiniteScoreError,
    OPERATOR_GT,
    OutOfVocabularyLabelError,
    PolicyEvaluationError,
    PredictionResult,
    ScoreOutOfRangeError,
    UncoveredFindingError,
    classify_label_prediction,
    classify_prediction,
    resolve_policy,
)

__all__ = [
    "OPERATOR_GT",
    "AGGREGATE_ANY_POSITIVE",
    "PolicyEvaluationError",
    "ScoreOutOfRangeError",
    "NonFiniteScoreError",
    "UncoveredFindingError",
    "MissingPolicyError",
    "InvalidPolicyConfigurationError",
    "OutOfVocabularyLabelError",
    "FindingDecision",
    "PredictionResult",
    "LabelPredictionResult",
    "resolve_policy",
    "classify_prediction",
    "classify_label_prediction",
    # --- classification measurements (Task 07) ---
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
    # --- descriptive measurements (Task 08) ---
    "QUANTILE_METHOD",
    "TAIL_METHOD",
    "DescriptiveError",
    "UnexpectedQuantileMethod",
    "DurationSummary",
    "record_count",
    "label_count",
    "categorical_count",
    "duration_summary",
    # --- reference-comparison / agreement measurements (Task 08) ---
    "AgreementError",
    "AgreementValidationError",
    "AgreementConfigurationError",
    "CompleteRows",
    "complete_rows",
    "AgreementRate",
    "cohen_kappa",
    "McNemarResult",
    "mcnemar",
    "FnFpCases",
    "fn_fp_cases",
]

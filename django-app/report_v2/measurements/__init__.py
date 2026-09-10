# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Report-v2 measurement entry points (pure threshold binarisation + label pass-through predictions).

The heavy lifting lives in :mod:`report_v2.measurements.predictions`; this package marker re-exports the
public surface so callers can ``from report_v2.measurements import classify_prediction`` directly. Nothing here
touches the ORM or the database -- the whole module computes immutable prediction *values*.
"""

from __future__ import annotations

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
]

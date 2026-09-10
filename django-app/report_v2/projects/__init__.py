# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Report-v2 project catalog primitives (generic metadata + the PRIME adapter + registries).

This package marker re-exports the public surface so callers can import directly from
:mod:`report_v2.projects` -- the generic value objects and the typed lookup errors from
:mod:`~report_v2.projects.base`, the configured PRIME definition from :mod:`~report_v2.projects.prime`,
and the production / test-only registries plus the ``require_*_context`` guard from
:mod:`~report_v2.projects.registry`.
"""

from __future__ import annotations

from .base import (
    AGGREGATES,
    CrossProjectReferenceError,
    Cohort,
    Dimension,
    KINDS,
    MeasurementSignature,
    Outcome,
    ProjectCatalogError,
    ProjectDefinition,
    SOURCE_OPERATORS,
    Source,
    ThresholdPolicy,
    UnknownCohortError,
    UnknownDimensionError,
    UnknownMeasurementError,
    UnknownOutcomeError,
    UnknownPolicyError,
    UnknownProjectError,
    UnknownSourceError,
)
from .prime import get_project_definition
from .registry import (
    ProjectRegistry,
    production_registry,
    register_production,
    register_test_project,
    require_project_context,
    require_test_project_context,
    test_registry,
)

__all__ = [
    "AGGREGATES",
    "KINDS",
    "SOURCE_OPERATORS",
    "Source",
    "Outcome",
    "Cohort",
    "Dimension",
    "ThresholdPolicy",
    "MeasurementSignature",
    "ProjectDefinition",
    "ProjectCatalogError",
    "UnknownProjectError",
    "UnknownSourceError",
    "UnknownOutcomeError",
    "UnknownCohortError",
    "UnknownDimensionError",
    "UnknownPolicyError",
    "UnknownMeasurementError",
    "CrossProjectReferenceError",
    "get_project_definition",
    "ProjectRegistry",
    "production_registry",
    "register_production",
    "register_test_project",
    "require_project_context",
    "require_test_project_context",
    "test_registry",
]

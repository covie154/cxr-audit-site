# PRIMER - LLM-based Chest X-Ray Audit Tool
# Copyright (C) 2026 Goh Shu Wen
# Licensed under AGPL-3.0-or-later. See LICENSE at the repository root.
"""Generic, project-agnostic catalog metadata for the report-v2 project layer.

This module models the *shape* of a reporting project: the sources it exposes, the binary outcomes it
can measure, the cohorts that restrict a population, the dimensions a reader may filter or compare on,
the versioned threshold policies that bin a numeric score, and the measurement *signatures* a code-side
registry can later fulfil. It is intentionally free of any clinical vocabulary: every concrete identifier,
physical column name and predicate is supplied by an adapter-owned module (for example the PRIME catalog),
so the generic structures and the strict parser used elsewhere never learn what a real study record looks
like. Nothing here imports Django or touches a database -- these are plain, frozen value objects.

Design rules relied upon by the rest of the layer:

* Every structure is an immutable :mod:`dataclasses` snapshot. Construction is keyword-friendly because
  each optional field carries an explicit ``field(default=...)``; collections default through
  ``default_factory`` so two instances never share mutable state.
* Self-validation lives in ``__post_init__`` and fails loudly with a plain :class:`ValueError` when a
  value is internally inconsistent (unknown kind, empty/duplicated class vocabulary, a positive class that
  is not part of the vocabulary, a malformed score scale, or an unsupported operator/aggregate).
* Lookups on :class:`ProjectDefinition` are strict: an absent entry raises the matching
  :class:`ProjectCatalogError` subclass. The error message names only the requested project and the
  missing identifier -- never the contents of any *other* project. The cross-project guard, which is the
  only place that may legitimately mention a second project, lives in :mod:`report_v2.projects.registry`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = [
    "KINDS",
    "SOURCE_OPERATORS",
    "AGGREGATES",
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
]

# ---------------------------------------------------------------------------
# Closed vocabularies for the free-text axes of the metadata model.
# ---------------------------------------------------------------------------
#: The only ``kind`` values a :class:`Source` may declare. ``field`` stays an opaque physical column
#: name owned by the adapter; the kind only tells the measurement layer what *role* the value plays.
KINDS = frozenset({"record_id", "identifier", "label", "score", "duration", "timestamp", "text"})

#: Comparison operators a threshold policy may use to bin a score. Only ``gt`` is shipped today.
SOURCE_OPERATORS = frozenset({"gt"})

#: Aggregation rules a threshold policy may use to combine per-finding decisions. Only ``any_positive``.
AGGREGATES = frozenset({"any_positive"})


# ---------------------------------------------------------------------------
# Error model
# ---------------------------------------------------------------------------
class ProjectCatalogError(Exception):
    """Common base for every catalog lookup rejection.

    Mirrors the simplicity of :class:`report_v2.definitions.loader.DefinitionError`: it carries a single
    human ``message`` and a stable machine-readable ``kind`` discriminator that subclasses override. The
    string form prefixes the message with the ``kind`` so logs and editors can triage without parsing.
    """

    kind = "project-catalog"

    def __init__(self, message: str) -> None:
        self.message = str(message)
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"[{self.kind}] {self.message}"


class UnknownProjectError(ProjectCatalogError):
    """Requested project identifier is not present in the consulted registry."""

    kind = "unknown-project"


class UnknownSourceError(ProjectCatalogError):
    """Requested source identifier is absent from the addressed project."""

    kind = "unknown-source"


class UnknownOutcomeError(ProjectCatalogError):
    """Requested outcome identifier is absent from the addressed project."""

    kind = "unknown-outcome"


class UnknownCohortError(ProjectCatalogError):
    """Requested cohort identifier is absent from the addressed project."""

    kind = "unknown-cohort"


class UnknownDimensionError(ProjectCatalogError):
    """Requested dimension identifier is absent from the addressed project."""

    kind = "unknown-dimension"


class UnknownPolicyError(ProjectCatalogError):
    """Requested threshold policy is absent from, or malformed for, the addressed project."""

    kind = "unknown-policy"


class UnknownMeasurementError(ProjectCatalogError):
    """Requested measurement signature is absent from the addressed project."""

    kind = "unknown-measurement"


class CrossProjectReferenceError(ProjectCatalogError):
    """An identifier that belongs to a *different* registered project was requested from this context.

    Raised by the registry guard -- never by :class:`ProjectDefinition` itself -- so that the message may
    name the two relevant projects (the requested context and the single clear owner) and nothing else.
    """

    kind = "cross-project-reference"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Source:
    """A single readable column surfaced to the measurement layer.

    ``field`` is the physical storage column name and stays completely opaque to this layer; the
    ``kind`` merely records which role the value plays so a signature can require, say, a ``label`` for
    ``ground_truth`` and a ``score`` for ``prediction``.
    """

    source_id: str
    kind: str
    field: str
    unit: str | None = None
    label: str = ""
    description: str = ""
    nullable: bool = True

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"source {self.source_id!r} has unknown kind {self.kind!r}; expected one of {sorted(KINDS)}")


@dataclass(frozen=True)
class Outcome:
    """A measurable binary classification with a declared positive class."""

    outcome_id: str
    classes: tuple[str, ...]
    positive_class: str
    meaning: str = ""

    def __post_init__(self) -> None:
        if not self.classes:
            raise ValueError(f"outcome {self.outcome_id!r} must declare at least one class")
        if len(set(self.classes)) != len(self.classes):
            raise ValueError(f"outcome {self.outcome_id!r} declares duplicate class labels")
        if self.positive_class not in self.classes:
            raise ValueError(
                f"outcome {self.outcome_id!r} positive_class {self.positive_class!r} is not part of its classes {self.classes!r}"
            )


@dataclass(frozen=True)
class Cohort:
    """A named population restriction interpreted by adapters through the predicate filter dict."""

    cohort_id: str
    description: str = ""
    predicate: Mapping[str, Any] = field(default_factory=dict)
    requires_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class Dimension:
    """A filter/compare axis the reader may group by, backed by a physical column."""

    dimension_id: str
    field: str
    label: str = ""
    allowed_values: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ThresholdPolicy:
    """A versioned rule that bins a numeric score into a positive/negative decision."""

    policy_id: str
    version: int
    score_scale: tuple[float, float]
    operator: str
    aggregate: str
    require_all_scores: bool
    findings: Mapping[str, float]
    description: str = ""

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ValueError(f"policy {self.policy_id!r} version must be >= 1, got {self.version!r}")
        if self.operator not in SOURCE_OPERATORS:
            raise ValueError(f"policy {self.policy_id!r} uses unsupported operator {self.operator!r}; expected one of {sorted(SOURCE_OPERATORS)}")
        if self.aggregate not in AGGREGATES:
            raise ValueError(f"policy {self.policy_id!r} uses unsupported aggregate {self.aggregate!r}; expected one of {sorted(AGGREGATES)}")
        if len(self.score_scale) != 2:
            raise ValueError(f"policy {self.policy_id!r} score_scale must be a [lo, hi] pair")
        lo, hi = self.score_scale
        if not lo < hi:
            raise ValueError(f"policy {self.policy_id!r} score_scale requires lo < hi, got {self.score_scale!r}")

    @property
    def ref(self) -> str:
        """Canonical ``id@version`` reference string."""
        return f"{self.policy_id}@{self.version}"


@dataclass(frozen=True)
class MeasurementSignature:
    """Declared contract a code-side measurement implementation must satisfy.

    ``inputs`` maps each required role to the ``kind`` of source it must be bound to (for example
    ``{"ground_truth": "label", "prediction": "score"}``). ``units`` maps an output column key to the
    unit it is expressed in so callers can render and compare values without guessing.
    """

    measurement_id: str
    inputs: Mapping[str, str]
    optional_inputs: Mapping[str, str] = field(default_factory=dict)
    requires_threshold_policy: bool = False
    supports_comparison: bool = False
    supported_displays: tuple[str, ...] = ()
    units: Mapping[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass(frozen=True)
class ProjectDefinition:
    """An immutable bundle of every catalog entry belonging to one reporting project.

    Mappings are keyed by the respective entry identifier. Construction verifies that each stored value's
    own identifier attribute agrees with the key it was placed under, so a mis-keyed registry can never be
    built silently. (Duplicate keys are impossible for a :class:`dict`; the id/key agreement check is the
    meaningful integrity gate here.)
    """

    project_id: str
    display_name: str
    timezone: str = "Asia/Singapore"
    model_label: str = ""
    sources: Mapping[str, Source] = field(default_factory=dict)
    outcomes: Mapping[str, Outcome] = field(default_factory=dict)
    cohorts: Mapping[str, Cohort] = field(default_factory=dict)
    dimensions: Mapping[str, Dimension] = field(default_factory=dict)
    policies: Mapping[str, ThresholdPolicy] = field(default_factory=dict)
    measurements: Mapping[str, MeasurementSignature] = field(default_factory=dict)

    # The collection -> (mapping attribute, id attribute) pairs used by the integrity check.
    _COLLECTIONS = (
        ("sources", "source_id"),
        ("outcomes", "outcome_id"),
        ("cohorts", "cohort_id"),
        ("dimensions", "dimension_id"),
        ("policies", "policy_id"),
        ("measurements", "measurement_id"),
    )

    def __post_init__(self) -> None:
        for attr, id_attr in ProjectDefinition._COLLECTIONS:
            entries = getattr(self, attr)
            if entries is None:
                object.__setattr__(self, attr, {})
                continue
            for key, value in entries.items():
                declared = getattr(value, id_attr, None)
                if declared != key:
                    raise ValueError(
                        f"project {self.project_id!r} maps {attr} key {key!r} to an entry whose "
                        f"{id_attr} is {declared!r}; the key must equal the entry's own identifier"
                    )

    # -- strict, project-local lookups (each raises only for THIS project) --
    def source(self, source_id: str) -> Source:
        try:
            return self.sources[source_id]
        except KeyError:
            raise UnknownSourceError(f"unknown source {source_id!r} for project {self.project_id!r}") from None

    def outcome(self, outcome_id: str) -> Outcome:
        try:
            return self.outcomes[outcome_id]
        except KeyError:
            raise UnknownOutcomeError(f"unknown outcome {outcome_id!r} for project {self.project_id!r}") from None

    def cohort(self, cohort_id: str) -> Cohort:
        try:
            return self.cohorts[cohort_id]
        except KeyError:
            raise UnknownCohortError(f"unknown cohort {cohort_id!r} for project {self.project_id!r}") from None

    def dimension(self, dimension_id: str) -> Dimension:
        try:
            return self.dimensions[dimension_id]
        except KeyError:
            raise UnknownDimensionError(f"unknown dimension {dimension_id!r} for project {self.project_id!r}") from None

    def measurement(self, measurement_id: str) -> MeasurementSignature:
        try:
            return self.measurements[measurement_id]
        except KeyError:
            raise UnknownMeasurementError(
                f"unknown measurement {measurement_id!r} for project {self.project_id!r}"
            ) from None

    def policy(self, ref: str) -> ThresholdPolicy:
        """Resolve a ``id@version`` reference, or a bare ``id`` naming its single registered version.

        Malformed references (empty id, empty or non-numeric version) are rejected as
        :class:`UnknownPolicyError` -- the lookup never guesses at a default version.
        """
        if not isinstance(ref, str) or not ref:
            raise UnknownPolicyError(f"malformed policy reference {ref!r}")
        if "@" in ref:
            policy_id, _, raw_version = ref.partition("@")
            if not policy_id:
                raise UnknownPolicyError(f"malformed policy reference {ref!r}: missing identifier")
            try:
                version = int(raw_version)
            except (ValueError, TypeError):
                raise UnknownPolicyError(f"malformed policy reference {ref!r}: version is not an integer") from None
            policy = self.policies.get(policy_id)
            if policy is None or policy.version != version:
                raise UnknownPolicyError(f"unknown policy {ref!r} for project {self.project_id!r}")
            return policy
        policy = self.policies.get(ref)
        if policy is None:
            raise UnknownPolicyError(f"unknown policy {ref!r} for project {self.project_id!r}")
        return policy
